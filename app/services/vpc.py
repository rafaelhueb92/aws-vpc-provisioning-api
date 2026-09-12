class VPC:

    def __init__(self,client):
        self.vpc_client = client

    def create_vpc(self,name:str,cidr:str):

        print("Creating vpc", name,cidr)

        response = self.vpc_client.create_vpc(CidrBlock=cidr)
        vpc_id = response["Vpc"]["VpcId"]
        print(f"Created VPC with ID: {vpc_id}")

        print("Waiting for VPC to become available...")
        waiter = self.vpc_client.get_waiter("vpc_available")
        waiter.wait(VpcIds=[vpc_id], WaiterConfig={"Delay": 5, "MaxAttempts": 12})

        print("VPC is now available.")

        self.vpc_client.create_tags(
            Resources=[vpc_id], Tags=[{"Key": "Name", "Value": name}]
        )
        
        print(f"Successfully added tags to VPC: {vpc_id}")

        return vpc_id