# action_handler.py

import os
import boto3
import json
import time
from twitchAPI.twitch import Twitch
from twitchAPI.oauth import refresh_access_token
from twitchAPI.types import AuthScope
from pymongo import MongoClient

def get_ssm_parameters():
    ssm = boto3.client('ssm', region_name='eu-west-1')
    parameter_names = [
        '/botaws/output_queue_url',
        '/botmongodb/connection_string'
    ]
    response = ssm.get_parameters(
        Names=parameter_names,
        WithDecryption=True
    )
    params = {param['Name']: param['Value'] for param in response['Parameters']}
    return params

def get_mongo_config(mongo_connection_string):
    # Connect to MongoDB
    mongo_client = MongoClient(mongo_connection_string)
    db = mongo_client['twitch_bot']
    config_collection = db['config']
    return config_collection

def get_twitch_credentials(config_collection):
    # Fetch Twitch App Credentials
    app_credentials = config_collection.find_one({'_id': 'twitch_app_credentials'})
    if not app_credentials:
        raise Exception("Twitch app credentials not found in MongoDB.")

    # Fetch User Tokens
    user_tokens = config_collection.find_one({'_id': 'twitch_user_tokens'})
    if not user_tokens:
        raise Exception("Twitch user tokens not found in MongoDB.")

    # Fetch Bot Configuration
    bot_config = config_collection.find_one({'_id': 'bot_config'})
    if not bot_config:
        raise Exception("Bot configuration not found in MongoDB.")

    return app_credentials, user_tokens, bot_config

def update_user_tokens(config_collection, new_tokens):
    new_tokens['expires_in'] = new_tokens.get('expires_in', 3600)
    new_tokens['obtained_at'] = int(time.time())
    config_collection.update_one(
        {'_id': 'twitch_user_tokens'},
        {'$set': new_tokens}
    )

def refresh_token_if_needed(app_credentials, user_tokens, config_collection):
    current_time = int(time.time())
    token_age = current_time - user_tokens['obtained_at']
    if token_age >= user_tokens['expires_in'] - 300:  # Refresh 5 minutes before expiration
        print("Refreshing access token...")
        new_tokens = refresh_access_token(
            user_tokens['refresh_token'],
            app_credentials['client_id'],
            app_credentials['client_secret']
        )
        update_user_tokens(config_collection, new_tokens)
        return new_tokens['access_token']
    else:
        return user_tokens['access_token']

def main():
    ssm_params = get_ssm_parameters()
    output_queue_url = ssm_params['/botaws/output_queue_url']
    mongo_connection_string = ssm_params['/botmongodb/connection_string']

    config_collection = get_mongo_config(mongo_connection_string)
    app_credentials, user_tokens, bot_config = get_twitch_credentials(config_collection)
    access_token = refresh_token_if_needed(app_credentials, user_tokens, config_collection)

    # Initialize Twitch API client
    twitch = Twitch(app_credentials['client_id'], app_credentials['client_secret'])
    twitch.set_user_authentication(
        access_token,
        [
            AuthScope.CHAT_EDIT,
            AuthScope.CHAT_READ,
            AuthScope.MODERATOR_MANAGE_CHAT_MESSAGES,
            AuthScope.USER_MANAGE_WHISPERS,
            AuthScope.MODERATOR_READ_CHATTERS,
            AuthScope.USER_READ_EMAIL,
            AuthScope.MODERATOR_MANAGE_BANNED_USERS
        ],
        user_tokens['refresh_token']
    )

    # Fetch channel ID
    channel_name = bot_config['channel_name']
    user_info = twitch.get_users(logins=[channel_name])
    if user_info['data']:
        channel_id = user_info['data'][0]['id']
    else:
        raise Exception(f"Channel {channel_name} not found.")

    sqs = boto3.client('sqs', region_name='eu-west-1')

    while True:
        response = sqs.receive_message(
            QueueUrl=output_queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20
        )
        messages = response.get('Messages', [])
        for msg in messages:
            body = json.loads(msg['Body'])
            event_type = body.get('event_type')
            username = body['username']
            is_allowed = body['is_allowed']

            try:
                # Get user_id from username
                users = twitch.get_users(logins=[username])
                user_data = users['data'][0] if users['data'] else None
                if user_data:
                    user_id = user_data['id']
                else:
                    print(f"User {username} not found.")
                    continue

                if not is_allowed:
                    # Timeout user for 10 hours (36,000 seconds)
                    try:
                        twitch.ban_user(
                            broadcaster_id=channel_id,
                            moderator_id=channel_id,  # Assuming the bot is a moderator
                            user_id=user_id,
                            reason="You are not allowed to chat in this channel.",
                            duration=36000  # 10 hours in seconds
                        )
                        print(f"User {username} has been timed out for 10 hours.")
                    except Exception as e:
                        print(f"Error timing out user {username}: {e}")

                    # Send a whisper to the user
                    try:
                        twitch.send_whisper(
                            from_user_id=channel_id,
                            to_user_id=user_id,
                            message="You have been timed out for 10 hours because you're not allowed to chat."
                        )
                        print(f"Whisper sent to user {username}.")
                    except Exception as e:
                        print(f"Error sending whisper to user {username}: {e}")
                else:
                    # User is allowed; no action needed
                    pass
            except Exception as e:
                print(f"Error processing user {username}: {e}")

            # Delete message from output queue
            sqs.delete_message(
                QueueUrl=output_queue_url,
                ReceiptHandle=msg['ReceiptHandle']
            )

if __name__ == '__main__':
    main()
