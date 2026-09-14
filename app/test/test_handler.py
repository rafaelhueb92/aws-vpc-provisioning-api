import json
from decimal import Decimal

VALID_BODY = {
    "name": "my-vpc",
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


def route_table_named(fake_ec2, name: str) -> dict:
    return next(
        table
        for table in fake_ec2.route_tables.values()
        if any(tag["Value"] == name for tag in table["Tags"])
    )


def test_health_returns_200(unit_client):
    response = unit_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"health": True}


def test_unknown_path_returns_400(unit_client):
    response = unit_client.get("/nope")

    assert response.status_code == 400
    assert response.json()["message"] == "Unsupported method or path"


def test_unsupported_method_returns_400(unit_client):
    response = unit_client.request("PUT", "/vpcs/whatever", vpc_id="vpc-1")

    assert response.status_code == 400
    assert response.json()["message"] == "Unsupported method or path"


def test_get_without_vpc_id_returns_400(unit_client):
    response = unit_client.get("/vpcs")

    assert response.status_code == 400
    assert response.json()["message"] == "vpc_id path parameter is required"


def test_delete_without_vpc_id_returns_400(unit_client):
    response = unit_client.delete("/vpcs")

    assert response.status_code == 400
    assert "vpc_id" in response.json()["message"]


def test_post_with_malformed_json_returns_400(unit_client):
    response = unit_client.post("/vpcs", raw_body="{not json")

    assert response.status_code == 400
    assert "message" in response.json()


def test_post_without_body_returns_400(unit_client):
    response = unit_client.post("/vpcs")

    assert response.status_code == 400
    assert "validation error" in response.json()["message"].lower()


def test_post_with_invalid_cidr_returns_400(unit_client):
    response = unit_client.post("/vpcs", body={"name": "v", "cidr": "not-a-cidr"})

    assert response.status_code == 400


def test_post_with_subnet_outside_vpc_returns_400(unit_client):
    body = {
        "name": "v",
        "cidr": "10.0.0.0/16",
        "subnets": [
            {"name": "bad", "cidr": "10.1.0.0/24", "availability_zone": "us-east-1a"}
        ],
    }

    response = unit_client.post("/vpcs", body=body)

    assert response.status_code == 400
    assert "is not within VPC CIDR" in response.json()["message"]


def test_post_with_overlapping_subnets_returns_400(unit_client):
    body = {
        "name": "v",
        "cidr": "10.0.0.0/16",
        "subnets": [
            {"name": "a", "cidr": "10.0.1.0/24", "availability_zone": "us-east-1a"},
            {"name": "b", "cidr": "10.0.1.0/25", "availability_zone": "us-east-1b"},
        ],
    }

    response = unit_client.post("/vpcs", body=body)

    assert response.status_code == 400
    assert "conflict" in response.json()["message"]


def test_invalid_post_never_calls_aws(unit_client, fake_ec2):
    unit_client.post("/vpcs", body={"name": "v", "cidr": "bad"})

    assert fake_ec2.calls == []


def test_post_creates_vpc_and_subnets(unit_client, fake_ec2):
    response = unit_client.post("/vpcs", body=VALID_BODY)

    assert response.status_code == 200
    payload = response.json()
    assert payload["vpc_id"] == "vpc-00000001"
    assert sorted(payload["subnet_ids"]) == ["subnet-00000002", "subnet-00000003"]
    assert "created with success" in payload["message"]

    assert fake_ec2.calls_of("create_vpc")[0][1] == {"CidrBlock": "10.0.0.0/16"}
    subnet_calls = fake_ec2.calls_of("create_subnet")
    assert sorted(
        (call[1]["CidrBlock"], call[1]["AvailabilityZone"]) for call in subnet_calls
    ) == [("10.0.1.0/24", "us-east-1a"), ("10.0.2.0/24", "us-east-1b")]


def test_post_maps_public_ip_only_for_public_subnets(unit_client, fake_ec2):
    unit_client.post("/vpcs", body=VALID_BODY)

    modified = [call[1]["SubnetId"] for call in fake_ec2.calls_of("modify_subnet_attribute")]
    assert [fake_ec2.subnets[subnet_id]["CidrBlock"] for subnet_id in modified] == [
        "10.0.1.0/24"
    ]


def test_post_creates_a_separate_route_table_for_public_and_private_subnets(
    unit_client, fake_ec2
):
    unit_client.post("/vpcs", body=VALID_BODY)

    assert len(fake_ec2.calls_of("create_route_table")) == 2
    names = {table["Tags"][0]["Value"] for table in fake_ec2.route_tables.values()}
    assert names == {"my-vpc-public-rt", "my-vpc-private-rt"}


