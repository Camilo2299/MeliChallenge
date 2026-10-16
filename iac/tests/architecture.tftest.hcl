mock_provider "aws" {
  mock_resource "aws_lb" { defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/infra-signal-lab/1234567890123456" } }
  mock_resource "aws_lb_target_group" { defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/infra-signal-lab/1234567890123456" } }
  mock_resource "aws_lb_listener" { defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:listener/app/infra-signal-lab/1234567890123456/1234567890123456" } }
  mock_resource "aws_iam_role" { defaults = { arn = "arn:aws:iam::123456789012:role/test-role" } }
  mock_resource "aws_cloudwatch_log_group" { defaults = { arn = "arn:aws:logs:us-east-1:123456789012:log-group:/test" } }
  mock_resource "aws_ecs_cluster" { defaults = { arn = "arn:aws:ecs:us-east-1:123456789012:cluster/test" } }
  mock_resource "aws_ecs_task_definition" { defaults = { arn = "arn:aws:ecs:us-east-1:123456789012:task-definition/test:1" } }
  mock_resource "aws_cognito_user_pool" { defaults = { id = "us-east-1_Test1234", endpoint = "cognito-idp.us-east-1.amazonaws.com/us-east-1_Test1234" } }

  mock_data "aws_availability_zones" { defaults = { names = ["us-east-1a", "us-east-1b"] } }
  mock_data "aws_caller_identity" { defaults = { account_id = "123456789012" } }
  mock_data "aws_ecr_repository" { defaults = { repository_url = "123456789012.dkr.ecr.us-east-1.amazonaws.com/infra-signal-lab" } }
}
variables { image_tag = "test-release" }
run "private_backend" {
  command = apply
  assert {
    condition     = aws_lb.internal.internal && length(aws_lb.internal.subnets) == 2
    error_message = "ALB must be private across two AZs."
  }
  assert {
    condition     = !aws_ecs_service.app.network_configuration[0].assign_public_ip && length(aws_ecs_service.app.network_configuration[0].subnets) == 2
    error_message = "ECS tasks must be private across two AZs."
  }
  assert {
    condition     = alltrue([for route in aws_apigatewayv2_route.business : route.authorization_type == "JWT"])
    error_message = "All business routes must require JWT."
  }
  assert {
    condition     = aws_apigatewayv2_integration.app.connection_type == "VPC_LINK" && aws_apigatewayv2_integration.app.request_parameters["overwrite:path"] == "$request.path"
    error_message = "Use a private integration and strip the stage prefix."
  }
  assert {
    condition     = aws_ecs_task_definition.app.runtime_platform[0].cpu_architecture == "X86_64"
    error_message = "Runtime must match the Linux/amd64 image."
  }
}
run "external_oidc" {
  command = apply
  variables {
    jwt_issuer    = "https://issuer.example.com"
    jwt_audiences = ["metrics-api"]
  }
  assert {
    condition     = length(aws_cognito_user_pool.api) == 0 && aws_apigatewayv2_authorizer.jwt.jwt_configuration[0].issuer == "https://issuer.example.com"
    error_message = "External OIDC should not provision Cognito."
  }
}
