# variables.tf

variable "project_name" {
  description = "Name of the project for resource naming"
  type        = string
  default     = "patrolia"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "AWS Region to deploy resources"
  type        = string
  default     = "eu-west-1"
}

variable "aws_access_key" {
  description = "AWS Access Key for authentication"
  type        = string
  sensitive   = true
}

variable "aws_secret_key" {
  description = "AWS Secret Key for authentication"
  type        = string
  sensitive   = true
}

variable "mongodb_connection_string" {
  description = "Connection string for MongoDB Atlas."
  type        = string
  sensitive   = true
}

variable "key_pair_name" {
  description = "Name of the AWS EC2 Key Pair."
  type        = string
}
