terraform {
  required_version = ">= 1.10.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}
provider "aws" { region = var.aws_region }
variable "aws_region" {
  type    = string
  default = "us-east-1"
}
variable "project" {
  type    = string
  default = "infra-signal"
}
variable "environment" {
  type    = string
  default = "lab"
}
data "aws_caller_identity" "current" {}
locals {
  name = "${var.project}-${var.environment}"
  tags = { Project = var.project, Environment = var.environment, ManagedBy = "terraform" }
}
resource "aws_s3_bucket" "state" {
  bucket = "${local.name}-tfstate-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  tags   = local.tags
  lifecycle { prevent_destroy = true }
}
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport", Effect = "Deny", Principal = "*", Action = "s3:*"
      Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}
resource "aws_ecr_repository" "app" {
  name                 = local.name
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
  tags = local.tags
}
# Retain tagged releases so a cleanup policy cannot remove a running/rollback image.
resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({ rules = [{
    rulePriority = 1, description = "Expire untagged layers after 7 days"
    selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 7 }
    action       = { type = "expire" }
  }] })
}
output "state_bucket" { value = aws_s3_bucket.state.id }
output "ecr_repository_url" { value = aws_ecr_repository.app.repository_url }

variable "monthly_budget_usd" {
  type        = number
  description = "Approved monthly account-wide budget in USD; alerts do not cap spending."
  validation {
    condition     = var.monthly_budget_usd > 0
    error_message = "Set an approved positive monthly budget."
  }
}
variable "budget_email" {
  type        = string
  sensitive   = true
  description = "Email destination for budget alerts."
  validation {
    condition     = can(regex("^[^@ ]+@[^@ ]+[.][^@ ]+$", var.budget_email))
    error_message = "Set a valid notification email."
  }
}
resource "aws_budgets_budget" "account" {
  name         = "${local.name}-account-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  cost_types {
    include_credit = false
    include_refund = false
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_email]
  }
}
