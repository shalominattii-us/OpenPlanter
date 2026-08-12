#!/usr/bin/env bash
set -euo pipefail

required=(
  AWS_REGION
  STACK_NAME
  ECR_REPOSITORY
  CLUSTER_ARN
  VPC_ID
  PRIVATE_SUBNET_IDS
  EFS_SECURITY_GROUP_ID
  SAM_GOV_SECRET_ARN
)

for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required deployment value: $name" >&2
    exit 2
  fi
done

aws sts get-caller-identity >/dev/null
aws ecs describe-clusters --clusters "$CLUSTER_ARN" \
  --query 'clusters[0].status' --output text | grep -qx ACTIVE
aws ec2 describe-vpcs --vpc-ids "$VPC_ID" >/dev/null
aws ec2 describe-security-groups --group-ids "$EFS_SECURITY_GROUP_ID" >/dev/null
aws secretsmanager describe-secret --secret-id "$SAM_GOV_SECRET_ARN" >/dev/null

IFS=',' read -r -a subnets <<< "$PRIVATE_SUBNET_IDS"
if (( ${#subnets[@]} < 1 )); then
  echo "At least one private subnet is required" >&2
  exit 2
fi

for subnet in "${subnets[@]}"; do
  subnet="${subnet//[[:space:]]/}"
  aws ec2 describe-subnets --subnet-ids "$subnet" \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'Subnets[0].SubnetId' --output text | grep -qx "$subnet"
done

echo "AWS deployment inputs validated."
