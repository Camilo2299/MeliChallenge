#!/usr/bin/env bash
set -euo pipefail
: "${AWS_REGION:?Set AWS_REGION}"
: "${CLUSTER:=infra-signal-production}"
: "${SERVICE:=infra-signal-production}"
: "${PREVIOUS_TASK_DEFINITION_ARN:?Set PREVIOUS_TASK_DEFINITION_ARN from a previously healthy deployment}"
aws ecs update-service --region "$AWS_REGION" --cluster "$CLUSTER" --service "$SERVICE" --task-definition "$PREVIOUS_TASK_DEFINITION_ARN" >/dev/null
aws ecs wait services-stable --region "$AWS_REGION" --cluster "$CLUSTER" --services "$SERVICE"
echo "ECS service stable; reconcile Terraform image_tag with rolled-back SHA before the next apply."