def test_post_routes_the_public_route_table_to_the_internet_gateway(unit_client, fake_ec2):
    unit_client.post("/vpcs", body=VALID_BODY)

    igw_id = next(iter(fake_ec2.internet_gateways))
    public_table = route_table_named(fake_ec2, "my-vpc-public-rt")
    attached = fake_ec2.calls_of("attach_internet_gateway")

    assert [call[1]["VpcId"] for call in attached] == ["vpc-00000001"]
    assert public_table["Routes"] == [
        {"DestinationCidrBlock": "0.0.0.0/0", "GatewayId": igw_id, "State": "active"}
    ]


def test_post_keeps_the_private_route_table_without_an_outside_route(unit_client, fake_ec2):
    unit_client.post("/vpcs", body=VALID_BODY)

    private_table = route_table_named(fake_ec2, "my-vpc-private-rt")

    assert private_table["Routes"] == []


def test_post_associates_each_subnet_with_its_route_table(unit_client, fake_ec2):
    unit_client.post("/vpcs", body=VALID_BODY)

    subnet_ids = {
        subnet["CidrBlock"]: subnet["SubnetId"] for subnet in fake_ec2.subnets.values()
    }
    public_table = route_table_named(fake_ec2, "my-vpc-public-rt")
    private_table = route_table_named(fake_ec2, "my-vpc-private-rt")

    assert [a["SubnetId"] for a in public_table["Associations"]] == [subnet_ids["10.0.1.0/24"]]
    assert [a["SubnetId"] for a in private_table["Associations"]] == [subnet_ids["10.0.2.0/24"]]


def test_post_without_a_public_subnet_skips_the_internet_gateway(unit_client, fake_ec2):
    body = {
        "name": "private-only",
        "cidr": "10.0.0.0/16",
        "subnets": [
            {
                "name": "private-1",
                "cidr": "10.0.1.0/24",
                "availability_zone": "us-east-1a",
                "is_public": False,
            }
        ],
    }

    unit_client.post("/vpcs", body=body)

    assert fake_ec2.calls_of("create_internet_gateway") == []
    assert fake_ec2.calls_of("create_route") == []
    names = {table["Tags"][0]["Value"] for table in fake_ec2.route_tables.values()}
    assert names == {"private-only-private-rt"}


def test_post_waits_for_the_vpc_and_every_subnet(unit_client, fake_ec2):
    unit_client.post("/vpcs", body=VALID_BODY)

    waiter_calls = fake_ec2.calls_of("get_waiter")
    assert [call[1] for call in waiter_calls] == [
        "vpc_available",
        "subnet_available",
        "subnet_available",
    ]


def test_post_persists_the_vpc_and_its_subnets(unit_client, fake_table):
    unit_client.post("/vpcs", body=VALID_BODY)

    rows = fake_table.rows("vpc-00000001")
    assert [row["resource_key"] for row in rows] == [
        "subnet-00000002",
        "subnet-00000003",
        "vpc-00000001",
    ]
    vpc_row = next(row for row in rows if row["resource_key"] == "vpc-00000001")
    assert vpc_row["name"] == "my-vpc"
    assert vpc_row["cidr"] == "10.0.0.0/16"
    assert rows[0]["is_public"] is True
    assert rows[1]["is_public"] is False


def test_post_persists_the_records_in_a_batch(unit_client, fake_table):
    unit_client.post("/vpcs", body=VALID_BODY)

    assert len(fake_table.calls_of("batch_put_item")) == 3
    assert fake_table.calls_of("put_item") == []


def test_post_without_subnets_is_allowed(unit_client, fake_ec2):
    response = unit_client.post("/vpcs", body={"name": "empty", "cidr": "10.9.0.0/16"})

    assert response.status_code == 200
    assert response.json()["subnet_ids"] == []
    assert fake_ec2.calls_of("create_subnet") == []
    assert fake_ec2.route_tables == {}


def test_get_returns_the_stored_vpc(unit_client, fake_table):
    fake_table.put_item(
        Item={
            "vpc_id": "vpc-1",
            "resource_key": "vpc-1",
            "name": "my-vpc",
            "cidr": "10.0.0.0/16",
        }
    )

    response = unit_client.get("/vpcs/vpc-1", vpc_id="vpc-1")

    assert response.status_code == 200
    assert response.json()["name"] == "my-vpc"
    assert response.json()["cidr"] == "10.0.0.0/16"


def test_get_unknown_vpc_returns_404(unit_client):
    response = unit_client.get("/vpcs/vpc-does-not-exist", vpc_id="vpc-does-not-exist")

    assert response.status_code == 404
    assert "not found" in response.json()["message"]


