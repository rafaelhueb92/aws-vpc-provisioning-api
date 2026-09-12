from concurrent.futures import ThreadPoolExecutor

class Subnet:
    def __init__(self,client):
        self.subnet_client = client

    def create_subnets(self,subnet_props):
        pass

    def get_subnets(self,vpc_id):
        pass

    def delete_subnets(self,vpc_id):
        pass

    # Use threadpool to create the subnets