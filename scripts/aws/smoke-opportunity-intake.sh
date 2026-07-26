#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?AWS_REGION is required}"
: "${STACK_NAME:?STACK_NAME is required}"
: "${CLUSTER_ARN:?CLUSTER_ARN is required}"
: "${PRIVATE_SUBNET_IDS:?PRIVATE_SUBNET_IDS is required}"

stack_output() {
  aws cloudformation describe-stacks \
    --region "$AWS_REGION" \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" \
    --output text
}

task_definition_arn="$(stack_output TaskDefinitionArn)"
task_security_group_id="$(stack_output TaskSecurityGroupId)"

if [[ -z "$task_definition_arn" || "$task_definition_arn" == "None" ]]; then
  echo "TaskDefinitionArn stack output is unavailable" >&2
  exit 1
fi
if [[ -z "$task_security_group_id" || "$task_security_group_id" == "None" ]]; then
  echo "TaskSecurityGroupId stack output is unavailable" >&2
  exit 1
fi

subnets_json="$(python - "$PRIVATE_SUBNET_IDS" <<'PY'
import json
import sys
subnets = [part.strip() for part in sys.argv[1].split(',') if part.strip()]
if not subnets:
    raise SystemExit("No subnet IDs supplied")
print(json.dumps(subnets))
PY
)"

network_configuration="$(python - "$subnets_json" "$task_security_group_id" <<'PY'
import json
import sys
print(json.dumps({
    "awsvpcConfiguration": {
        "subnets": json.loads(sys.argv[1]),
        "securityGroups": [sys.argv[2]],
        "assignPublicIp": "DISABLED",
    }
}))
PY
)"

echo "Starting smoke task with $task_definition_arn"
task_arn="$(aws ecs run-task \
  --region "$AWS_REGION" \
  --cluster "$CLUSTER_ARN" \
  --task-definition "$task_definition_arn" \
  --launch-type FARGATE \
  --platform-version LATEST \
  --network-configuration "$network_configuration" \
  --started-by "github-actions-${GITHUB_RUN_ID:-manual}" \
  --query 'tasks[0].taskArn' \
  --output text)"

if [[ -z "$task_arn" || "$task_arn" == "None" ]]; then
  echo "ECS did not return a task ARN" >&2
  exit 1
fi

echo "Waiting for smoke task to stop: $task_arn"
aws ecs wait tasks-stopped \
  --region "$AWS_REGION" \
  --cluster "$CLUSTER_ARN" \
  --tasks "$task_arn"

read -r exit_code stopped_reason task_status <<< "$(aws ecs describe-tasks \
  --region "$AWS_REGION" \
  --cluster "$CLUSTER_ARN" \
  --tasks "$task_arn" \
  --query 'tasks[0].[containers[0].exitCode,stoppedReason,lastStatus]' \
  --output text)"

echo "Smoke task status=$task_status exit_code=$exit_code reason=$stopped_reason"
if [[ "$exit_code" != "0" ]]; then
  aws ecs describe-tasks \
    --region "$AWS_REGION" \
    --cluster "$CLUSTER_ARN" \
    --tasks "$task_arn" \
    --output json
  exit 1
fi

echo "Smoke task completed successfully."
