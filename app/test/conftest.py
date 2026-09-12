import itertools
import json
import os
import sys
from pathlib import Path
from typing import Any, Generator, Optional

import pytest

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

TEST_TABLE_NAME = "vpc-provisioning-records-test"
TEST_REGION = "us-east-1"

os.environ["AWS_REGION"] = TEST_REGION
os.environ["AWS_DEFAULT_REGION"] = TEST_REGION
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["DDB_TABLE_NAME"] = TEST_TABLE_NAME
os.environ["LOG_LEVEL"] = "WARNING"
os.environ.pop("AWS_ENDPOINT_URL", None)


@pytest.fixture(scope="session")
def aws() -> Generator[None, None, None]:
    moto = pytest.importorskip("moto", reason="moto is required for the AWS backed fixtures")
    mock = moto.mock_aws()
    mock.start()
    try:
        yield mock
    finally:
        mock.stop()


@pytest.fixture(scope="session")
def records_table(aws) -> Generator[Any, None, None]:
    import boto3

    resource = boto3.resource("dynamodb", region_name=TEST_REGION)
    resource.create_table(
        TableName=TEST_TABLE_NAME,
        KeySchema=[
            {"AttributeName": "vpc_id", "KeyType": "HASH"},
            {"AttributeName": "sort_key", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "vpc_id", "AttributeType": "S"},
            {"AttributeName": "sort_key", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    yield resource.Table(TEST_TABLE_NAME)


@pytest.fixture(scope="session")
def lambda_module(aws):
    import handler

    return handler


def _truncate(table) -> None:
    keys = [
        {"vpc_id": item["vpc_id"], "sort_key": item["sort_key"]}
        for item in table.scan()["Items"]
    ]
    with table.batch_writer() as batch:
        for key in keys:
            batch.delete_item(Key=key)


class FakeWaiter:
    def __init__(self, client: "FakeEc2Client", name: str) -> None:
        self._client = client
        self._name = name

    def wait(self, **kwargs) -> None:
        self._client.record(("wait", self._name), **kwargs)


class FakeEc2Client:

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.vpcs: dict[str, dict] = {}
        self.subnets: dict[str, dict] = {}
        self.internet_gateways: dict[str, str] = {}
        self._ids = itertools.count(1)
        self._errors: dict[str, Exception] = {}

    def record(self, *args, **kwargs) -> None:
        self.calls.append(args + (kwargs,) if kwargs else args)

    def raise_on(self, operation: str, error: Exception) -> None:
        self._errors[operation] = error

    def operations(self) -> list[str]:
        return [call[0] for call in self.calls]

    def calls_of(self, operation: str) -> list[tuple]:
        return [call for call in self.calls if call[0] == operation]

    def _maybe_raise(self, operation: str) -> None:
        error = self._errors.pop(operation, None)
        if error is not None:
            raise error

    def get_waiter(self, name: str) -> FakeWaiter:
        self.record("get_waiter", name)
        return FakeWaiter(self, name)

    def create_vpc(self, CidrBlock: str) -> dict:
        self.record("create_vpc", CidrBlock=CidrBlock)
        self._maybe_raise("create_vpc")
        vpc_id = f"vpc-{next(self._ids):08d}"
        self.vpcs[vpc_id] = {
            "VpcId": vpc_id,
            "CidrBlock": CidrBlock,
            "State": "available",
            "Tags": [],
        }
        return {"Vpc": self.vpcs[vpc_id]}

    def delete_vpc(self, VpcId: str) -> dict:
        self.record("delete_vpc", VpcId=VpcId)
        self._maybe_raise("delete_vpc")
        self.vpcs.pop(VpcId, None)
        return {}

    def create_tags(self, Resources: list, Tags: list) -> dict:
        self.record("create_tags", Resources=Resources, Tags=Tags)
        for resource_id in Resources:
            if resource_id in self.vpcs:
                self.vpcs[resource_id]["Tags"] = Tags
            elif resource_id in self.subnets:
                self.subnets[resource_id]["Tags"] = Tags
        return {}

    def create_subnet(self, VpcId: str, CidrBlock: str, AvailabilityZone: str) -> dict:
        self.record(
            "create_subnet",
            VpcId=VpcId,
            CidrBlock=CidrBlock,
            AvailabilityZone=AvailabilityZone,
        )
        self._maybe_raise("create_subnet")
        subnet_id = f"subnet-{next(self._ids):08d}"
        self.subnets[subnet_id] = {
            "SubnetId": subnet_id,
            "VpcId": VpcId,
            "CidrBlock": CidrBlock,
            "AvailabilityZone": AvailabilityZone,
            "MapPublicIpOnLaunch": False,
            "Tags": [],
        }
        return {"Subnet": self.subnets[subnet_id]}

    def delete_subnet(self, SubnetId: str) -> dict:
        self.record("delete_subnet", SubnetId=SubnetId)
        self._maybe_raise("delete_subnet")
        self.subnets.pop(SubnetId, None)
        return {}

    def modify_subnet_attribute(self, SubnetId: str, MapPublicIpOnLaunch: dict) -> dict:
        self.record(
            "modify_subnet_attribute",
            SubnetId=SubnetId,
            MapPublicIpOnLaunch=MapPublicIpOnLaunch,
        )
        if SubnetId in self.subnets:
            self.subnets[SubnetId]["MapPublicIpOnLaunch"] = MapPublicIpOnLaunch["Value"]
        return {}

    def describe_subnets(self, Filters: Optional[list] = None) -> dict:
        self.record("describe_subnets", Filters=Filters)
        self._maybe_raise("describe_subnets")
        vpc_id = None
        for query_filter in Filters or []:
            if query_filter.get("Name") == "vpc-id":
                vpc_id = query_filter["Values"][0]
        subnets = [s for s in self.subnets.values() if vpc_id is None or s["VpcId"] == vpc_id]
        return {"Subnets": subnets}

    def create_internet_gateway(self) -> dict:
        self.record("create_internet_gateway")
        self._maybe_raise("create_internet_gateway")
        igw_id = f"igw-{next(self._ids):08d}"
        self.internet_gateways[igw_id] = None
        return {"InternetGateway": {"InternetGatewayId": igw_id}}

    def attach_internet_gateway(self, InternetGatewayId: str, VpcId: str) -> dict:
        self.record("attach_internet_gateway", InternetGatewayId=InternetGatewayId, VpcId=VpcId)
        return {}

    def detach_internet_gateway(self, InternetGatewayId: str, VpcId: str) -> dict:
        self.record("detach_internet_gateway", InternetGatewayId=InternetGatewayId, VpcId=VpcId)
        return {}

    def delete_internet_gateway(self, InternetGatewayId: str) -> dict:
        self.record("delete_internet_gateway", InternetGatewayId=InternetGatewayId)
        self.internet_gateways.pop(InternetGatewayId, None)
        return {}

    def describe_internet_gateways(self, Filters: Optional[list] = None) -> dict:
        self.record("describe_internet_gateways", Filters=Filters)
        vpc_id = None
        for query_filter in Filters or []:
            if query_filter.get("Name") == "attachment.vpc-id":
                vpc_id = query_filter["Values"][0]
        if not vpc_id or vpc_id not in self.vpcs:
            return {"InternetGateways": []}
        return {
            "InternetGateways": [
                {"InternetGatewayId": igw_id} for igw_id in self.internet_gateways
            ]
        }


class FakeTable:

    def __init__(self) -> None:
        self.items: dict[tuple, dict] = {}
        self.calls: list[tuple] = []

    def put_item(self, Item: dict, **kwargs) -> dict:
        self.calls.append(("put_item", Item["vpc_id"], Item["sort_key"]))
        self.items[(Item["vpc_id"], Item["sort_key"])] = Item
        return {}

    def get_item(self, Key: dict, **kwargs) -> dict:
        self.calls.append(("get_item", Key["vpc_id"], Key["sort_key"]))
        item = self.items.get((Key["vpc_id"], Key["sort_key"]))
        return {"Item": item} if item is not None else {}

    def delete_item(self, Key: dict, **kwargs) -> dict:
        self.calls.append(("delete_item", Key["vpc_id"], Key["sort_key"]))
        self.items.pop((Key["vpc_id"], Key["sort_key"]), None)
        return {}

    def query(self, KeyConditionExpression, **kwargs) -> dict:
        self.calls.append(("query", kwargs))
        expression = KeyConditionExpression.get_expression()
        key_name = getattr(expression["values"][0], "name", None)
        if key_name != "vpc_id":
            raise AssertionError(
                f"FakeTable supports a vpc_id equality condition only, got {key_name!r}"
            )
        vpc_id = expression["values"][1]
        return {"Items": self.rows(vpc_id)}

    def rows(self, vpc_id: str) -> list[dict]:
        return [item for (item_vpc, _), item in sorted(self.items.items()) if item_vpc == vpc_id]


@pytest.fixture()
def fake_ec2() -> FakeEc2Client:
    return FakeEc2Client()


@pytest.fixture()
def fake_table() -> FakeTable:
    return FakeTable()


@pytest.fixture()
def logger():
    import logging

    return logging.getLogger("test")


@pytest.fixture()
def client_error():
    from botocore.exceptions import ClientError

    def _factory(code: str) -> ClientError:
        return ClientError({"Error": {"Code": code, "Message": code}}, "OperationName")

    return _factory


class LambdaResponse:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.status_code = result.get("statusCode")
        self.body = result.get("body")

    def json(self) -> Any:
        return json.loads(self.body) if self.body else None

    def __repr__(self) -> str:
        return f"<LambdaResponse {self.status_code} {self.body!r}>"


class ApiGatewayClient:

    def __init__(self, module) -> None:
        self._module = module

    def request(
        self,
        method: str,
        path: str,
        vpc_id: Optional[str] = None,
        body: Optional[dict] = None,
        raw_body: Optional[str] = None,
    ) -> LambdaResponse:
        event: dict = {
            "httpMethod": method,
            "path": path,
            "pathParameters": {"vpc_id": vpc_id} if vpc_id else None,
        }
        if raw_body is not None:
            event["body"] = raw_body
        elif body is not None:
            event["body"] = json.dumps(body)
        return LambdaResponse(self._module.lambda_handler(event, {}))

    def get(self, path: str, vpc_id: Optional[str] = None) -> LambdaResponse:
        return self.request("GET", path, vpc_id=vpc_id)

    def post(
        self, path: str, body: Optional[dict] = None, raw_body: Optional[str] = None
    ) -> LambdaResponse:
        return self.request("POST", path, body=body, raw_body=raw_body)

    def delete(self, path: str, vpc_id: Optional[str] = None) -> LambdaResponse:
        return self.request("DELETE", path, vpc_id=vpc_id)


@pytest.fixture()
def client(lambda_module, records_table) -> Generator[ApiGatewayClient, None, None]:
    _truncate(records_table)
    yield ApiGatewayClient(lambda_module)
    _truncate(records_table)


@pytest.fixture()
def unit_client(lambda_module, monkeypatch, fake_ec2, fake_table, logger) -> ApiGatewayClient:
    from services.storage import Storage
    from services.subnet import Subnet
    from services.vpc import VPC

    monkeypatch.setattr(lambda_module, "vpc", VPC(fake_ec2, logger))
    monkeypatch.setattr(lambda_module, "subnet", Subnet(fake_ec2, logger))
    monkeypatch.setattr(lambda_module, "storage", Storage(fake_table, TEST_TABLE_NAME))
    return ApiGatewayClient(lambda_module)
