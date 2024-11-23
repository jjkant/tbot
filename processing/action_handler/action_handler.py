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
            '/botaws/output_queue_url',
            '/bottwitch/client_id',
            '/bottwitch/client_secret',
            '/bottwitch/bot_refresh_token',
            '/bottwitch/channel_id'
        ],
        WithDecryption=True
    )
    return {param['Name']: param['Value'] for param in params['Parameters']}

params = get_parameters()

sqs = boto3.client('sqs', region_name='eu-west-1')
output_queue_url = params['/botaws/output_queue_url']

client_id = params['/bottwitch/client_id']
client_secret = params['/bottwitch/client_secret']
channel_id = params['/bottwitch/channel_id']
bot_refresh_token = params['/bottwitch/bot_refresh_token']

# Refresh the access token
new_tokens = refresh_access_token(
    bot_refresh_token,
    client_id,
    client_secret
)

bot_access_token = new_tokens['access_token']
bot_refresh_token = new_tokens['refresh_token']

# Update the refresh token in SSM Parameter Store
ssm.put_parameter(
    Name='/bottwitch/bot_refresh_token',
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
        AuthScope.USER_READ_EMAIL,
        AuthScope.MODERATOR_MANAGE_BANNED_USERS
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
    handle_actions()
