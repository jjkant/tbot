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

variable "twitch_bot_oauth_token" {
  description = "OAuth token for the Twitch bot."
  type        = string
}

variable "twitch_client_id" {
  description = "Twitch application client ID."
  type        = string
}

variable "twitch_client_secret" {
  description = "Twitch application client secret."
  type        = string
}

variable "twitch_bot_refresh_token" {
  description = "Refresh token for the Twitch bot."
  type        = string
}

variable "twitch_bot_access_token" {
  description = "Access token for Twitch API calls."
  type        = string
}

variable "twitch_channel_name" {
  description = "Name of your Twitch channel."
  type        = string
}

variable "twitch_channel_id" {
  description = "ID of your Twitch channel."
  type        = string
}

variable "mongodb_connection_string" {
  description = "Connection string for MongoDB Atlas."
  type        = string
}

variable "key_pair_name" {
  description = "Name of the AWS EC2 Key Pair."
  type        = string
}
