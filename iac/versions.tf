terraform {
  required_version = ">= 1.11.0"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.7" }
  }
  backend "s3" {}
}
provider "aws" {
  region = var.aws_region
  default_tags {
    tags = { Project = var.project, Environment = var.environment, ManagedBy = "terraform" }
  }
}
