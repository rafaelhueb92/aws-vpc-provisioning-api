resource "null_resource" "build_lambda" {
  triggers = {
    requirements = filemd5("${local.app_dir}/requirements.txt")
    source       = local.app_source_hash
    runtime      = var.lambda_runtime
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -euo pipefail
      rm -rf "${local.lambda_build_dir}"
      mkdir -p "${local.lambda_build_dir}"

      python3 -m pip install --quiet --target "${local.lambda_build_dir}" \
        --platform manylinux2014_x86_64 --implementation cp \
        --python-version ${local.lambda_python_version} --only-binary=:all: \
        -r "${local.app_dir}/requirements.txt"

      rsync -a \
        --exclude 'venv' --exclude 'test' --exclude '.abacusai' \
        --exclude '__pycache__' --exclude '*.pyc' \
        "${local.app_dir}/" "${local.lambda_build_dir}/"

      (
        cd "${local.lambda_build_dir}"
        rm -f lambda.zip
        zip -q -r lambda.zip . -x '*__pycache__*' '*.pyc'
      )
    EOT
  }
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    sid     = "LambdaAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name_prefix}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${local.name_prefix}:*",
    ]
  }

  statement {
    sid    = "VpcAndSubnetLifecycle"
    effect = "Allow"

    actions = [
      "ec2:CreateVpc",
      "ec2:DeleteVpc",
      "ec2:DescribeVpcs",
      "ec2:CreateTags",
      "ec2:CreateSubnet",
      "ec2:DeleteSubnet",
      "ec2:DescribeSubnets",
      "ec2:ModifySubnetAttribute",
      "ec2:CreateInternetGateway",
      "ec2:AttachInternetGateway",
      "ec2:DetachInternetGateway",
      "ec2:DeleteInternetGateway",
      "ec2:DescribeInternetGateways",
    ]

    resources = ["*"]
  }

  statement {
    sid    = "VpcRecords"
    effect = "Allow"

    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:DeleteItem",
    ]

    resources = [aws_dynamodb_table.vpcs.arn]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.name_prefix}-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}


resource "aws_lambda_function" "this" {
  function_name = local.name_prefix
  description   = "Provision VPCs, subnets and internet gateways on demand"
  role          = aws_iam_role.lambda.arn

  runtime = var.lambda_runtime
  handler = "handler.lambda_handler"

  filename = local.lambda_zip_path

  source_code_hash = fileexists(local.lambda_zip_path) ? filebase64sha256(local.lambda_zip_path) : null

  memory_size = var.lambda_memory_size
  timeout     = var.lambda_timeout

  architectures = ["x86_64"]

  environment {
    variables = {
      DDB_TABLE_NAME = aws_dynamodb_table.vpcs.name
      LOG_LEVEL      = var.log_level
    }
  }

  depends_on = [
    null_resource.build_lambda,
    aws_iam_role_policy.lambda,
  ]
}
