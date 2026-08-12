# AWS deployment: scheduled opportunity intake

This deployment runs `openplanter-opportunities` as an isolated ECS Fargate task. It does not require the long-running OpenPlanter service to stay active between runs.

## Resources

The CloudFormation template creates:

- an ECS Fargate task definition;
- an encrypted EFS file system and access point for immutable run artifacts and reports;
- a least-privilege ECS execution role for image retrieval, logs, and secret injection;
- a task role restricted to the EFS access point;
- an EventBridge Scheduler schedule;
- an encrypted SQS dead-letter queue;
- a CloudWatch log group;
- an SNS failure topic and optional email subscription;
- an EventBridge rule for non-zero ECS task exits.

The existing ECS cluster, VPC, private subnets, SAM.gov secret, container image, and EFS security group are supplied as parameters.

## Build and publish the image

```bash
docker build -f Dockerfile.opportunities -t openplanter-opportunities:latest .

aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin \
    "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

docker tag openplanter-opportunities:latest \
  "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/openplanter-opportunities:$GIT_SHA"

docker push \
  "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/openplanter-opportunities:$GIT_SHA"
```

Use the resulting immutable image digest in the stack parameter rather than `latest`.

## Store the SAM.gov API key

```bash
aws secretsmanager create-secret \
  --name openplanter/prod/sam-gov-api-key \
  --secret-string "$SAM_GOV_API_KEY"
```

The task definition injects the full secret value into `SAM_GOV_API_KEY`. The key is never placed in the image, task command, or CloudFormation parameters file.

## Network prerequisite

The supplied EFS security group must allow inbound TCP 2049 from the task security group created by the stack. Private subnets also need outbound HTTPS through a NAT gateway or suitable VPC endpoints so the task can reach SAM.gov, ECR, CloudWatch Logs, and Secrets Manager.

After the first stack deployment, use the `TaskSecurityGroupId` output to restrict the EFS inbound rule to that security group.

## Deploy

Copy the example parameters and replace placeholders:

```bash
cp infra/aws/opportunity-intake.parameters.example.json \
  infra/aws/opportunity-intake.parameters.json
```

Validate and deploy:

```bash
aws cloudformation validate-template \
  --template-body file://infra/aws/opportunity-intake-scheduled-task.yaml

aws cloudformation deploy \
  --stack-name openplanter-opportunity-intake \
  --template-file infra/aws/opportunity-intake-scheduled-task.yaml \
  --parameter-overrides file://infra/aws/opportunity-intake.parameters.json \
  --capabilities CAPABILITY_NAMED_IAM
```

## Runtime paths

The EFS access point is mounted at `/mnt/opportunities`.

```text
/mnt/opportunities/
  runs/
    <UTC run id>/
      run.json
      manifest.json
      opportunities/
      evidence/
      missions/
      graphs/
      bundles/
  reports/
    latest-report.json
```

The Fargate root filesystem is read-only. Only the EFS mount is writable.

## Schedule and recovery

The default schedule is daily at 06:00 UTC. EventBridge Scheduler retries twice for up to one hour. Exhausted scheduler deliveries go to the encrypted SQS dead-letter queue.

A stopped ECS task with a non-zero container exit code publishes to the SNS failure topic. When `NotificationEmail` is supplied, AWS sends a subscription confirmation email that must be accepted before notifications begin.

## Manual verification

Run the task once manually before relying on the schedule:

```bash
aws ecs run-task \
  --cluster "$CLUSTER_ARN" \
  --task-definition "$TASK_DEFINITION_ARN" \
  --launch-type FARGATE \
  --network-configuration \
    "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$TASK_SECURITY_GROUP_ID],assignPublicIp=DISABLED}"
```

Verify:

1. The task exits with code `0`.
2. CloudWatch contains the completion log.
3. EFS contains `run.json`, `manifest.json`, and the artifact directories.
4. `latest-report.json` exists.
5. The SAM.gov API key does not appear in logs or task metadata.

## Operational boundary

This stack prepares and schedules the infrastructure but does not modify the existing `aegentix-govops` ECS service. The intake runs as a separate one-shot task in the same cluster, which avoids coupling daily ingestion success to the availability or deployment lifecycle of the long-running service.
