resource "aws_apigatewayv2_api" "this" {
  name        = local.name_prefix
  description = "Serverless VPC provisioning API (${var.environment})"

  protocol_type = "HTTP"

  body = jsonencode(local.openapi_spec)
}

resource "aws_apigatewayv2_stage" "default" {
  api_id = aws_apigatewayv2_api.this.id
  name   = "$default"

  auto_deploy = true
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "apigateway.amazonaws.com"

  source_arn = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}
