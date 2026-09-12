import ipaddress

from pydantic import BaseModel, Field, model_validator


class SubnetDefinition(BaseModel):
    name: str
    cidr: str
    availability_zone: str
    is_public: bool = False

class CreateVpcRequest(BaseModel):
    name: str
    cidr: str
    subnets: list[SubnetDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_network(self) -> "CreateVpcRequest":
        vpc_net = ipaddress.ip_network(self.cidr)

        seen = []
        for subnet in self.subnets:
            net = ipaddress.ip_network(subnet.cidr)
            if not net.subnet_of(vpc_net):
                raise ValueError(f"Subnet {net} is not within VPC CIDR {vpc_net}")
            conflict = next((other for other in seen if net.overlaps(other)), None)
            if conflict:
                raise ValueError(f"Subnet CIDR conflict between {net} and {conflict}")
            seen.append(net)
        return self
