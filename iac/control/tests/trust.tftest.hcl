mock_provider "aws" {}
run "bounded_control" {
  command = plan
  assert {
    condition     = jsondecode(aws_iam_role.foundation.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:Camilo2299@80074245/MeliChallenge@1421554656:environment:foundation"
    error_message = "Foundation trust must bind the immutable repository identity and dedicated environment."
  }
  assert {
    condition     = alltrue([for statement in jsondecode(aws_iam_policy.foundation.policy).Statement : !contains(statement.Action, "iam:PassRole") && !contains(statement.Action, "iam:DeleteRolePermissionsBoundary")])
    error_message = "Foundation must not pass roles or remove their permission boundaries."
  }
}
