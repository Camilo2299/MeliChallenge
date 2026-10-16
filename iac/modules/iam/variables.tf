variable "repository" { type = string }
variable "role_prefix" { type = string }
variable "existing_oidc_provider_arn" {
  type    = string
  default = ""
}
variable "tags" { type = map(string) }
variable "roles" {
  type = map(object({ environment = string, policies = list(string) }))
  validation {
    condition     = alltrue([for role in values(var.roles) : alltrue([for policy in role.policies : can(jsondecode(policy).Statement)])])
    error_message = "Each role requires a valid identity policy."
  }
}

variable "repository_subject" {
  type        = string
  default     = ""
  description = "Exact GitHub repository sub_claim_prefix when immutable subjects are enabled."
}
