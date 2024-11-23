# main.tf

provider "aws" {
  region     = var.aws_region
  access_key = var.aws_access_key
  secret_key = var.aws_secret_key
}

# 1. AWS SSM Parameters
resource "aws_ssm_parameter" "mongodb_connection_string" {
  name  = "/botmongodb/connection_string"
  type  = "SecureString"
  value = var.mongodb_connection_string
}

# 2. AWS SQS Queues
resource "aws_sqs_queue" "input_queue" {
  name                       = "twitch-input-queue"
  visibility_timeout_seconds = 30
}

resource "aws_sqs_queue" "output_queue" {
  name                       = "twitch-output-queue"
  visibility_timeout_seconds = 30
}

# SSM Parameters for SQS Queue URLs
resource "aws_ssm_parameter" "sqs_input_queue_url" {
  name  = "/botaws/input_queue_url"
  type  = "String"
  value = aws_sqs_queue.input_queue.id
}

resource "aws_ssm_parameter" "sqs_output_queue_url" {
  name  = "/botaws/output_queue_url"
  type  = "String"
  value = aws_sqs_queue.output_queue.id
}

# 3. IAM Roles and Policies

# EC2 Role
resource "aws_iam_role" "ec2_role" {
  name = "twitch_bot_ec2_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_policy" "ec2_policy" {
  name = "twitch_bot_ec2_policy"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath",
          "ssm:DescribeParameters"
        ],
        Effect   = "Allow",
        Resource = "*"
      },
      {
        Action = [
          "sqs:*",
          "logs:*",
          "ec2:DescribeVpcs",
          "ec2:DescribeSubnets",
          "ec2:DescribeImages",
          "ec2:DescribeRouteTables"
        ],
        Effect   = "Allow",
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ec2_role_attach" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.ec2_policy.arn
}

resource "aws_iam_instance_profile" "ec2_instance_profile" {
  name = "twitch_bot_instance_profile"
  role = aws_iam_role.ec2_role.name
}

# Lambda Role
resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      },
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_policy" "lambda_policy" {
  name        = "${var.project_name}_lambda_policy"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow",
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath",
          "ssm:DescribeParameters"
        ],
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_policy_attachment" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

# 4. Security Group
data "aws_vpc" "default" {
  default = true
}

resource "aws_security_group" "ec2_sg" {
  name        = "twitch_bot_sg"
  description = "Security group for Twitch Bot EC2 instance"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # Consider restricting SSH access to specific IPs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 5. EC2 Instance
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]  # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*"]
  }
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_instance" "twitch_bot_ec2" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = "t3.micro"
  subnet_id                   = data.aws_subnets.default.ids[0]  # Use the first subnet
  associate_public_ip_address = true
  key_name                    = var.key_pair_name
  iam_instance_profile        = aws_iam_instance_profile.ec2_instance_profile.name
  security_groups             = [aws_security_group.ec2_sg.id]

  user_data = file("user_data.sh")

  tags = {
    Name = "TwitchBotEC2"
  }
}

# 6. Random ID for Bucket Name Uniqueness
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# 7. S3 Bucket for Frontend
resource "aws_s3_bucket" "frontend_bucket" {
  bucket = "${var.project_name}-frontend-${random_id.bucket_suffix.hex}"
  acl    = "public-read"

  tags = {
    Name        = "${var.project_name}-frontend"
    Environment = var.environment
  }
}

# S3 Bucket Website Configuration
resource "aws_s3_bucket_website_configuration" "frontend_website" {
  bucket = aws_s3_bucket.frontend_bucket.id

  index_document {
    suffix = "index.html"
  }
}

# S3 Bucket Policy to Allow Public Read Access
resource "aws_s3_bucket_policy" "frontend_bucket_policy" {
  bucket = aws_s3_bucket.frontend_bucket.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid       = "PublicReadGetObject",
        Effect    = "Allow",
        Principal = "*",
        Action    = "s3:GetObject",
        Resource  = "${aws_s3_bucket.frontend_bucket.arn}/*"
      }
    ]
  })
}

# 8. Lambda Function
resource "aws_lambda_function" "oauth_handler" {
  filename         = "lambda_package.zip"  # The deployment package
  function_name    = "${var.project_name}_oauth_handler"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.9"
  timeout          = 10
  publish          = true

  environment {
    variables = {
      MONGODB_CONNECTION_STRING = var.mongodb_connection_string
      # No need for FRONTEND_CALLBACK_URL since we're not using it
    }
  }
}

# Lambda Function URL
resource "aws_lambda_function_url" "oauth_handler_url" {
  function_name      = aws_lambda_function.oauth_handler.function_name
  authorization_type = "NONE"  # Allows public access

  cors {
    allow_methods = ["POST"]
    allow_origins = ["*"]
  }
}

# 9. S3 Bucket Objects for Frontend

# Upload index.html
resource "aws_s3_object" "index_html" {
  bucket       = aws_s3_bucket.frontend_bucket.id
  key          = "index.html"
  source       = "${path.module}/frontend/index.html"
  content_type = "text/html"
  acl          = "public-read"
}

# Upload auth_callback.html with templating
resource "aws_s3_object" "auth_callback_html" {
  bucket       = aws_s3_bucket.frontend_bucket.id
  key          = "auth_callback.html"
  content      = templatefile("${path.module}/frontend/auth_callback.html", {
    LAMBDA_FUNCTION_URL = aws_lambda_function_url.oauth_handler_url.function_url
  })
  content_type = "text/html"
  acl          = "public-read"
}
