import boto3
import json
import uuid
from models.vpc import CreateVpcRequest
from services.vpc import VPC

client = boto3.client('ec2',region_name='us-east-1')

vpc = VPC(client)

def get_vpc(event, context):
    pass

def delete_vpc(event, context):
    pass

def lambda_handler(event:dict, context:dict):
    method = event.get('httpMethod')
    path = event.get('path')
    vpc_request = CreateVpcRequest(**json.loads(event.get('body', {})))

    print("VPC Request", vpc_request)

    if path == '/vpcs':

        if method == 'GET':
            return get_vpc(event, context)
        elif method == 'POST':
            name = vpc_request.name
            cidr = vpc_request.cidr
            return vpc.create_vpc(name,cidr)
        elif method == 'DELETE':
            return delete_vpc(event, context)
        
    return {
        'statusCode': 400,
        'body': json.dumps({'message': 'Unsupported method or path'})
    }

if __name__ == '__main__':
    event = {
        'httpMethod':'POST',
        'path': '/vpcs',
        'body': json.dumps({
            'name': 'my-vpc',
            'cidr': '10.0.0.0/16',
            'subnets': [
                {
                    'name': 'public-subnet-1',
                    'cidr': '10.0.1.0/24',
                    'availability_zone': 'us-east-1a',
                    'is_public': True
                },
                {
                    'name': 'private-subnet-1',
                    'cidr': '10.0.2.0/24',
                    'availability_zone': 'us-east-1b',
                    'is_public': False
                }
            ]
        })
    }

    
    lambda_handler(event,{})