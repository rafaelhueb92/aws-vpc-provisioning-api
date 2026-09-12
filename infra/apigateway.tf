resource "aws_apigatewayv2_api" "this" {
  name        = local.name_prefix
  description = "Serverless VPC provisioning API (${var.environment})"

  protocol_type = "HTTP"

  body = templatefile(local.openapi_spec_path, {
    lambda_invoke_uri = local.lambda_invoke_uri
    cognito_issuer    = local.cognito_issuer
    cognito_client_id = local.cognito_client_id
  })
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "apigateway.amazonaws.com"

  source_arn = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}
