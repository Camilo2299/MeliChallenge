data "aws_caller_identity" "current" {}
resource "aws_iam_openid_connect_provider" "github" {
  count          = var.existing_oidc_provider_arn == "" ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  tags           = var.tags
}
locals {
  provider_arn = var.existing_oidc_provider_arn != "" ? var.existing_oidc_provider_arn : aws_iam_openid_connect_provider.github[0].arn
}
resource "aws_iam_role" "github" {
  for_each             = var.roles
  name                 = "${var.role_prefix}-${each.key}"
  max_session_duration = 3600
  permissions_boundary = var.permissions_boundary_arn
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity", Principal = { Federated = local.provider_arn }, Condition = {
      StringEquals = {
        "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        "token.actions.githubusercontent.com:sub" = "${var.repository_subject != "" ? var.repository_subject : "repo:${var.repository}"}:environment:${each.value.environment}"
      }
    } }]
  })
  tags = var.tags
}
locals {
  documents = merge([for key, role in var.roles : {
    for idx, policy in role.policies : "${key}-${idx}" => { role_key = key, policy = policy }
  }]...)
}
resource "aws_iam_policy" "github" {
  for_each = local.documents
  name     = "${var.role_prefix}-${each.key}"
  policy   = each.value.policy
  tags     = var.tags
}
resource "aws_iam_role_policy_attachment" "github" {
  for_each   = local.documents
  role       = aws_iam_role.github[each.value.role_key].name
  policy_arn = aws_iam_policy.github[each.key].arn
}