def test_get_serializes_dynamodb_numbers(unit_client, fake_table):
    fake_table.put_item(
        Item={
            "vpc_id": "vpc-1",
            "resource_key": "vpc-1",
            "name": "my-vpc",
            "subnet_count": Decimal("3"),
        }
    )

    response = unit_client.get("/vpcs/vpc-1", vpc_id="vpc-1")

    assert response.status_code == 200
    assert json.loads(response.body)["subnet_count"] == "3"


def test_delete_removes_subnets_then_vpc_then_records(unit_client, fake_table):
    fake_table.put_item(Item={"vpc_id": "vpc-00000001", "resource_key": "vpc-00000001"})
    fake_table.put_item(Item={"vpc_id": "vpc-00000001", "resource_key": "subnet-00000002"})
    unit_client.post("/vpcs", body=VALID_BODY)

    response = unit_client.delete("/vpcs/vpc-00000001", vpc_id="vpc-00000001")

    assert response.status_code == 200
    assert "deleted" in response.json()["message"]
    assert fake_table.rows("vpc-00000001") == []


def test_delete_removes_the_stored_records_in_a_batch(unit_client, fake_table):
    unit_client.post("/vpcs", body=VALID_BODY)
    stored = [call[2] for call in fake_table.calls_of("batch_put_item")]
    fake_table.calls.clear()

    unit_client.delete("/vpcs/vpc-00000001", vpc_id="vpc-00000001")

    deleted = [call[2] for call in fake_table.calls_of("batch_delete_item")]
    assert sorted(deleted) == sorted(stored)
    assert fake_table.calls_of("delete_item") == []


def test_delete_removes_subnets_before_the_vpc(unit_client, fake_ec2):
    unit_client.post("/vpcs", body=VALID_BODY)
    fake_ec2.calls.clear()

    unit_client.delete("/vpcs/vpc-00000001", vpc_id="vpc-00000001")

    operations = fake_ec2.operations()
    assert operations.index("describe_subnets") < operations.index("delete_subnet")
    assert operations.index("delete_subnet") < operations.index("delete_vpc")


def test_delete_removes_the_route_tables(unit_client, fake_ec2):
    unit_client.post("/vpcs", body=VALID_BODY)
    fake_ec2.calls.clear()

    unit_client.delete("/vpcs/vpc-00000001", vpc_id="vpc-00000001")

    operations = fake_ec2.operations()
    assert len(fake_ec2.calls_of("disassociate_route_table")) == 2
    assert len(fake_ec2.calls_of("delete_route_table")) == 2
    assert operations.index("disassociate_route_table") < operations.index("delete_route_table")
    assert operations.index("delete_route_table") < operations.index("delete_subnet")
    assert fake_ec2.route_tables == {}


def test_delete_detaches_and_deletes_the_internet_gateway(unit_client, fake_ec2):
    unit_client.post("/vpcs", body=VALID_BODY)
    igw_id = next(iter(fake_ec2.internet_gateways))
    fake_ec2.calls.clear()

    unit_client.delete("/vpcs/vpc-00000001", vpc_id="vpc-00000001")

    operations = fake_ec2.operations()
    detached = [c[1]["InternetGatewayId"] for c in fake_ec2.calls_of("detach_internet_gateway")]
    deleted = [c[1]["InternetGatewayId"] for c in fake_ec2.calls_of("delete_internet_gateway")]
    assert detached == [igw_id]
    assert deleted == [igw_id]
    assert "detach_internet_gateway" in operations
    assert operations.index("detach_internet_gateway") < operations.index("delete_internet_gateway")
    assert operations.index("delete_internet_gateway") < operations.index("delete_vpc")
    assert fake_ec2.internet_gateways == {}


def test_not_found_client_error_returns_404(unit_client, fake_ec2, client_error):
    fake_ec2.raise_on("delete_vpc", client_error("InvalidVpcID.NotFound"))

    response = unit_client.delete("/vpcs/vpc-123", vpc_id="vpc-123")

    assert response.status_code == 404
    assert response.json()["message"] == "InvalidVpcID.NotFound"


def test_other_client_errors_return_502(unit_client, fake_ec2, client_error):
    fake_ec2.raise_on("delete_vpc", client_error("DependencyViolation"))

    response = unit_client.delete("/vpcs/vpc-123", vpc_id="vpc-123")

    assert response.status_code == 502
    assert response.json()["message"] == "DependencyViolation"


def test_client_error_on_create_returns_502(unit_client, fake_ec2, client_error):
    fake_ec2.raise_on("create_vpc", client_error("VpcLimitExceeded"))

    response = unit_client.post("/vpcs", body=VALID_BODY)

    assert response.status_code == 502
