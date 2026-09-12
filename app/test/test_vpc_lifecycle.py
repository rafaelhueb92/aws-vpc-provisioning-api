import boto3
import pytest
from conftest import TEST_TABLE_NAME

BODY = {
    "name": "integration-vpc",
    "cidr": "10.0.0.0/16",
    "subnets": [
        {
            "name": "public-1",
            "cidr": "10.0.1.0/24",
            "availability_zone": "us-east-1a",
            "is_public": True,
        },
        {
            "name": "private-1",
            "cidr": "10.0.2.0/24",
            "availability_zone": "us-east-1b",
            "is_public": False,
        },
    ],
}


@pytest.fixture()
def ec2():
    return boto3.client("ec2", region_name="us-east-1")


def test_lambda_uses_the_configured_table(lambda_module):
    assert lambda_module.settings.vpc_table == TEST_TABLE_NAME
    assert lambda_module.storage.table_name == TEST_TABLE_NAME


def test_post_creates_a_real_vpc_and_subnets(client, ec2):
    response = client.post("/vpcs", body=BODY)

    assert response.status_code == 200
    payload = response.json()
    vpc_id = payload["vpc_id"]
    assert vpc_id.startswith("vpc-")
    assert len(payload["subnet_ids"]) == 2

    vpc = ec2.describe_vpcs(VpcIds=[vpc_id])["Vpcs"][0]
    assert vpc["CidrBlock"] == "10.0.0.0/16"
    assert vpc["State"] == "available"
    assert {"Key": "Name", "Value": "integration-vpc"} in vpc["Tags"]

    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["Subnets"]
    assert sorted(s["CidrBlock"] for s in subnets) == ["10.0.1.0/24", "10.0.2.0/24"]
    public_flags = {
        s["CidrBlock"]: s["MapPublicIpOnLaunch"] for s in subnets
    }
    assert public_flags == {"10.0.1.0/24": True, "10.0.2.0/24": False}


def test_post_stores_the_vpc_and_subnet_records(client, records_table):
    payload = client.post("/vpcs", body=BODY).json()
    vpc_id = payload["vpc_id"]

    rows = records_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("vpc_id").eq(vpc_id)
    )["Items"]

    assert sorted(row["sort_key"] for row in rows) == sorted([vpc_id] + payload["subnet_ids"])
    vpc_row = next(row for row in rows if row["sort_key"] == vpc_id)
    assert vpc_row["name"] == "integration-vpc"
    assert vpc_row["cidr"] == "10.0.0.0/16"
    assert "updated_at" in vpc_row


def test_get_returns_the_created_vpc(client):
    created = client.post("/vpcs", body=BODY).json()

    response = client.get(f"/vpcs/{created['vpc_id']}", vpc_id=created["vpc_id"])

    assert response.status_code == 200
    assert response.json()["name"] == "integration-vpc"
    assert response.json()["cidr"] == "10.0.0.0/16"


def test_get_unknown_vpc_returns_404(client):
    response = client.get("/vpcs/vpc-00000000000000000", vpc_id="vpc-00000000000000000")

    assert response.status_code == 404


def test_delete_removes_the_vpc_subnets_and_records(client, ec2, records_table):
    created = client.post("/vpcs", body=BODY).json()
    vpc_id = created["vpc_id"]

    response = client.delete(f"/vpcs/{vpc_id}", vpc_id=vpc_id)

    assert response.status_code == 200
    with pytest.raises(ec2.exceptions.ClientError) as error:
        ec2.describe_vpcs(VpcIds=[vpc_id])
    assert error.value.response["Error"]["Code"] == "InvalidVpcID.NotFound"
    assert ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["Subnets"] == []
    rows = records_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("vpc_id").eq(vpc_id)
    )["Items"]
    assert rows == []


def test_delete_is_not_idempotent_by_design(client):
    created = client.post("/vpcs", body=BODY).json()
    vpc_id = created["vpc_id"]

    assert client.delete(f"/vpcs/{vpc_id}", vpc_id=vpc_id).status_code == 200
    second = client.delete(f"/vpcs/{vpc_id}", vpc_id=vpc_id)
    assert second.status_code == 404


def test_delete_removes_an_attached_internet_gateway(client, ec2, lambda_module):
    created = client.post("/vpcs", body=BODY).json()
    vpc_id = created["vpc_id"]
    igw_id = lambda_module.vpc.create_internet_gateway(vpc_id)

    assert client.delete(f"/vpcs/{vpc_id}", vpc_id=vpc_id).status_code == 200

    assert (
        ec2.describe_internet_gateways(
            Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}]
        )["InternetGateways"]
        == []
    )
    with pytest.raises(ec2.exceptions.ClientError) as error:
        ec2.describe_internet_gateways(InternetGatewayIds=[igw_id])
    assert error.value.response["Error"]["Code"] == "InvalidInternetGatewayID.NotFound"


def test_invalid_request_does_not_touch_aws(client, ec2):
    before = len(ec2.describe_vpcs()["Vpcs"])

    response = client.post("/vpcs", body={"name": "bad", "cidr": "10.0.0.0/16",
                                          "subnets": [{"name": "x", "cidr": "10.9.0.0/24",
                                                       "availability_zone": "us-east-1a"}]})

    assert response.status_code == 400
    assert len(ec2.describe_vpcs()["Vpcs"]) == before
