import json
import logging

import boto3
from botocore.exceptions import ClientError
from pydantic import ValidationError

from config import get_settings
from models.vpc import CreateVpcRequest
from services.route_table import RouteTable
from services.storage import Storage
from services.subnet import Subnet
from services.vpc import VPC

settings = get_settings()
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

client = boto3.client(
    'ec2',
    region_name=settings.aws_region,
    endpoint_url=settings.aws_endpoint_url,
)

client_dynamo = boto3.resource(
    "dynamodb",
    region_name=settings.aws_region,
    endpoint_url=settings.aws_endpoint_url
)

vpc = VPC(client,logger)
subnet = Subnet(client,logger)
route_table = RouteTable(client,logger)
storage = Storage(client_dynamo,settings.vpc_table)

def _response(status_code: int, payload) -> dict:
    return {'statusCode': status_code, 'body': json.dumps(payload, default=str)}

def lambda_handler(event:dict, context:dict):
    try:
        return _route(event)
    except (ValidationError, ValueError) as error:
        return _response(400, {'message': str(error)})
    except ClientError as error:
        code = error.response['Error']['Code']
        return _response(404 if code.endswith('NotFound') else 502, {'message': code})

def _route(event:dict) -> dict:
    method = event.get('httpMethod')
    path = event.get('path')
    path_parameters = event.get('pathParameters') or {}

    if (path or '').startswith('/vpcs'):

        if method == 'POST':

            vpc_request = CreateVpcRequest(**json.loads(event.get('body') or '{}'))

            logger.info("Requesting VPC Creation %s",vpc_request)

            vpc_id = vpc.create_vpc(vpc_request.name,vpc_request.cidr)

            subnets = subnet.create_subnets(
                vpc_id,[definition.model_dump() for definition in vpc_request.subnets]
            )

            igw_id = vpc.create_igw_if_public_subnet(
                vpc_id,subnets,name=f'{vpc_request.name}-igw'
            )
            route_table.create_for_subnets(vpc_id,subnets,vpc_request.name,igw_id=igw_id)

            records = [(vpc_id, {'name': vpc_request.name, 'cidr': vpc_request.cidr})]
            records += [(created['subnet_id'], created) for created in subnets]
            storage.insert_many(vpc_id, records)

            return _response(200, {
                'message': f'VPC {vpc_id} created with success.',
                'vpc_id': vpc_id,
                'subnet_ids': [created['subnet_id'] for created in subnets]
            })
        else:
             vpc_id = path_parameters.get('vpc_id')

             if method not in ('GET', 'DELETE'):
                 return _response(400, {'message': 'Unsupported method or path'})

             if not vpc_id:
                 return _response(400, {'message': 'vpc_id path parameter is required'})

             if method == 'GET':
                founded_vpc = storage.get_by_id(vpc_id)
                if not founded_vpc:
                    return _response(404, {'message': f'VPC {vpc_id} not found'})
                return _response(200, founded_vpc)
             elif method == 'DELETE':
                  route_table.delete_route_tables(vpc_id)
                  subnet.delete_subnets(vpc_id)
                  vpc.delete_vpc(vpc_id)
                  storage.delete_many(
                      vpc_id,[stored['resource_key'] for stored in storage.list_all(vpc_id)]
                  )
                  return _response(200, {'message': f'VPC {vpc_id} deleted.'})

    elif (path or '').startswith('/health') and method == 'GET':
        return _response(200, {'health': True})

    return _response(400, {'message': 'Unsupported method or path'})
