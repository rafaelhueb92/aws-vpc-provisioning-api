```bash
    aws ec2 describe-vpcs --query "Vpcs[*].[VpcId, CidrBlock, State, Tags[?Key=='Name'].Value | [0]]" --output table
```
