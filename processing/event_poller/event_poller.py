# event_poller.py

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
    return params

def get_twitch_credentials(mongo_connection_string):
    # Connect to MongoDB
    mongo_client = MongoClient(mongo_connection_string)
    db = mongo_client['patrolia']
    config_collection = db['config']

    # Fetch User Tokens
    user_tokens = config_collection.find_one({'_id': 'twitch_user_tokens'})
    if not user_tokens:
        raise Exception("Twitch user tokens not found in MongoDB.")

    # Fetch Bot Configuration
    bot_config = config_collection.find_one({'_id': 'bot_config'})
    if not bot_config:
        raise Exception("Bot configuration not found in MongoDB.")

    return user_tokens, bot_config

def update_user_tokens(config_collection, new_tokens):
    new_tokens['expires_in'] = new_tokens.get('expires_in', 3600)
    new_tokens['obtained_at'] = int(time.time())
    config_collection.update_one(
        {'_id': 'twitch_user_tokens'},
        {'$set': new_tokens}
    )

def refresh_token_if_needed(user_tokens, config_collection):
    current_time = int(time.time())
    token_age = current_time - user_tokens['obtained_at']
    if token_age >= user_tokens['expires_in'] - 300:  # Refresh 5 minutes before expiration
        print("Refreshing access token...")
        new_tokens = refresh_access_token(
            user_tokens['refresh_token'],
            user_tokens['client_id'],
            user_tokens['client_secret']
        )
        update_user_tokens(config_collection, new_tokens)
        return new_tokens['access_token']
    else:
        return user_tokens['access_token']

def main():
    ssm_params = get_ssm_parameters()
    input_queue_url = ssm_params['/patroliaaws/input_queue_url']
    mongo_connection_string = ssm_params['/patroliamongodb/connection_string']

    mongo_client = MongoClient(mongo_connection_string)
    db = mongo_client['patrolia']
    config_collection = db['config']

    user_tokens, bot_config = get_twitch_credentials(mongo_connection_string)
    access_token = refresh_token_if_needed(user_tokens, config_collection)

    # Initialize the bot
    class Patrolia(commands.Bot):

        def __init__(self):
            super().__init__(
                token=access_token,
                client_id=user_tokens['client_id'],
                nick=bot_config['bot_username'],
                prefix='!',
                initial_channels=[bot_config['channel_name']]
            )
            self.sqs = boto3.client('sqs', region_name='eu-west-1')
            self.queue_url = input_queue_url

        async def event_ready(self):
            print(f"Logged in as | {self.nick}")

        async def event_message(self, message):
            if message.echo:
                return

            message_id = message.tags.get('id')  # Message ID
            msg_data = {
                'event_type': 'message',
                'username': message.author.name,
                'message': message.content,
                'timestamp': str(message.timestamp),
                'message_id': message_id
            }
            self.sqs.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(msg_data)
            )

        async def event_join(self, channel, user):
            if user.name.lower() == self.nick.lower():
                return
            msg_data = {
                'event_type': 'join',
                'username': user.name,
                'timestamp': datetime.datetime.utcnow().isoformat()
            }
            self.sqs.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(msg_data)
            )
            print(f"User {user.name} has joined the channel.")

    bot = Patrolia()
    bot.run()

if __name__ == '__main__':
    main()
