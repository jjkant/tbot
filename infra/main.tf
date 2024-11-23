
provider "aws" {
  region     = var.aws_region
  access_key = var.aws_access_key
  secret_key = var.aws_secret_key
}

resource "aws_ssm_parameter" "twitch_bot_oauth_token" {
  name  = "/bottwitch/bot_oauth_token"
  type  = "SecureString"
  value = var.twitch_bot_oauth_token
}

resource "aws_ssm_parameter" "twitch_bot_refresh_token" {
  name  = "/bottwitch/bot_refresh_token"
  type  = "SecureString"
  value = var.twitch_bot_refresh_token
}

resource "aws_ssm_parameter" "twitch_client_id" {
  name  = "/bottwitch/client_id"
  type  = "String"
  value = var.twitch_client_id
}

resource "aws_ssm_parameter" "twitch_client_secret" {
  name  = "/bottwitch/client_secret"
  type  = "SecureString"
  value = var.twitch_client_secret
}

resource "aws_ssm_parameter" "twitch_bot_access_token" {
  name  = "/bottwitch/bot_access_token"
  type  = "SecureString"
  value = var.twitch_bot_access_token
}

resource "aws_ssm_parameter" "twitch_channel_name" {
  name  = "/bottwitch/channel_name"
  type  = "String"
  value = var.twitch_channel_name
}

resource "aws_ssm_parameter" "twitch_channel_id" {
  name  = "/bottwitch/channel_id"
  type  = "String"
  value = var.twitch_channel_id
}

resource "aws_ssm_parameter" "mongodb_connection_string" {
  name  = "/botmongodb/connection_string"
  type  = "SecureString"
  value = var.mongodb_connection_string
}

# 2. AWS SQS Queues

resource "aws_sqs_queue" "input_queue" {
  name                      = "twitch-input-queue"
  visibility_timeout_seconds = 30
}

resource "aws_sqs_queue" "output_queue" {
  name                      = "twitch-output-queue"
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

# 3. IAM Role and Instance Profile for EC2

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

resource "aws_iam_role_policy_attachment" "ec2_role_attach" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.ec2_policy.arn
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
          "ssm:DescribeParameters",
          "ssm:PutParameter"
        ],
        Effect   = "Allow",
        Resource = "*"
      },
      {
        Action = [
          "sqs:*",
          "ssm:*",
          "logs:*",
          "ecr:*",
          "secretsmanager:GetSecretValue",
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

resource "aws_iam_instance_profile" "ec2_instance_profile" {
  name = "twitch_bot_instance_profile"
  role = aws_iam_role.ec2_role.name
}

# 4. Security Group

resource "aws_security_group" "ec2_sg" {
  name        = "twitch_bot_sg"
  description = "Security group for Twitch Bot EC2 instance"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

data "aws_vpc" "default" {
  default = true
}

# 5. EC2 Instance

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

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

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
