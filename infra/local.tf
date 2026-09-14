locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = merge(
    {
      ManagedBy   = "terraform"
      Project     = var.project_name
      Environment = var.environment
    },
    var.tags,
  )

  app_dir          = "${path.module}/../app"
  lambda_build_dir = "${path.module}/build"
  lambda_zip_path  = "${path.module}/build/lambda.zip"
  openapi_dir      = "${path.module}/openapi"

  lambda_python_version = trimprefix(var.lambda_runtime, "python")

  app_source_files = concat(
    ["handler.py"],
    [for f in fileset("${local.app_dir}/config", "**") : "config/${f}" if endswith(f, ".py") && !strcontains(f, "__pycache__")],
    [for f in fileset("${local.app_dir}/models", "**") : "models/${f}" if endswith(f, ".py") && !strcontains(f, "__pycache__")],
    [for f in fileset("${local.app_dir}/services", "**") : "services/${f}" if endswith(f, ".py") && !strcontains(f, "__pycache__")],
  )

  app_source_hash = sha256(join("", [for f in local.app_source_files : filemd5("${local.app_dir}/${f}")]))

  lambda_invoke_uri = "arn:aws:apigateway:${var.aws_region}:lambda:path/2015-03-31/functions/${aws_lambda_function.this.arn}/invocations"

  cognito_issuer    = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.this.id}"
  cognito_client_id = aws_cognito_user_pool_client.this.id
}

locals {
  openapi_template_vars = {
    lambda_invoke_uri = local.lambda_invoke_uri
    cognito_issuer    = local.cognito_issuer
    cognito_client_id = local.cognito_client_id
  }

  openapi_fragment_dirs = {
    paths            = "${local.openapi_dir}/paths"
    schemas          = "${local.openapi_dir}/components/schemas"
    security_schemes = "${local.openapi_dir}/components/securitySchemes"
  }

  openapi_fragments = {
    for name, dir in local.openapi_fragment_dirs :
    name => merge([
      for file in fileset(dir, "*.yaml") :
      yamldecode(templatefile("${dir}/${file}", local.openapi_template_vars))
    ]...)
  }

  openapi_spec = merge(
    yamldecode(templatefile("${local.openapi_dir}/api.yaml", local.openapi_template_vars)),
    {
      paths = local.openapi_fragments.paths
      components = {
        schemas         = local.openapi_fragments.schemas
        securitySchemes = local.openapi_fragments.security_schemes
      }
    },
  )
}
