output "api_endpoint" {
  description = "Base invoke URL of the HTTP API ($default stage). Append the route, e.g. /vpcs."
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "cognito_user_pool_id" {
  description = "ID of the Cognito User Pool that issues the JWTs accepted by the API."
  value       = aws_cognito_user_pool.this.id
}

output "cognito_app_client_id" {
  description = "App client ID, also used as the JWT audience of the API Gateway authorizer."
  value       = aws_cognito_user_pool_client.this.id
}

output "lambda_function_arn" {
  description = "ARN of the provisioning Lambda function."
  value       = aws_lambda_function.this.arn
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB table holding the VPC records, passed to the Lambda as DDB_TABLE_NAME."
  value       = aws_dynamodb_table.vpcs.name
}
