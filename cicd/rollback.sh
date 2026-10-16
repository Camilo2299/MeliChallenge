#!/usr/bin/env bash
set -euo pipefail
: "${AWS_REGION:?Set AWS_REGION}"
: "${CLUSTER:?Set CLUSTER explicitly}"
: "${SERVICE:?Set SERVICE explicitly}"
: "${PREVIOUS_TASK_DEFINITION_ARN:?Set PREVIOUS_TASK_DEFINITION_ARN from a previously healthy deployment}"
STATUS=$(aws ecs describe-task-definition --region "$AWS_REGION" --task-definition "$PREVIOUS_TASK_DEFINITION_ARN" --query 'taskDefinition.status' --output text)
if [ "$STATUS" != ACTIVE ]; then
  echo "Refusing rollback: the target task definition is not ACTIVE. Review and re-register the known-good configuration first." >&2
  exit 1
fi
aws ecs update-service --region "$AWS_REGION" --cluster "$CLUSTER" --service "$SERVICE" --task-definition "$PREVIOUS_TASK_DEFINITION_ARN" >/dev/null
aws ecs wait services-stable --region "$AWS_REGION" --cluster "$CLUSTER" --services "$SERVICE"
echo "ECS service stable; reconcile Terraform image_tag with rolled-back SHA before the next apply."
