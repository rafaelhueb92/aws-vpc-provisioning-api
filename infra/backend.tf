# Bucket, key, region and lock table are not stored here: they are injected at
# init time from the GitHub Actions workflow (secret TF_STATE_BUCKET / TF_STATE_LOCK_TABLE):
#   terraform init -backend-config="bucket=..." -backend-config="key=..." \
#                  -backend-config="region=..." -backend-config="dynamodb_table=..."
terraform {
  backend "s3" {}
}
