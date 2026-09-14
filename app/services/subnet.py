from concurrent.futures import ThreadPoolExecutor
from typing import Any

from config import get_settings


class Subnet:

    def __init__(self, client, logger):
        settings = get_settings()
        self.subnet_client = client
        self.map_public_ip = settings.subnet_map_public_ip
        self.max_workers = settings.subnet_max_workers
        self.waiter_config = {
            "Delay": settings.subnet_waiter_delay,
            "MaxAttempts": settings.subnet_waiter_max_attempts,
        }
        self.logger = logger

    def create_subnet(self, vpc_id: str, subnet_props: Any) -> dict:
        name = subnet_props["name"]
        cidr = subnet_props["cidr"]
        availability_zone = subnet_props["availability_zone"]
        is_public = subnet_props["is_public"]

        self.logger.info("Creating subnet %s (%s) in %s", name, cidr, availability_zone)

        response = self.subnet_client.create_subnet(
            VpcId=vpc_id,
            CidrBlock=cidr,
            AvailabilityZone=availability_zone,
        )
        subnet_id = response["Subnet"]["SubnetId"]

        self.subnet_client.create_tags(
            Resources=[subnet_id], Tags=[{"Key": "Name", "Value": name}]
        )

        waiter = self.subnet_client.get_waiter("subnet_available")
        waiter.wait(SubnetIds=[subnet_id], WaiterConfig=self.waiter_config)

        if is_public and self.map_public_ip:
            self.subnet_client.modify_subnet_attribute(
                SubnetId=subnet_id, MapPublicIpOnLaunch={"Value": True}
            )

        self.logger.info("Created subnet %s with ID: %s", name, subnet_id)

        return {
            "name": name,
            "subnet_id": subnet_id,
            "cidr": cidr,
            "availability_zone": availability_zone,
            "is_public": is_public,
        }

    def create_subnets(self, vpc_id: str, subnet_props_list) -> list[dict]:
        subnet_props_list = list(subnet_props_list or [])
        if not subnet_props_list:
            return []

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            return list(
                pool.map(lambda props: self.create_subnet(vpc_id, props), subnet_props_list)
            )

    def get_subnets(self, vpc_id: str) -> list[dict]:
        response = self.subnet_client.describe_subnets(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
        )
        return [
            {
                "subnet_id": subnet["SubnetId"],
                "cidr": subnet.get("CidrBlock"),
                "availability_zone": subnet.get("AvailabilityZone"),
                "is_public": bool(subnet.get("MapPublicIpOnLaunch", False)),
            }
            for subnet in response.get("Subnets", [])
        ]

    def delete_subnets(self, vpc_id: str) -> list[str]:
        subnets = self.get_subnets(vpc_id)
        if not subnets:
            return []

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            return list(pool.map(self._delete_subnet, subnets))

    def _delete_subnet(self, subnet: dict) -> str:
        self.subnet_client.delete_subnet(SubnetId=subnet["subnet_id"])
        self.logger.info("Deleted subnet %s", subnet["subnet_id"])
        return subnet["subnet_id"]
