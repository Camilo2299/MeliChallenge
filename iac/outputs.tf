output "api_url" { value = aws_apigatewayv2_api.api.api_endpoint }
output "alb_dns" {
  value       = aws_lb.internal.dns_name
  description = "Private ALB hostname; use API Gateway for public access."
}
output "ecr_repository_url" { value = data.aws_ecr_repository.app.repository_url }
output "ecs_cluster" { value = aws_ecs_cluster.main.name }
output "ecs_service" { value = aws_ecs_service.app.name }
output "vpc_id" { value = aws_vpc.main.id }
output "public_subnet_id" { value = aws_subnet.public[0].id }
output "private_subnet_ids" { value = aws_subnet.private[*].id }
output "cognito_user_pool_id" { value = try(aws_cognito_user_pool.api[0].id, null) }
output "cognito_client_id" { value = try(aws_cognito_user_pool_client.api[0].id, null) }
output "cognito_login_url" {
  value = var.jwt_issuer == "" ? "https://${aws_cognito_user_pool_domain.api[0].domain}.auth.${var.aws_region}.amazoncognito.com/oauth2/authorize" : null
}
