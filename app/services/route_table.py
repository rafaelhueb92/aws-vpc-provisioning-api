from concurrent.futures import ThreadPoolExecutor
from typing import Any


class RouteTable:

    def __init__(self, client, logger):
        self.ec2_client = client
        self.logger = logger

    def create_route_table(self, vpc_id: str, name: str, igw_id: str | None = None) -> str:
        response = self.ec2_client.create_route_table(VpcId=vpc_id)
        route_table_id = response["RouteTable"]["RouteTableId"]

        self.ec2_client.create_tags(
            Resources=[route_table_id], Tags=[{"Key": "Name", "Value": name}]
        )
        self.logger.info("Created route table %s (%s)", name, route_table_id)

        if igw_id:
            self.ec2_client.create_route(
                RouteTableId=route_table_id,
                DestinationCidrBlock="0.0.0.0/0",
                GatewayId=igw_id,
            )
            self.logger.info("Route table %s routes 0.0.0.0/0 to %s", route_table_id, igw_id)

        return route_table_id

    def associate_subnets(self, route_table_id: str, subnet_ids: list[str]) -> list[str]:
        subnet_ids = list(subnet_ids or [])
        if not subnet_ids:
            return []

        with ThreadPoolExecutor(max_workers=len(subnet_ids)) as pool:
            return list(
                pool.map(
                    lambda subnet_id: self._associate_subnet(route_table_id, subnet_id),
                    subnet_ids,
                )
            )

    def _associate_subnet(self, route_table_id: str, subnet_id: str) -> str:
        response = self.ec2_client.associate_route_table(
            RouteTableId=route_table_id, SubnetId=subnet_id
        )
        self.logger.info("Associated subnet %s with route table %s", subnet_id, route_table_id)
        return response["AssociationId"]

    def create_for_subnets(
        self,
        vpc_id: str,
        subnets: list[Any],
        name: str,
        igw_id: str | None = None,
    ) -> dict[str, str]:
        
        public_subnets = [subnet["subnet_id"] for subnet in subnets if subnet.get("is_public")]
        private_subnets = [
            subnet["subnet_id"] for subnet in subnets if not subnet.get("is_public")
        ]

        created = {}

        if public_subnets:
            public_route_table = self.create_route_table(
                vpc_id, f"{name}-public-rt", igw_id=igw_id
            )
            self.associate_subnets(public_route_table, public_subnets)
            self.logger.info("Public subnets %s use route table %s", public_subnets, public_route_table)
            created["public"] = public_route_table

        if private_subnets:
            private_route_table = self.create_route_table(vpc_id, f"{name}-private-rt")
            self.associate_subnets(private_route_table, private_subnets)
            self.logger.info(
                "Private subnets %s use route table %s", private_subnets, private_route_table
            )
            created["private"] = private_route_table

        return created

    def get_route_tables(self, vpc_id: str) -> list[dict]:
        response = self.ec2_client.describe_route_tables(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
        )
        route_tables = []
        for table in response.get("RouteTables", []):
            associations = table.get("Associations") or []
            route_tables.append(
                {
                    "route_table_id": table["RouteTableId"],
                    "is_main": any(association.get("Main") for association in associations),
                    "association_ids": [
                        association["RouteTableAssociationId"]
                        for association in associations
                        if not association.get("Main")
                    ],
                }
            )
        return route_tables

    def delete_route_tables(self, vpc_id: str) -> list[str]:
        route_tables = [
            table for table in self.get_route_tables(vpc_id) if not table["is_main"]
        ]
        if not route_tables:
            return []

        with ThreadPoolExecutor(max_workers=len(route_tables)) as pool:
            return list(pool.map(self._delete_route_table, route_tables))

    def _delete_route_table(self, table: dict) -> str:
        for association_id in table["association_ids"]:
            self.ec2_client.disassociate_route_table(AssociationId=association_id)

        self.ec2_client.delete_route_table(RouteTableId=table["route_table_id"])
        self.logger.info("Deleted route table %s", table["route_table_id"])
        return table["route_table_id"]
