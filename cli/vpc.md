# VPC Useful Commands

Check the vpc's by aws cli.

```bash
    aws ec2 describe-vpcs --query "Vpcs[*].[VpcId, CidrBlock, State, Tags[?Key=='Name'].Value | [0]]" --output table
```
