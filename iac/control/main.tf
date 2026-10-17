# Root of trust: installed with SSO once, retained across application destruction.
terraform {
  required_version = ">= 1.11.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
  backend "s3" {}
}
provider "aws" {
  region              = "us-east-1"
  allowed_account_ids = ["026249143093"]
  default_tags { tags = { Project = "infra-signal", Environment = "lab", ManagedBy = "terraform" } }
}
locals {
  account       = "026249143093"
  runtime_roles = [for name in ["execution", "task"] : "arn:aws:iam::${local.account}:role/infra-signal-lab-${name}"]
}
# Ceiling, not a grant: the existing CI policies remain more restrictive. The
# foundation role cannot edit this policy or the immutable runtime ceiling.
resource "aws_iam_policy" "ci_ceiling" {
  name = "meli-ci-lab-ci-ceiling"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["apigateway:*", "application-autoscaling:*", "cloudwatch:*", "cognito-idp:*", "ec2:*", "ecs:*", "elasticloadbalancing:*", "logs:*", "dynamodb:*", "secretsmanager:*", "ecr:*"], Resource = "*", Condition = { StringEquals = { "aws:RequestedRegion" = "us-east-1" } } },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = "arn:aws:s3:::infra-signal-lab-tfstate-026249143093-us-east-1" },
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = ["arn:aws:s3:::infra-signal-lab-tfstate-026249143093-us-east-1/infra-signal/lab.tfstate*", "arn:aws:s3:::infra-signal-lab-tfstate-026249143093-us-east-1/infra-signal/lifecycle.json"] },
    { Effect = "Allow", Action = ["s3:DeleteObject"], Resource = "arn:aws:s3:::infra-signal-lab-tfstate-026249143093-us-east-1/infra-signal/lab.tfstate.tflock" },
    { Effect = "Allow", Action = ["iam:GetRole", "iam:GetRolePolicy", "iam:ListRolePolicies", "iam:ListRoleTags", "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole", "iam:TagRole", "iam:UntagRole", "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:DeleteRole", "iam:UpdateAssumeRolePolicy", "iam:AttachRolePolicy", "iam:DetachRolePolicy"], Resource = local.runtime_roles },
    { Effect = "Allow", Action = ["iam:CreateRole", "iam:PutRolePermissionsBoundary"], Resource = local.runtime_roles, Condition = { ArnEquals = { "iam:PermissionsBoundary" = "arn:aws:iam::026249143093:policy/meli-ci-lab-runtime-boundary" } } },
    { Effect = "Allow", Action = "iam:PassRole", Resource = local.runtime_roles, Condition = { StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" } } },
    { Effect = "Allow", Action = "iam:CreateServiceLinkedRole", Resource = "arn:aws:iam::026249143093:role/aws-service-role/*" }
  ] })
  lifecycle { prevent_destroy = true }
}
resource "aws_iam_role" "foundation" {
  name = "meli-ci-lab-foundation"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Allow", Action = "sts:AssumeRoleWithWebIdentity",
    Principal = { Federated = "arn:aws:iam::026249143093:oidc-provider/token.actions.githubusercontent.com" },
    Condition = { StringEquals = {
      "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub" = "repo:Camilo2299@80074245/MeliChallenge@1421554656:environment:foundation"
    } }
  }] })
  lifecycle { prevent_destroy = true }
}
resource "aws_iam_policy" "foundation" {
  name   = "meli-ci-lab-foundation-maintenance"
  policy = file("${path.module}/foundation.policy.json")
  lifecycle { prevent_destroy = true }
}
resource "aws_iam_role_policy_attachment" "foundation" {
  role       = aws_iam_role.foundation.name
  policy_arn = aws_iam_policy.foundation.arn
}
output "foundation_role_arn" { value = aws_iam_role.foundation.arn }
