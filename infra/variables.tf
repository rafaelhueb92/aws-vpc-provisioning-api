variable "aws_region" {
  description = "AWS region where the API and its resources are deployed."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name, used as the prefix of the Lambda function, IAM role and API Gateway names."
  type        = string
  default     = "vpc-provisioning-api"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod). Appended to resource names and used as a tag."
  type        = string
  default     = "dev"
}

variable "lambda_runtime" {
  description = <<-EOT
    Python runtime for the Lambda function.

    app/ has no pyproject.toml, setup.cfg or python version constraint: the only
    dependency manifest is app/requirements.txt, which pins no interpreter
    version. The default therefore follows the fallback python3.12, which
    satisfies every pin in that file (boto3 1.43.93, pydantic 2.13.5 /
    pydantic_core 2.46.5 all support Python >= 3.9).
  EOT
  type        = string
  default     = "python3.12"
}

variable "lambda_memory_size" {
  description = "Memory (MB) allocated to the Lambda function."
  type        = number
  default     = 256
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds. Subnet creation runs in a thread pool, so keep this above the sum of the EC2 waiter retries."
  type        = number
  default     = 30
}

variable "log_level" {
  description = "Value of the LOG_LEVEL environment variable read by app/config/settings.py (controls the Lambda logger verbosity)."
  type        = string
  default     = "INFO"
}

variable "dynamodb_table_name" {
  description = "Name of the DynamoDB table used to store VPC records. The Lambda receives it through the DDB_TABLE_NAME environment variable."
  type        = string
  default     = "vpc-provisioning-records"
}

variable "cognito_user_pool_name" {
  description = "Name of the Cognito User Pool that issues the JWTs accepted by the API Gateway authorizer."
  type        = string
  default     = "vpc-api-user-pool"
}

variable "github_repository" {
  description = "GitHub repository allowed to assume the deployment role through OIDC, in owner/repo form. Override this with your own repository."
  type        = string
  default     = "your-org/your-repo-name"
}

variable "github_branch" {
  description = "Branch allowed to assume the deployment role for pushes (pull request plans are allowed separately through the pull_request subject)."
  type        = string
  default     = "main"
}

variable "tags" {
  description = "Tags applied to every taggable resource through the provider default_tags block."
  type        = map(string)
  default = {
    ManagedBy = "terraform"
    Project   = "vpc-provisioning-api"
  }
}
