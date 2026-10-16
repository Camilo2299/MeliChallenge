terraform {
  required_version = ">= 1.10.0"
  required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } }
  backend "s3" {}
}
provider "aws" {
  region              = "us-east-1"
  allowed_account_ids = ["026249143093"]
}
module "iam" {
  source             = "../modules/iam"
  repository         = "Camilo2299/MeliChallenge"
  repository_subject = "repo:Camilo2299@80074245/MeliChallenge@1421554656"
  role_prefix        = "meli-ci-lab"
  tags               = { Project = "infra-signal", Environment = "lab", ManagedBy = "terraform", Owner = "Camilo2299" }
  roles = {
    publish   = { environment = "image-publish", policies = [for policy in jsondecode(file("${path.module}/publish.policy.json")) : jsonencode(policy)] }
    plan      = { environment = "production-plan", policies = [for policy in jsondecode(file("${path.module}/plan.policy.json")) : jsonencode(policy)] }
    terraform = { environment = "production", policies = [for policy in jsondecode(file("${path.module}/terraform.policy.json")) : jsonencode(policy)] }
  }
}
output "role_arns" { value = module.iam.role_arns }
output "oidc_provider_arn" { value = module.iam.oidc_provider_arn }
