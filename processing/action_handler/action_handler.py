import os
import boto3
import json
import time
import asyncio
from twitchAPI.twitch import Twitch
from twitchAPI.oauth import refresh_access_token
from twitchAPI.type import AuthScope
from pymongo import MongoClient

def get_ssm_parameters():
    """Fetch parameters from AWS SSM."""
    ssm = boto3.client('ssm', region_name='eu-west-1')
    parameter_names = [
        '/patroliaaws/output_queue_url',
        '/patroliamongodb/connection_string'
    ]
    response = ssm.get_parameters(
        Names=parameter_names,
        WithDecryption=True
    )
    params = {param['Name']: param['Value'] for param in response['Parameters']}
    print(f"SSM Parameters fetched: {params.keys()}")
    return params

def get_twitch_credentials(mongo_connection_string):
    """Fetch Twitch credentials and bot configuration from MongoDB."""
    mongo_client = MongoClient(mongo_connection_string)
    db = mongo_client['patrolia']
    config_collection = db['config']

    user_tokens = config_collection.find_one({'_id': 'twitch_user_tokens'})
    if not user_tokens:
        raise Exception("Twitch user tokens not found in MongoDB.")

    bot_config = config_collection.find_one({'_id': 'bot_config'})
    if not bot_config:
        raise Exception("Bot configuration not found in MongoDB.")

    return user_tokens, bot_config

def update_user_tokens(config_collection, new_tokens):
    """Update tokens in MongoDB."""
    new_tokens['expires_in'] = new_tokens.get('expires_in', 3600)
    new_tokens['obtained_at'] = int(time.time())
    config_collection.update_one(
        {'_id': 'twitch_user_tokens'},
        {'$set': new_tokens}
    )
    print("User tokens updated in MongoDB.")

def refresh_token_if_needed(user_tokens, config_collection):
    """Refresh access token if expired or near expiration."""
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
        print("Access token is still valid.")
        return user_tokens['access_token']

async def fetch_channel_id(twitch, channel_name):
    """Fetch the channel ID for the given channel name."""
    async for user_info in twitch.get_users(logins=[channel_name]):
        if user_info.get('data'):
            return user_info['data'][0]['id']
    raise Exception(f"Channel {channel_name} not found.")

async def handle_user(twitch, channel_id, username, is_allowed):
    """Handle user actions (ban/timeout) based on their status."""
    async for user_data in twitch.get_users(logins=[username]):
        if user_data.get('data'):
            user_id = user_data['data'][0]['id']
            if not is_allowed:
                try:
                    # Timeout user for 10 hours
                    await twitch.ban_user(
                        broadcaster_id=channel_id,
                        moderator_id=channel_id,
                        user_id=user_id,
                        reason="You are not allowed to chat.",
                        duration=36000
                    )
                    print(f"User {username} timed out for 10 hours.")
                except Exception as e:
                    print(f"Error timing out user {username}: {e}")
                return
        else:
            print(f"User {username} not found.")

async def main():
    """Main event loop."""
    print("Starting action handler...")
    ssm_params = get_ssm_parameters()
    output_queue_url = ssm_params['/patroliaaws/output_queue_url']
    mongo_connection_string = ssm_params['/patroliamongodb/connection_string']

    mongo_client = MongoClient(mongo_connection_string)
    db = mongo_client['patrolia']
    config_collection = db['config']

    user_tokens, bot_config = get_twitch_credentials(mongo_connection_string)
    access_token = refresh_token_if_needed(user_tokens, config_collection)

    # Initialize Twitch API client
    twitch = await Twitch(user_tokens['client_id'], user_tokens['client_secret'])
    twitch.set_user_authentication(
        access_token,
        [
            AuthScope.MODERATOR_MANAGE_CHAT_MESSAGES,
            AuthScope.MODERATOR_MANAGE_BANNED_USERS,
            AuthScope.MODERATOR_READ_CHATTERS,
            AuthScope.CHAT_EDIT,
            AuthScope.CHAT_READ,
            AuthScope.WHISPERS_EDIT
        ],
        user_tokens['refresh_token']
    )

    # Fetch channel ID
    channel_name = bot_config['channel_name']
    channel_id = await fetch_channel_id(twitch, channel_name)
    print(f"Channel ID for {channel_name}: {channel_id}")

    sqs = boto3.client('sqs', region_name='eu-west-1')

    while True:
        response = sqs.receive_message(
            QueueUrl=output_queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20
        )
        messages = response.get('Messages', [])
        print(f"Received {len(messages)} messages from SQS.")
        for msg in messages:
            body = json.loads(msg['Body'])
            username = body['username']
            is_allowed = body['is_allowed']

            try:
                await handle_user(twitch, channel_id, username, is_allowed)
            except Exception as e:
                print(f"Error processing user {username}: {e}")

            sqs.delete_message(
                QueueUrl=output_queue_url,
                ReceiptHandle=msg['ReceiptHandle']
            )
        await asyncio.sleep(1)

if __name__ == '__main__':
    asyncio.run(main())
