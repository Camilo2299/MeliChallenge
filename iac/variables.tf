variable "aws_region" {
  type    = string
  default = "us-east-1"
}
variable "project" {
  type    = string
  default = "infra-signal"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,14}$", var.project))
    error_message = "Use 3-15 lowercase letters, digits or hyphens, starting with a letter."
  }
}
variable "environment" {
  type    = string
  default = "lab"
  validation {
    condition     = contains(["lab", "staging", "production"], var.environment)
    error_message = "Use lab, staging or production."
  }
}
variable "image_tag" {
  type        = string
  description = "Immutable release tag already pushed to ECR."
  validation {
    condition     = can(regex("^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$", var.image_tag)) && var.image_tag != "latest"
    error_message = "Use a versioned immutable tag, never latest."
  }
}
variable "desired_count" {
  type    = number
  default = 2
  validation {
    condition     = var.desired_count >= var.min_capacity && var.desired_count <= var.max_capacity && floor(var.desired_count) == var.desired_count
    error_message = "desired_count must be an integer within the scaling limits."
  }
}
variable "min_capacity" {
  type    = number
  default = 2
  validation {
    condition     = var.min_capacity >= 2 && floor(var.min_capacity) == var.min_capacity
    error_message = "At least two tasks are required for the multi-AZ design."
  }
}
variable "max_capacity" {
  type    = number
  default = 4
  validation {
    condition     = var.max_capacity >= var.min_capacity && floor(var.max_capacity) == var.max_capacity
    error_message = "max_capacity must be an integer >= min_capacity."
  }
}
variable "deletion_protection" {
  type    = bool
  default = true
}
variable "deployment_generation" {
  type        = string
  default     = ""
  description = "Stable generation persisted by the lifecycle pipeline; changes only after a full destruction."
  validation {
    condition     = var.deployment_generation == "" || can(regex("^r[0-9]{1,20}$", var.deployment_generation))
    error_message = "Use an empty legacy generation or r followed by a GitHub run ID."
  }
}
variable "permissions_boundary_arn" {
  type    = string
  default = "arn:aws:iam::026249143093:policy/meli-ci-lab-runtime-boundary"
}
variable "secret_arn" {
  type        = string
  default     = ""
  description = "Optional existing secret ARN; API_TOKEN is not used to authorize demo requests."
}
variable "alarm_topic_arn" {
  type        = string
  default     = ""
  description = "Existing SNS topic with confirmed subscriptions; empty means no paging."
}
variable "jwt_issuer" {
  type        = string
  default     = ""
  description = "External OIDC issuer; empty provisions Cognito."
  validation {
    condition     = var.jwt_issuer == "" || startswith(var.jwt_issuer, "https://")
    error_message = "External issuer must use HTTPS."
  }
}
variable "jwt_audiences" {
  type    = list(string)
  default = []
  validation {
    condition     = var.jwt_issuer == "" || length(var.jwt_audiences) > 0
    error_message = "An external issuer requires at least one audience."
  }
}
variable "callback_urls" {
  type        = list(string)
  default     = ["http://localhost:8085/callback"]
  description = "Allowed OAuth authorization-code + PKCE callbacks for the Cognito client."
}
variable "throttle_rate" {
  type    = number
  default = 100
  validation {
    condition     = var.throttle_rate > 0
    error_message = "Throttle rate must be positive."
  }
}
variable "throttle_burst" {
  type    = number
  default = 200
  validation {
    condition     = var.throttle_burst >= 1 && floor(var.throttle_burst) == var.throttle_burst
    error_message = "Throttle burst must be a positive integer."
  }
}

variable "jwt_scopes" {
  type        = list(string)
  default     = ["infra-metrics/read"]
  description = "Required scopes for the external IdP; configure according to its access tokens."
  validation {
    condition     = length(var.jwt_scopes) > 0
    error_message = "Require at least one read scope on external JWTs."
  }
}

variable "additional_jwt_audiences" {
  type        = list(string)
  default     = []
  description = "Temporary additional machine client IDs for separately authorized capacity tests; empty in the normal lab."
}
