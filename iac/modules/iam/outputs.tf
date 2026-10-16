output "role_arns" { value = { for key, role in aws_iam_role.github : key => role.arn } }
output "oidc_provider_arn" { value = local.provider_arn }

output "trust_policies" {
  value = { for key, role in aws_iam_role.github : key => jsondecode(role.assume_role_policy) }
}
