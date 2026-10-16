mock_provider "aws" {
  mock_resource "aws_iam_openid_connect_provider" {
    defaults = { arn = "arn:aws:iam::026249143093:oidc-provider/token.actions.githubusercontent.com" }
  }
  mock_resource "aws_iam_policy" {
    defaults = { arn = "arn:aws:iam::026249143093:policy/test-policy" }
  }
}
run "exact_repository_and_environments" {
  command = apply
  assert {
    condition     = alltrue([for key, trust in output.trust_policies : trust.Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"])
    error_message = "Every role must restrict the OIDC audience to AWS STS."
  }
  assert {
    condition     = output.trust_policies.publish.Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:Camilo2299/MeliChallenge:environment:image-publish" && output.trust_policies.plan.Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:Camilo2299/MeliChallenge:environment:production-plan" && output.trust_policies.terraform.Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:Camilo2299/MeliChallenge:environment:production"
    error_message = "Trust must bind each role to its exact repository and environment."
  }
}
