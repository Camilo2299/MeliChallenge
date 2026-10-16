data "aws_caller_identity" "current" {}

resource "aws_cognito_user_pool" "api" {
  count                    = var.jwt_issuer == "" ? 1 : 0
  name                     = local.name
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  admin_create_user_config { allow_admin_create_user_only = true }
  password_policy {
    minimum_length    = 14
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }
  tags = local.tags
}
resource "aws_cognito_resource_server" "metrics" {
  count        = var.jwt_issuer == "" ? 1 : 0
  identifier   = "infra-metrics"
  name         = "Infrastructure metrics"
  user_pool_id = aws_cognito_user_pool.api[0].id
  scope {
    scope_name        = "read"
    scope_description = "Read infrastructure sample metrics"
  }
}
resource "aws_cognito_user_pool_client" "api" {
  count                                = var.jwt_issuer == "" ? 1 : 0
  name                                 = "${local.name}-consumer"
  user_pool_id                         = aws_cognito_user_pool.api[0].id
  generate_secret                      = false
  supported_identity_providers         = ["COGNITO"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "${aws_cognito_resource_server.metrics[0].identifier}/read"]
  callback_urls                        = var.callback_urls
  prevent_user_existence_errors        = "ENABLED"
  enable_token_revocation              = true
  explicit_auth_flows                  = ["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_SRP_AUTH"]
}
resource "aws_cognito_user_pool_domain" "api" {
  count        = var.jwt_issuer == "" ? 1 : 0
  domain       = "${local.name}-${data.aws_caller_identity.current.account_id}"
  user_pool_id = aws_cognito_user_pool.api[0].id
}
locals {
  jwt_issuer    = var.jwt_issuer != "" ? var.jwt_issuer : "https://${aws_cognito_user_pool.api[0].endpoint}"
  jwt_audiences = var.jwt_issuer != "" ? var.jwt_audiences : [aws_cognito_user_pool_client.api[0].id]
  routes        = toset(["GET /v1/services", "GET /v1/services/{service_id}", "GET /v1/deployments", "GET /v1/summary"])
}
resource "aws_apigatewayv2_api" "api" {
  name          = local.name
  protocol_type = "HTTP"
  tags          = local.tags
}
resource "aws_apigatewayv2_vpc_link" "api" {
  name               = local.name
  subnet_ids         = aws_subnet.private[*].id
  security_group_ids = [aws_security_group.link.id]
  tags               = local.tags
}
resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.api.id
  name             = "organization-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  jwt_configuration {
    issuer   = local.jwt_issuer
    audience = local.jwt_audiences
  }
}
resource "aws_apigatewayv2_integration" "app" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "ANY"
  integration_uri        = aws_lb_listener.http.arn
  connection_type        = "VPC_LINK"
  connection_id          = aws_apigatewayv2_vpc_link.api.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 10000
  request_parameters     = { "overwrite:path" = "$request.path" }
}
resource "aws_apigatewayv2_route" "business" {
  for_each             = local.routes
  api_id               = aws_apigatewayv2_api.api.id
  route_key            = each.value
  target               = "integrations/${aws_apigatewayv2_integration.app.id}"
  authorization_type   = "JWT"
  authorizer_id        = aws_apigatewayv2_authorizer.jwt.id
  authorization_scopes = var.jwt_issuer == "" ? ["infra-metrics/read"] : var.jwt_scopes
}
resource "aws_apigatewayv2_route" "ready" {
  api_id             = aws_apigatewayv2_api.api.id
  route_key          = "GET /health/ready"
  target             = "integrations/${aws_apigatewayv2_integration.app.id}"
  authorization_type = "NONE"
}
resource "aws_cloudwatch_log_group" "gateway" {
  name              = "/apigateway/${local.name}"
  retention_in_days = 30
  tags              = local.tags
}
resource "aws_apigatewayv2_stage" "api" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_rate_limit    = var.throttle_rate
    throttling_burst_limit   = var.throttle_burst
    detailed_metrics_enabled = true
  }
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.gateway.arn
    format          = jsonencode({ requestId = "$context.requestId", routeKey = "$context.routeKey", status = "$context.status", latency = "$context.responseLatency", integrationError = "$context.integrationErrorMessage" })
  }
  tags = local.tags
}
resource "aws_cloudwatch_metric_alarm" "gateway_5xx" {
  alarm_name          = "${local.name}-gateway-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 5
  metric_name         = "5xx"
  namespace           = "AWS/ApiGateway"
  period              = 60
  statistic           = "Sum"
  treat_missing_data  = "notBreaching"
  dimensions          = { ApiId = aws_apigatewayv2_api.api.id }
  alarm_actions       = var.alarm_topic_arn == "" ? [] : [var.alarm_topic_arn]
  tags                = local.tags
}
resource "aws_cloudwatch_metric_alarm" "target_5xx" {
  alarm_name          = "${local.name}-target-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 5
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  treat_missing_data  = "notBreaching"
  dimensions          = { LoadBalancer = aws_lb.internal.arn_suffix }
  alarm_actions       = var.alarm_topic_arn == "" ? [] : [var.alarm_topic_arn]
  tags                = local.tags
}
