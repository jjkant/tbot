import os
import asyncio
import datetime
import time
from twitchio.ext import commands
import boto3
import json
from pymongo import MongoClient
from twitchAPI.oauth import refresh_access_token

def get_ssm_parameters():
    print("Fetching SSM parameters...")
    ssm = boto3.client('ssm', region_name='eu-west-1')
    parameter_names = [
        '/patroliaaws/input_queue_url',
        '/patroliamongodb/connection_string'
    ]
    response = ssm.get_parameters(
        Names=parameter_names,
        WithDecryption=True
    )
    params = {param['Name']: param['Value'] for param in response['Parameters']}
    print(f"SSM parameters fetched: {params.keys()}")
    return params

def get_twitch_credentials(mongo_connection_string):
    print("Connecting to MongoDB...")
    mongo_client = MongoClient(mongo_connection_string)
    db = mongo_client['patrolia']
    config_collection = db['config']

    print("Fetching Twitch user tokens from MongoDB...")
    user_tokens = config_collection.find_one({'_id': 'twitch_user_tokens'})
    if not user_tokens:
        raise Exception("Twitch user tokens not found in MongoDB.")

    print("Fetching bot configuration from MongoDB...")
    bot_config = config_collection.find_one({'_id': 'bot_config'})
    if not bot_config:
        raise Exception("Bot configuration not found in MongoDB.")

    print("Twitch credentials and bot configuration fetched successfully.")
    return user_tokens, bot_config

def update_user_tokens(config_collection, new_tokens):
    print("Updating user tokens in MongoDB...")
    new_tokens['expires_in'] = new_tokens.get('expires_in', 3600)
    new_tokens['obtained_at'] = int(time.time())
    config_collection.update_one(
        {'_id': 'twitch_user_tokens'},
        {'$set': new_tokens}
    )
    print("User tokens updated successfully.")

def refresh_token_if_needed(user_tokens, config_collection):
    print("Checking if token refresh is needed...")
    current_time = int(time.time())
    token_age = current_time - user_tokens['obtained_at']
    if token_age >= user_tokens['expires_in'] - 300:  # Refresh 5 minutes before expiration
        print("Token expired or near expiry. Refreshing token...")
        new_tokens = refresh_access_token(
            user_tokens['refresh_token'],
            user_tokens['client_id'],
            user_tokens['client_secret']
        )
        update_user_tokens(config_collection, new_tokens)
        print("Access token refreshed successfully.")
        return new_tokens['access_token']
    else:
        print("Access token is still valid.")
        return user_tokens['access_token']

def main():
    print("Starting event poller...")
    ssm_params = get_ssm_parameters()
    input_queue_url = ssm_params['/patroliaaws/input_queue_url']
    mongo_connection_string = ssm_params['/patroliamongodb/connection_string']

    mongo_client = MongoClient(mongo_connection_string)
    db = mongo_client['patrolia']
    config_collection = db['config']

    print("Fetching credentials and bot configuration...")
    user_tokens, bot_config = get_twitch_credentials(mongo_connection_string)
    access_token = refresh_token_if_needed(user_tokens, config_collection)

    print("Initializing Twitch bot...")

    class Patrolia(commands.Bot):
        def __init__(self):
            print("Initializing bot instance...")
            super().__init__(
                token=access_token,
                client_id=user_tokens['client_id'],
                nick=bot_config['bot_username'],
                prefix='!',
                initial_channels=[bot_config['channel_name']]
            )
            print("Bot instance initialized successfully.")
            self.sqs = boto3.client('sqs', region_name='eu-west-1')
            self.queue_url = input_queue_url
            print(f"Connected to SQS. Input queue URL: {self.queue_url}")

        async def event_ready(self):
            print(f"Bot is ready. Logged in as {self.nick}")

        async def event_message(self, message):
            print(f"Received message from {message.author.name}: {message.content}")
            if message.echo:
                print("Ignoring bot's own message.")
                return

            message_id = message.tags.get('id')  # Message ID
            msg_data = {
                'event_type': 'message',
                'username': message.author.name,
                'message': message.content,
                'timestamp': str(message.timestamp),
                'message_id': message_id
            }
            print(f"Sending message event to SQS: {msg_data}")
            self.sqs.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(msg_data)
            )
            print("Message event sent to SQS successfully.")

        async def event_join(self, channel, user):
            print(f"User {user.name} joined the channel.")
            if user.name.lower() == self.nick.lower():
                print("Ignoring bot's own join event.")
                return

            msg_data = {
                'event_type': 'join',
                'username': user.name,
                'timestamp': datetime.datetime.utcnow().isoformat()
            }
            print(f"Sending join event to SQS: {msg_data}")
            self.sqs.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(msg_data)
            )
            print(f"Join event for {user.name} sent to SQS successfully.")

    try:
        bot = Patrolia()
        print("Running bot...")
        bot.run()
    except Exception as e:
        print(f"Error starting bot: {e}")

if __name__ == '__main__':
    main()
