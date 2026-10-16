terraform {
  required_version = ">= 1.10.0"
  required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } }
  backend "s3" {}
}
provider "aws" {
  region = "us-east-1"
  default_tags { tags = { Project = "infra-signal", Environment = "lab", Purpose = "temporary-capacity-generator", ManagedBy = "terraform" } }
}
data "aws_caller_identity" "current" {}
data "aws_ssm_parameter" "ami" { name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64" }
data "aws_subnet" "public" { id = "subnet-04e759fd4b629e774" }
resource "aws_cognito_user_pool_client" "capacity" {
  name                                 = "infra-signal-lab-capacity-temporary"
  user_pool_id                         = "us-east-1_krpZrFRXe"
  generate_secret                      = true
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_scopes                 = ["infra-metrics/read"]
  access_token_validity                = 10
  token_validity_units { access_token = "minutes" }
  prevent_user_existence_errors = "ENABLED"
}
resource "aws_s3_bucket" "artifacts" {
  bucket        = "infra-signal-lab-capacity-${data.aws_caller_identity.current.account_id}"
  force_destroy = true # Temporary scripts/results; download sanitized evidence before destroy.
}
resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_policy" "tls" {
  bucket = aws_s3_bucket.artifacts.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.artifacts.arn, "${aws_s3_bucket.artifacts.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}
resource "aws_s3_object" "scripts" {
  for_each = {
    "capacity.js"     = "${path.module}/../capacity.js"
    "regional_run.py" = "${path.module}/../regional_run.py"
  }
  bucket                 = aws_s3_bucket.artifacts.id
  key                    = "scripts/${each.key}"
  source                 = each.value
  source_hash            = filemd5(each.value)
  server_side_encryption = "AES256"
}
resource "aws_iam_role" "generator" {
  name = "infra-signal-lab-capacity-generator"
  # EC2 instance-profile trust; this service does not supply SourceArn/SourceAccount here.
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.generator.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_role_policy" "generator" {
  role = aws_iam_role.generator.name
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["cognito-idp:DescribeUserPoolClient"], Resource = ["arn:aws:cognito-idp:us-east-1:${data.aws_caller_identity.current.account_id}:userpool/us-east-1_krpZrFRXe"], Condition = { StringEquals = { "aws:RequestedRegion" = "us-east-1" } } },
    { Effect = "Allow", Action = ["s3:GetObject"], Resource = ["${aws_s3_bucket.artifacts.arn}/scripts/*"] },
    { Effect = "Allow", Action = ["s3:PutObject"], Resource = ["${aws_s3_bucket.artifacts.arn}/results/*"] }
  ] })
}
resource "aws_iam_instance_profile" "generator" {
  name = "infra-signal-lab-capacity-generator"
  role = aws_iam_role.generator.name
}
resource "aws_security_group" "generator" {
  name        = "infra-signal-lab-capacity-generator"
  description = "Temporary outbound HTTPS load generator; no ingress or SSH"
  vpc_id      = data.aws_subnet.public.vpc_id
  egress {
    description = "HTTPS to API Gateway, SSM, Cognito, S3 and official k6 release"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_launch_template" "generator" {
  name_prefix   = "infra-signal-lab-capacity-"
  image_id      = data.aws_ssm_parameter.ami.value
  instance_type = "c7g.2xlarge"
  iam_instance_profile { name = aws_iam_instance_profile.generator.name }
  instance_initiated_shutdown_behavior = "terminate"
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  network_interfaces {
    associate_public_ip_address = true
    subnet_id                   = data.aws_subnet.public.id
    security_groups             = [aws_security_group.generator.id]
  }
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      encrypted             = true
      volume_size           = 8
      volume_type           = "gp3"
      delete_on_termination = true
    }
  }
  user_data = base64encode(templatefile("${path.module}/bootstrap.sh.tftpl", {
    bucket = aws_s3_bucket.artifacts.id, client_id = aws_cognito_user_pool_client.capacity.id
  }))
  tag_specifications {
    resource_type = "instance"
    tags          = { Name = "infra-signal-lab-capacity-generator", Project = "infra-signal", Environment = "lab", Purpose = "temporary-capacity-generator", ManagedBy = "terraform" }
  }
}
resource "aws_instance" "generator" {
  launch_template {
    id      = aws_launch_template.generator.id
    version = aws_launch_template.generator.latest_version
  }
  tags       = { Name = "infra-signal-lab-capacity-generator" }
  depends_on = [aws_iam_role_policy_attachment.ssm, aws_iam_role_policy.generator, aws_s3_object.scripts]
}
output "instance_id" { value = aws_instance.generator.id }
output "capacity_client_id" { value = aws_cognito_user_pool_client.capacity.id }
output "artifact_bucket" { value = aws_s3_bucket.artifacts.id }
