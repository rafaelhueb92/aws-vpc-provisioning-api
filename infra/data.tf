data "aws_caller_identity" "current" {}

resource "local_file" "placeholder" {
  count    = fileexists("${path.module}/build/handler.py") ? 0 : 1
  filename = "${path.module}/build/.keep"
  content  = ""
}

data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/build"
  output_path = "${path.module}/build/lambda.zip"

  excludes = [
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    "tests",
    "test",
    "pytest.ini",
    ".ruff_cache",
    ".abacusai"
  ]

  depends_on = [local_file.placeholder]

}
