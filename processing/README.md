
# Twitch Chat Bot

This project provides a Twitch Chat Bot with the following features:

- Monitor Twitch chat messages and users.
- Decide if a user is allowed to chat based on a database.
- Delete unauthorized messages and notify users privately.

## Project Structure

- `message_poller/`: Polls Twitch messages and sends metadata to AWS SQS.
- `eligibility_processor/`: Checks user eligibility and sends results to another queue.
- `action_handler/`: Deletes unauthorized messages and sends private messages.

## Requirements

- Python 3.9+
- Docker
- MongoDB Atlas
- AWS Account with the following services:
  - SQS (Simple Queue Service)
  - SSM (System Manager Parameter Store)

## Getting Started

1. Clone the repository.
2. Set up AWS SSM Parameter Store with required parameters.
3. Deploy the infrastructure using Terraform.
4. Run the bot using Docker Compose.

## Environment Variables

Ensure the following parameters are available in AWS Parameter Store:

- `/bottwitch/bot_oauth_token`: Twitch bot OAuth token.
- `/bottwitch/client_id`: Twitch application client ID.
- `/bottwitch/client_secret`: Twitch application client secret.
- `/bottwitch/bot_access_token`: Access token for the bot.
- `/bottwitch/channel_name`: Twitch channel name.
- `/bottwitch/channel_id`: Twitch channel ID.
- `/botmongodb/connection_string`: MongoDB Atlas connection string.
- `/botaws/input_queue_url`: SQS input queue URL.
- `/botaws/output_queue_url`: SQS output queue URL.

## Usage

1. Build the Docker containers:
   ```bash
   docker-compose build
   ```

2. Run the containers:
   ```bash
   docker-compose up -d
   ```

3. Monitor logs:
   ```bash
   docker-compose logs -f
   ```

## Infrastructure Setup

Use the provided Terraform files to set up AWS resources:

- SSM Parameter Store
- SQS Queues
- EC2 Instance

## License

This project is licensed under the MIT License.
