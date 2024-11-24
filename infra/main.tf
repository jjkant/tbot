provider "aws" {
  region     = var.aws_region
  access_key = var.aws_access_key
  secret_key = var.aws_secret_key
}

# 1. AWS SSM Parameters
resource "aws_ssm_parameter" "mongodb_connection_string" {
  name  = "/patroliamongodb/connection_string"
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
  name  = "/patroliaaws/input_queue_url"
  type  = "String"
  value = aws_sqs_queue.input_queue.id
}

resource "aws_ssm_parameter" "sqs_output_queue_url" {
  name  = "/patroliaaws/output_queue_url"
  type  = "String"
  value = aws_sqs_queue.output_queue.id
}

# 3. IAM Roles and Policies

# EC2 Role
resource "aws_iam_role" "ec2_role" {
  name = "patrolia_ec2_role"

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
  name = "patrolia_ec2_policy"

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
  name = "patrolia_instance_profile"
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
  name        = "patrolia_sg"
  description = "Security group for Patrolia EC2 instance"
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

resource "aws_instance" "patrolia_ec2" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = "t3.micro"
  subnet_id                   = data.aws_subnets.default.ids[0]  # Use the first subnet
  associate_public_ip_address = true
  key_name                    = var.key_pair_name
  iam_instance_profile        = aws_iam_instance_profile.ec2_instance_profile.name
  security_groups             = [aws_security_group.ec2_sg.id]

  user_data = file("user_data.sh")

  tags = {
    Name = "PatroliaEC2"
  }
}

# 6. Random ID for Bucket Name Uniqueness
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# 7. S3 Bucket for Frontend
resource "aws_s3_bucket" "frontend_bucket" {
  bucket = "${var.project_name}-frontend-${random_id.bucket_suffix.hex}"

  tags = {
    Name        = "${var.project_name}-frontend"
    Environment = var.environment
  }
}

resource "aws_s3_bucket_ownership_controls" "frontend_bucket_ownership_controls" {
  bucket = aws_s3_bucket.frontend_bucket.id

  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_public_access_block" "frontend_bucket_public_access_block" {
  bucket = aws_s3_bucket.frontend_bucket.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false

  depends_on = [aws_s3_bucket.frontend_bucket]
}

resource "aws_s3_bucket_acl" "frontend_bucket_acl" {
  depends_on = [
    aws_s3_bucket.frontend_bucket,
    aws_s3_bucket_ownership_controls.frontend_bucket_ownership_controls,
    aws_s3_bucket_public_access_block.frontend_bucket_public_access_block,
  ]

  bucket = aws_s3_bucket.frontend_bucket.id
  acl    = "public-read"
}

# S3 Bucket Website Configuration
resource "aws_s3_bucket_website_configuration" "frontend_website" {
  bucket = aws_s3_bucket.frontend_bucket.id

  index_document {
    suffix = "index.html"
  }

  depends_on = [aws_s3_bucket_acl.frontend_bucket_acl]
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

  depends_on = [
    aws_s3_bucket_acl.frontend_bucket_acl,
    aws_s3_bucket_website_configuration.frontend_website
  ]
}

# 8. S3 Bucket Objects for Frontend

# Upload index.html
resource "aws_s3_object" "index_html" {
  bucket       = aws_s3_bucket.frontend_bucket.id
  key          = "index.html"
  source       = "${path.module}/frontend/index.html"
  content_type = "text/html"

  depends_on = [aws_s3_bucket_policy.frontend_bucket_policy]
}

# Upload auth_callback.html with templating
resource "aws_s3_object" "auth_callback_html" {
  bucket       = aws_s3_bucket.frontend_bucket.id
  key          = "auth_callback.html"
  content      = templatefile("${path.module}/frontend/auth_callback.html", {
    LAMBDA_FUNCTION_URL = aws_lambda_function_url.oauth_handler_url.function_url
  })
  content_type = "text/html"

  depends_on = [aws_s3_bucket_policy.frontend_bucket_policy]
}

# 9. Lambda Function
resource "aws_lambda_function" "oauth_handler" {
  filename         = "lambda_function.zip"  # The deployment package
  function_name    = "${var.project_name}_oauth_handler"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.11"
  timeout          = 10
  publish          = true

  layers = [
    "arn:aws:lambda:eu-west-1:770693421928:layer:Klayers-p311-pymongo:11",
    "arn:aws:lambda:eu-west-1:770693421928:layer:Klayers-p311-requests:13"
  ]

  environment {
    variables = {
      MONGODB_CONNECTION_STRING = var.mongodb_connection_string
      FRONTEND_CALLBACK_URL     = "https://patrolia-frontend-${random_id.bucket_suffix.hex}.s3.${var.aws_region}.amazonaws.com/auth_callback.html"
    }
  }
}

# Lambda Function URL
resource "aws_lambda_function_url" "oauth_handler_url" {
  function_name      = aws_lambda_function.oauth_handler.function_name
  authorization_type = "NONE"  # Allows public access

  cors {
    allow_methods = ["POST"]
    allow_origins = ["https://patrolia-frontend-${random_id.bucket_suffix.hex}.s3.${var.aws_region}.amazonaws.com"]
    allow_headers = ["Content-Type", "Authorization", "X-Amz-Date", "X-Api-Key", "X-Amz-Security-Token"]
    expose_headers = ["Content-Type", "Authorization"]
    max_age        = 3600
  }
}
