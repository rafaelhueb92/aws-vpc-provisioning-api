POOL_ID=$1
CLIENT_ID=$2
USERNAME=$3
PASSWORD=$4

aws cognito-idp admin-create-user --user-pool-id "$POOL_ID" --username $USERNAME
aws cognito-idp admin-set-user-password --user-pool-id "$POOL_ID" \
  --username you@example.com --password $PASSWORD --permanent
