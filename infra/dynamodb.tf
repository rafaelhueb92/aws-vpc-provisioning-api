resource "aws_dynamodb_table" "vpcs" {
  name         = var.dynamodb_table_name
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "vpc_id"
  range_key = "resource_key"

  attribute {
    name = "vpc_id"
    type = "S"
  }

  attribute {
    name = "resource_key"
    type = "S"
  }
}
