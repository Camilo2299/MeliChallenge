# Retained control foundation: the workload role cannot grant itself administrative access.
resource "aws_iam_policy" "runtime_boundary" {
  name = "meli-ci-lab-runtime-boundary"
  tags = { Project = "infra-signal", Environment = "lab", ManagedBy = "terraform" }
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken", "cloudwatch:GetMetricData"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"], Resource = "arn:aws:ecr:us-east-1:026249143093:repository/infra-signal-lab" },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "arn:aws:logs:us-east-1:026249143093:log-group:/ecs/infra-signal-lab:*" },
    { Effect = "Allow", Action = ["ecs:DescribeServices"], Resource = "arn:aws:ecs:us-east-1:026249143093:service/infra-signal-lab/infra-signal-lab" },
    { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:UpdateItem", "dynamodb:PutItem"], Resource = "arn:aws:dynamodb:us-east-1:026249143093:table/infra-signal-lab-telemetry" },
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = "arn:aws:secretsmanager:us-east-1:026249143093:secret:infra-signal-lab/snapshot-signing-*" }
  ] })
}
output "runtime_boundary_arn" { value = aws_iam_policy.runtime_boundary.arn }
