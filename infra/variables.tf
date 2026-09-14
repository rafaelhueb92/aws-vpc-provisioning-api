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
  description = "Python runtime for the Lambda function."
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

variable "tags" {
  description = "Tags applied to every taggable resource through the provider default_tags block."
  type        = map(string)
  default = {
    ManagedBy = "terraform"
    Project   = "vpc-provisioning-api"
  }
}
