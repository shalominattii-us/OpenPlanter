#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?AWS_REGION is required}"
: "${STACK_NAME:?STACK_NAME is required}"
: "${CONTAINER_IMAGE:?CONTAINER_IMAGE is required}"
: "${CLUSTER_ARN:?CLUSTER_ARN is required}"
: "${VPC_ID:?VPC_ID is required}"
: "${PRIVATE_SUBNET_IDS:?PRIVATE_SUBNET_IDS is required}"
: "${EFS_SECURITY_GROUP_ID:?EFS_SECURITY_GROUP_ID is required}"
: "${SAM_GOV_SECRET_ARN:?SAM_GOV_SECRET_ARN is required}"
: "${SCHEDULE_EXPRESSION:?SCHEDULE_EXPRESSION is required}"
: "${SCHEDULE_TIMEZONE:?SCHEDULE_TIMEZONE is required}"

notification_email="${NOTIFICATION_EMAIL:-}"

echo "Deploying stack $STACK_NAME in $AWS_REGION"
aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME" \
  --template-file infra/aws/opportunity-intake-scheduled-task.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    ClusterArn="$CLUSTER_ARN" \
    ContainerImage="$CONTAINER_IMAGE" \
    VpcId="$VPC_ID" \
    PrivateSubnetIds="$PRIVATE_SUBNET_IDS" \
    EfsSecurityGroupId="$EFS_SECURITY_GROUP_ID" \
    SamGovApiKeySecretArn="$SAM_GOV_SECRET_ARN" \
    ScheduleExpression="$SCHEDULE_EXPRESSION" \
    ScheduleTimezone="$SCHEDULE_TIMEZONE" \
    NotificationEmail="$notification_email"

aws cloudformation describe-stacks \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs' \
  --output table
