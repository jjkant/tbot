import os
import boto3
import json
import time
import asyncio
from twitchAPI.twitch import Twitch
from twitchAPI.oauth import refresh_access_token
from twitchAPI.type import AuthScope
from pymongo import MongoClient
import logging

# Set up logging configuration
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO  # You can change this to DEBUG, ERROR, etc.
)
logger = logging.getLogger()

def get_ssm_parameters():
    """Fetch parameters from AWS SSM."""
    logger.info("Fetching SSM parameters...")
    ssm = boto3.client('ssm', region_name='eu-west-1')
    parameter_names = [
        '/patroliaaws/output_queue_url',
        '/patroliamongodb/connection_string'
    ]
    try:
        response = ssm.get_parameters(
            Names=parameter_names,
            WithDecryption=True
        )
        params = {param['Name']: param['Value'] for param in response['Parameters']}
        logger.info(f"SSM Parameters fetched: {list(params.keys())}")
        return params
    except Exception as e:
        logger.error(f"Error fetching SSM parameters: {e}")
        raise
    
async def schedule_token_refresh(user_tokens, config_collection, twitch):
    """Schedule token renewal just before it expires."""
    try:
        # Calculate the delay until the token needs to be refreshed
        current_time = int(time.time())
        token_age = current_time - user_tokens['obtained_at']
        delay = max(0, user_tokens['expires_in'] - token_age - 300)  # Refresh 5 minutes early

        logger.info(f"Scheduling token refresh in {delay} seconds...")
        await asyncio.sleep(delay)

        # Refresh the token
        logger.info("Refreshing access token...")
        new_tokens = refresh_access_token(
            user_tokens['refresh_token'],
            user_tokens['client_id'],
            user_tokens['client_secret']
        )
        update_user_tokens(config_collection, new_tokens)
        user_tokens.update(new_tokens)
        logger.info("Access token refreshed successfully.")

        # Update Twitch authentication
        await twitch.set_user_authentication(
            new_tokens['access_token'],
            [
                AuthScope.MODERATOR_MANAGE_CHAT_MESSAGES,
                AuthScope.MODERATOR_MANAGE_BANNED_USERS,
                AuthScope.MODERATOR_READ_CHATTERS,
                AuthScope.CHAT_EDIT,
                AuthScope.CHAT_READ,
                AuthScope.WHISPERS_EDIT
            ],
            new_tokens['refresh_token']
        )

        # Schedule the next refresh
        asyncio.create_task(schedule_token_refresh(user_tokens, config_collection, twitch))

    except Exception as e:
        logger.error(f"Error scheduling token refresh: {e}")

def get_twitch_credentials(config_collection):
    """Fetch Twitch credentials and bot configuration from MongoDB."""
    user_tokens = config_collection.find_one({'_id': 'twitch_user_tokens'})
    if not user_tokens:
        logger.error("Twitch user tokens not found in MongoDB.")
        raise Exception("Twitch user tokens not found in MongoDB.")

    bot_config = config_collection.find_one({'_id': 'bot_config'})
    if not bot_config:
        logger.error("Bot configuration not found in MongoDB.")
        raise Exception("Bot configuration not found in MongoDB.")

    logger.info("Fetched Twitch credentials and bot configuration successfully.")
    return user_tokens, bot_config

def update_user_tokens(config_collection, new_tokens):
    """Update tokens in MongoDB."""
    logger.info("Updating user tokens in MongoDB...")
    new_tokens['expires_in'] = new_tokens.get('expires_in', 3600)
    new_tokens['obtained_at'] = int(time.time())
    try:
        config_collection.update_one(
            {'_id': 'twitch_user_tokens'},
            {'$set': new_tokens}
        )
        logger.info("User tokens updated successfully.")
    except Exception as e:
        logger.error(f"Error updating user tokens: {e}")

def refresh_token_if_needed(user_tokens, config_collection):
    """Refresh access token if expired or near expiration."""
    logger.info("Checking if token refresh is needed...")
    current_time = int(time.time())
    token_age = current_time - user_tokens['obtained_at']
    if token_age >= user_tokens['expires_in'] - 300:  # Refresh 5 minutes before expiration
        logger.info("Access token is near expiry. Refreshing token...")
        try:
            new_tokens = refresh_access_token(
                user_tokens['refresh_token'],
                user_tokens['client_id'],
                user_tokens['client_secret']
            )
            update_user_tokens(config_collection, new_tokens)
            return new_tokens['access_token']
        except Exception as e:
            logger.error(f"Error refreshing access token: {e}")
            raise
    else:
        logger.info("Access token is still valid.")
        return user_tokens['access_token']

async def fetch_channel_id(twitch, channel_name):
    """Fetch the channel ID for the given channel name."""
    try:
        async for user_info in twitch.get_users(logins=[channel_name]):
            if user_info:
                logger.info(f"Found channel ID for {channel_name}: {user_info.id}")
                return user_info.id
        logger.error(f"Channel {channel_name} not found.")
        raise Exception(f"Channel {channel_name} not found.")
    except Exception as e:
        logger.error(f"Error fetching channel ID for {channel_name}: {e}")
        raise

async def handle_user(twitch, channel_id, username, is_allowed):
    """Handle user actions (ban/timeout) based on their status."""
    logger.info(f"Processing user: {username} with allowed status: {is_allowed}")
    try:
        async for user_data in twitch.get_users(logins=[username]):
            if user_data:
                user_id = user_data.id
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
                        logger.info(f"User {username} timed out for 10 hours.")
                    except Exception as e:
                        logger.error(f"Error timing out user {username}: {e}")
                return
            else:
                logger.error(f"User {username} not found.")
    except Exception as e:
        logger.error(f"Error processing user {username}: {e}")


async def main():
    """Main event loop."""
    logger.info("Starting action handler...")
    try:
        ssm_params = get_ssm_parameters()
        output_queue_url = ssm_params['/patroliaaws/output_queue_url']
        mongo_connection_string = ssm_params['/patroliamongodb/connection_string']

        logger.info("Connecting to MongoDB...")
        mongo_client = MongoClient(mongo_connection_string)
        db = mongo_client['patrolia']
        config_collection = db['config']

        user_tokens, bot_config = get_twitch_credentials(config_collection)
        access_token = refresh_token_if_needed(user_tokens, config_collection)

        # Initialize Twitch API client
        twitch = await Twitch(user_tokens['client_id'], user_tokens['client_secret'])
        await twitch.set_user_authentication(
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
        asyncio.create_task(schedule_token_refresh(user_tokens, config_collection, twitch))

        # Fetch channel ID
        channel_name = bot_config['channel_name']
        channel_id = await fetch_channel_id(twitch, channel_name)

        sqs = boto3.client('sqs', region_name='eu-west-1')

        while True:
            response = sqs.receive_message(
                QueueUrl=output_queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20
            )
            messages = response.get('Messages', [])
            logger.info(f"Received {len(messages)} messages from SQS.")
            for msg in messages:
                body = json.loads(msg['Body'])
                username = body['username']
                is_allowed = body['is_allowed']

                try:
                    await handle_user(twitch, channel_id, username, is_allowed)
                except Exception as e:
                    logger.error(f"Error processing user {username}: {e}")

                # Deleting message from the queue after processing
                try:
                    sqs.delete_message(
                        QueueUrl=output_queue_url,
                        ReceiptHandle=msg['ReceiptHandle']
                    )
                    logger.info(f"Message for {username} deleted from SQS.")
                except Exception as e:
                    logger.error(f"Error deleting message from SQS for {username}: {e}")

            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"Error in main process: {e}")

if __name__ == '__main__':
    asyncio.run(main())
