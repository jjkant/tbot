# action_handler.py

import os
import boto3
import json
from twitchAPI.twitch import Twitch
from twitchAPI.types import AuthScope
from twitchAPI.oauth import refresh_access_token

def get_parameters():
    ssm = boto3.client('ssm', region_name='eu-west-1')
    params = ssm.get_parameters(
        Names=[
            '/aws/sqs/output_queue_url',
            '/twitch/client_id',
            '/twitch/client_secret',
            '/twitch/bot_refresh_token',
            '/twitch/channel_id'
        ],
        WithDecryption=True
    )
    return {param['Name']: param['Value'] for param in params['Parameters']}

params = get_parameters()

sqs = boto3.client('sqs', region_name='eu-west-1')
output_queue_url = params['/aws/sqs/output_queue_url']

client_id = params['/twitch/client_id']
client_secret = params['/twitch/client_secret']
channel_id = params['/twitch/channel_id']
bot_refresh_token = params['/twitch/bot_refresh_token']

# Refresh the access token
new_tokens = refresh_access_token(
    bot_refresh_token,
    client_id,
    client_secret
)

bot_access_token = new_tokens['access_token']
bot_refresh_token = new_tokens['refresh_token']

# Update the refresh token in SSM Parameter Store
ssm = boto3.client('ssm', region_name='eu-west-1')
ssm.put_parameter(
    Name='/twitch/bot_refresh_token',
    Value=bot_refresh_token,
    Type='SecureString',
    Overwrite=True
)

# Initialize Twitch API client
twitch = Twitch(client_id, client_secret)
twitch.set_user_authentication(
    bot_access_token,
    [
        AuthScope.CHAT_EDIT,
        AuthScope.CHAT_READ,
        AuthScope.MODERATOR_MANAGE_CHAT_MESSAGES,
        AuthScope.USER_MANAGE_WHISPERS,
        AuthScope.MODERATOR_READ_CHATTERS,
        AuthScope.USER_READ_EMAIL
    ],
    bot_refresh_token
)

def handle_actions():
    while True:
        response = sqs.receive_message(
            QueueUrl=output_queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20
        )
        messages = response.get('Messages', [])
        for msg in messages:
            body = json.loads(msg['Body'])
            username = body['username']
            is_allowed = body['is_allowed']
            message_id = body.get('message_id')

            if not is_allowed:
                try:
                    # Get user_id from username
                    users = twitch.get_users(logins=[username])
                    user_data = users['data'][0] if users['data'] else None
                    if user_data:
                        user_id = user_data['id']

                        # Delete the user's message
                        if message_id:
                            # If message_id is available, delete specific message
                            twitch.delete_chat_messages(
                                broadcaster_id=channel_id,
                                moderator_id=channel_id,  # Assuming the bot is a moderator
                                message_id=message_id
                            )
                        else:
                            # Otherwise, delete all messages from user
                            twitch.delete_chat_messages(
                                broadcaster_id=channel_id,
                                moderator_id=channel_id,
                                user_id=user_id
                            )

                        # Send a whisper to the user
                        twitch.send_whisper(
                            from_user_id=channel_id,
                            to_user_id=user_id,
                            message="Your message was deleted because you're not allowed to chat."
                        )
                    else:
                        print(f"User {username} not found.")
                except Exception as e:
                    print(f"Error processing user {username}: {e}")

            # Delete message from output queue
            sqs.delete_message(
                QueueUrl=output_queue_url,
                ReceiptHandle=msg['ReceiptHandle']
            )

if __name__ == '__main__':
    handle_actions()
