# ☁️ AWS VPC Provisioning API

[![Deploy](https://github.com/rafaelhueb92/aws-vpc-provisioning-api/actions/workflows/deploy.yml/badge.svg)](https://github.com/rafaelhueb92/aws-vpc-provisioning-api/actions/workflows/deploy.yml)
[![Python](https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Terraform](https://img.shields.io/badge/terraform-%3E%3D%201.5-7B42BC?logo=terraform&logoColor=white)](https://developer.hashicorp.com/terraform)
[![AWS](https://img.shields.io/badge/AWS-Lambda%20%7C%20API%20Gateway%20%7C%20DynamoDB%20%7C%20Cognito-FF9900?logo=amazonwebservices&logoColor=white)](https://aws.amazon.com/)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)
[![Tests](https://img.shields.io/badge/tests-34%20passing-brightgreen?logo=pytest&logoColor=white)](#-tests)

Serverless API that provisions AWS networking on demand: create a VPC with its subnets, get it
back, delete it. Infrastructure is defined with Terraform, and every request is authenticated
with a Cognito JWT.

## 🏗️ Architecture

![Architecture](images/architecture.jpeg)

A request hits **API Gateway** with a Bearer JWT, which **Cognito** validates. The **Lambda**
then either talks to **EC2** to provision the networking resources, or reads and writes the VPC
records in **DynamoDB**.

> The diagram shows the target AWS topology. Today the API provisions the **VPC** and its
> **subnets** (with public IP mapping on the public ones). The service layer can also attach an
> **internet gateway** (`vpc.create_igw_if_public_subnet(...)`) and `DELETE` cleans one up if it
> exists, but the `POST` flow does not call it yet. Route tables are not created yet.

## 🚏 Routes

| Method   | Path             | Auth   | What it does                                                                       |
| -------- | ---------------- | ------ | ---------------------------------------------------------------------------------- |
| `POST`   | `/vpcs`          | JWT    | Creates the VPC and its subnets, then stores the records                           |
| `GET`    | `/vpcs/{vpc_id}` | JWT    | Returns the stored VPC                                                             |
| `DELETE` | `/vpcs/{vpc_id}` | JWT    | Deletes the subnets, any attached internet gateway, the VPC and the stored records |
| `GET`    | `/health`        | public | Liveness probe                                                                     |

## 📁 Project layout

```
app/                 Lambda application (Python 3.12)
  handler.py         entrypoint: handler.lambda_handler
  config/            settings read from environment variables
  models/            request validation (pydantic)
  services/          vpc.py · subnet.py · storage.py  (boto3)
  test/              pytest suite + fixtures
infra/               Terraform: Lambda, API Gateway, DynamoDB, Cognito, OIDC
  openapi/api.yaml   OpenAPI 3.0 spec imported by API Gateway
.github/workflows/   CI/CD: ruff + tests, then terraform plan/apply
```

## 🚀 Deploy

**Prerequisites:** Terraform >= 1.5, AWS credentials with admin rights (for the first apply),
and an S3 bucket for the remote state.

```bash
cd infra

terraform init \
  -backend-config="bucket=<your-tf-state-bucket>" \
  -backend-config="key=vpc-provisioning-api/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="dynamodb_table=<your-lock-table>" \
  -backend-config="encrypt=true"

terraform apply
```

Then read the outputs:

```bash
terraform output api_endpoint          # https://xxxxxxxx.execute-api.us-east-1.amazonaws.com
terraform output cognito_user_pool_id
terraform output cognito_app_client_id
```

Useful variables: `aws_region` (default `us-east-1`), `environment` (default `dev`),
`dynamodb_table_name` (default `vpc-provisioning-records`).

> The first apply must be run locally with admin credentials: it creates the GitHub OIDC
> provider and the deploy role that CI assumes afterwards.

## 🔑 Get a token

```bash
POOL_ID=$(terraform -chdir=infra output -raw cognito_user_pool_id)
CLIENT_ID=$(terraform -chdir=infra output -raw cognito_app_client_id)

# create a user and set a permanent password
aws cognito-idp admin-create-user --user-pool-id "$POOL_ID" --username you@example.com
aws cognito-idp admin-set-user-password --user-pool-id "$POOL_ID" \
  --username you@example.com --password 'Passw0rd!' --permanent

# get the token
aws cognito-idp initiate-auth --auth-flow USER_PASSWORD_AUTH --client-id "$CLIENT_ID" \
  --auth-parameters USERNAME=you@example.com,PASSWORD='Passw0rd!' \
  --query 'AuthenticationResult.IdToken' --output text
```

## 🧪 Use the API

```bash
API=$(terraform -chdir=infra output -raw api_endpoint)
TOKEN="<the IdToken from above>"

# health check (no token needed)
curl "$API/health"

# create a VPC with a public and a private subnet
curl -X POST "$API/vpcs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "name": "my-vpc",
        "cidr": "10.0.0.0/16",
        "subnets": [
          {"name": "public-1",  "cidr": "10.0.1.0/24", "availability_zone": "us-east-1a", "is_public": true},
          {"name": "private-1", "cidr": "10.0.2.0/24", "availability_zone": "us-east-1b", "is_public": false}
        ]
      }'
# -> {"message": "VPC vpc-0123... created with success.", "vpc_id": "vpc-0123...", "subnet_ids": ["subnet-...", "subnet-..."]}

# get it back
curl "$API/vpcs/vpc-0123..." -H "Authorization: Bearer $TOKEN"

# delete it (removes the subnets and any attached internet gateway)
curl -X DELETE "$API/vpcs/vpc-0123..." -H "Authorization: Bearer $TOKEN"
```

The subnets are validated before any AWS call: each CIDR must sit inside the VPC CIDR, and
subnet CIDRs cannot overlap. Bad input returns `400`; an unknown VPC returns `404`.

## 💻 Local development

```bash
cd app
python3.12 -m venv venv && source venv/bin/activate

pip install -r requirements.txt          # runtime deps
pip install -r test/requirements.txt     # pytest, moto, ruff

# run the API: keeps credentials local, everything else comes from the env
DDB_TABLE_NAME=vpc-provisioning-records AWS_REGION=us-east-1 \
  python -c "import json, handler; print(handler.lambda_handler({'httpMethod':'GET','path':'/health'}, {}))"
```

### ⚙️ Environment variables

| Variable                                                                                             | Required | Default                   | Purpose                                              |
| ---------------------------------------------------------------------------------------------------- | -------- | ------------------------- | ---------------------------------------------------- |
| `DDB_TABLE_NAME`                                                                                     | yes      | —                         | DynamoDB table for the VPC records                   |
| `AWS_REGION`                                                                                         | no       | `us-east-1`               | Region of the clients (Lambda sets it automatically) |
| `LOG_LEVEL`                                                                                          | no       | `INFO`                    | Logger verbosity                                     |
| `AWS_ENDPOINT_URL`                                                                                   | no       | —                         | Point boto3 at LocalStack or moto instead of AWS     |
| `VPC_WAITER_DELAY` · `VPC_WAITER_MAX_ATTEMPTS` · `VPC_WAITER_ENABLED`                                | no       | `5` · `12` · `true`       | EC2 waiter tuning for VPC creation                   |
| `SUBNET_WAITER_DELAY` · `SUBNET_WAITER_MAX_ATTEMPTS` · `SUBNET_MAP_PUBLIC_IP` · `SUBNET_MAX_WORKERS` | no       | `5` · `12` · `true` · `5` | Subnet waiter, public IP and thread pool tuning      |

## ✅ Tests

```bash
cd app
python -m pytest        # 34 tests: 25 unit (fakes) + 9 lifecycle (moto)
```

The suite runs without AWS credentials: `app/test/conftest.py` injects in-memory collaborators,
and `moto` provides a fake EC2 and DynamoDB for the lifecycle tests.

```bash
ruff check .            # same command CI runs (see .github/workflows/deploy.yml)
ruff check --fix .      # apply the safe fixes
```

## 🤖 CI/CD

`.github/workflows/deploy.yml` runs on every PR and push:

1. **lint and unit tests** — `ruff check` + `pytest`, no AWS credentials needed
2. **terraform** — `plan` on pull requests, `apply -auto-approve` on push to `main`

AWS access uses GitHub OIDC, so no long-lived keys are stored in the repository.

**Repository secrets required:** `AWS_DEPLOY_ROLE_ARN` (role from `infra/oidc.tf`),
`TF_STATE_BUCKET`, `TF_STATE_LOCK_TABLE`. Optional variable: `TF_STATE_KEY`.
