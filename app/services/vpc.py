from typing import Any, Optional

from config import get_settings


class VPC:

    def __init__(self, client, logger, waiter_config: Optional[dict] = None):
        settings = get_settings()
        self.vpc_client = client
        self.waiter_config = waiter_config or {
            "Delay": settings.vpc_waiter_delay,
            "MaxAttempts": settings.vpc_waiter_max_attempts,
        }
        self.logger = logger

    def _wait_until_available(self, vpc_id: str) -> None:
        self.logger.info("Waiting for VPC %s to become available", vpc_id)
        waiter = self.vpc_client.get_waiter("vpc_available")
        waiter.wait(VpcIds=[vpc_id], WaiterConfig=self.waiter_config)
        self.logger.info("VPC %s is available", vpc_id)

    def _tag_resources(self, resource_ids: list[str], tags: Optional[dict] = None) -> None:
        if not tags:
            return

        resource_ids = list(resource_ids)
        if not resource_ids:
            return

        self.vpc_client.create_tags(
            Resources=resource_ids,
            Tags=[{"Key": key, "Value": str(value)} for key, value in tags.items()],
        )
        self.logger.info("Tagged %s with %s", resource_ids, tags)

    @staticmethod
    def _is_public(subnet: Any) -> bool:
        if isinstance(subnet, dict):
            return bool(subnet.get("is_public", False))
        return bool(getattr(subnet, "is_public", False))

    def create_vpc(
        self,
        name: str,
        cidr: str,
        tags: Optional[dict] = None,
        wait: Optional[bool] = None,
    ) -> str:

        self.logger.info("Creating vpc name=%s cidr=%s", name, cidr)

        response = self.vpc_client.create_vpc(CidrBlock=cidr)
        vpc_id = response["Vpc"]["VpcId"]
        self.logger.info("Created VPC with ID: %s", vpc_id)

        should_wait = get_settings().vpc_waiter_enabled if wait is None else wait
        if should_wait:
            self._wait_until_available(vpc_id)

        resource_tags = {"Name": name}
        resource_tags.update(tags or {})
        self._tag_resources([vpc_id], resource_tags)

        return vpc_id

    def delete_vpc(self, vpc_id: str) -> None:
        igw_id = self.get_internet_gateway(vpc_id)
        if igw_id:
            self.vpc_client.detach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
            self.vpc_client.delete_internet_gateway(InternetGatewayId=igw_id)
            self.logger.info("Deleted internet gateway %s", igw_id)

        self.vpc_client.delete_vpc(VpcId=vpc_id)
        self.logger.info("Deleted VPC %s", vpc_id)

    def has_public_subnet(self, subnets: Optional[list[Any]]) -> bool:
        return any(self._is_public(subnet) for subnet in subnets or [])

    def get_internet_gateway(self, vpc_id: str) -> Optional[str]:
        response = self.vpc_client.describe_internet_gateways(
            Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}]
        )
        gateways = response.get("InternetGateways", [])
        return gateways[0]["InternetGatewayId"] if gateways else None

    def create_internet_gateway(self, vpc_id: str, name: Optional[str] = None) -> str:
        existing = self.get_internet_gateway(vpc_id)
        if existing:
            self.logger.info("VPC %s already has internet gateway %s", vpc_id, existing)
            return existing

        response = self.vpc_client.create_internet_gateway()
        igw_id = response["InternetGateway"]["InternetGatewayId"]

        self.vpc_client.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
        self.logger.info("Attached internet gateway %s to VPC %s", igw_id, vpc_id)

        self._tag_resources([igw_id], {"Name": name or f"{vpc_id}-igw"})

        return igw_id

    def create_igw_if_public_subnet(
        self,
        vpc_id: str,
        subnets: Optional[list[Any]],
        name: Optional[str] = None,
    ) -> Optional[str]:
        if not self.has_public_subnet(subnets):
            self.logger.info("No public subnet for VPC %s, skipping internet gateway", vpc_id)
            return None

        return self.create_internet_gateway(vpc_id, name=name)
