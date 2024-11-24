Twitch Chat Bot
===============

This project provides a Twitch Chat Bot with the following features:

-   Monitor Twitch chat events (messages and user joins).
-   Decide if a user is allowed to chat based on a database.
-   Timeout unauthorized users, notify them privately, and delete their messages.

Project Structure
-----------------

-   `event_poller/`: Polls Twitch events (messages and joins) and sends metadata to AWS SQS.
-   `eligibility_processor/`: Checks user eligibility and sends results to another queue.
-   `action_handler/`: Times out unauthorized users, deletes their messages, and sends private messages.

Requirements
------------

-   Python 3.9+
-   Docker
-   MongoDB Atlas
-   AWS Account with the following services:
    -   SQS (Simple Queue Service)
    -   SSM (System Manager Parameter Store)

Getting Started
---------------

1.  Clone the repository.
2.  Set up AWS SSM Parameter Store with required parameters.
3.  Deploy the infrastructure using Terraform.
4.  Run the bot using Docker Compose.

Environment Variables
---------------------

Ensure the following parameters are available in AWS Parameter Store:

-   `/patroliatwitch/patrolia_oauth_token`: Patrolia OAuth token.
-   `/patroliatwitch/client_id`: Twitch application client ID.
-   `/patroliatwitch/client_secret`: Twitch application client secret.
-   `/patroliatwitch/patrolia_access_token`: Access token for the bot.
-   `/patroliatwitch/channel_name`: Twitch channel name.
-   `/patroliatwitch/channel_id`: Twitch channel ID.
-   `/patroliamongodb/connection_string`: MongoDB Atlas connection string.
-   `/patroliaaws/input_queue_url`: SQS input queue URL.
-   `/patroliaaws/output_queue_url`: SQS output queue URL.

Usage
-----

1.  Build the Docker containers:

    bash

    Copiar código

    `docker-compose build`

2.  Run the containers:

    bash

    Copiar código

    `docker-compose up -d`

3.  Monitor logs:

    bash

    Copiar código

    `docker-compose logs -f`

Infrastructure Setup
--------------------

Use the provided Terraform files to set up AWS resources:

-   SSM Parameter Store
-   SQS Queues
-   EC2 Instance

Features
--------

### `event_poller/`

-   Monitors Twitch events:
    -   **Messages**: Captures user messages, message IDs, and timestamps.
    -   **Joins**: Detects when users join the chat.
-   Sends event metadata to the SQS input queue.

### `eligibility_processor/`

-   Consumes events from the SQS input queue.
-   Checks if users are in the allowed database (MongoDB Atlas).
-   Sends eligibility results to the SQS output queue.

### `action_handler/`

-   Consumes results from the SQS output queue.
-   Takes actions based on user eligibility:
    -   Times out unauthorized users for 10 hours.
    -   Deletes unauthorized messages.
    -   Sends private messages to unauthorized users.

License
-------

This project is licensed under the MIT License.

* * * * *

### **What's Updated:**

-   Renamed `message_poller` to `event_poller` throughout.
-   Adjusted the description for `event_poller` to include its role in handling both messages and join events.
-   Updated the feature descriptions to align with the current functionality (e.g., timeouts for unauthorized users).

Let me know if you need further changes!