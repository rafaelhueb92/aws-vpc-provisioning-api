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
        subnet_nets = [ipaddress.ip_network(s.cidr) for s in self.subnets]

        for s_net in subnet_nets:
            if not s_net.subnet_of(vpc_net):
                raise ValueError(f"Subnet {s_net} is not within VPC CIDR {vpc_net}")

        for i, net1 in enumerate(subnet_nets):
            for net2 in subnet_nets[i + 1:]:
                if net1.overlaps(net2):
                    raise ValueError(f"Subnet CIDR conflict between {net1} and {net2}")
        return self