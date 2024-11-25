import asyncio
import boto3
import json
import time
from twitchio.ext import commands
import logging

# Set up logging configuration
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger()

class Patrolia(commands.Bot):
    def __init__(self, token, client_id, nick, prefix, initial_channels, sqs_queue_url):
        """Initialize the Patrolia bot."""
        super().__init__(
            token=token,
            client_id=client_id,
            nick=nick,
            prefix=prefix,
            initial_channels=initial_channels
        )
        self.sqs = boto3.client('sqs', region_name='eu-west-1')
        self.queue_url = sqs_queue_url
        self.activity_detected = False  # Tracks recent activity
        self.known_users = set()        # Track known users
        self.poll_interval = 7200       # Start with low frequency (2 hours)

    def send_to_sqs(self, message_body):
        """Encapsulate sending messages to SQS."""
        try:
            self.sqs.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(message_body)
            )
            logger.info(f"Sent message to SQS: {message_body}")
        except Exception as e:
            logger.error(f"Error sending message to SQS: {e}")

    async def event_ready(self):
        """Called when the bot has successfully connected to Twitch."""
        logger.info(f"Bot is ready. Logged in as {self.nick}")
        # Start polling chatters
        asyncio.create_task(self.poll_chatters())

    async def event_message(self, message):
        """Called when a message is received in the channel."""
        logger.info(f"Received message from {message.author.name}: {message.content}")
        if message.echo:
            return  # Ignore bot's own messages

        message_data = {
            'event_type': 'message',
            'username': message.author.name,
            'message': message.content,
            'timestamp': time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        self.send_to_sqs(message_data)
        self.activity_detected = True  # Mark activity as detected only in relevant context

    async def poll_chatters(self):
        """Poll chatters API and send join events to SQS with dynamic polling intervals."""
        logger.info("Starting chatters polling...")
        while True:
            try:
                response = await self.twitch.get_chatters(self.channel_id)
                current_users = {chatter['user_name'] for chatter in response.get('data', [])}
                new_users = current_users - self.known_users
                users_left = self.known_users - current_users

                # Send join events for new users
                for new_user in new_users:
                    join_event = {
                        'event_type': 'join',
                        'username': new_user,
                        'timestamp': time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    }
                    self.send_to_sqs(join_event)
                    self.activity_detected = True  # Mark activity only for relevant events

                # Adjust polling interval based on activity
                if new_users or users_left or self.activity_detected:
                    self.poll_interval = 30  # High activity, poll frequently
                else:
                    self.poll_interval = 7200  # Low activity, poll every 2 hours

                self.activity_detected = False  # Reset activity flag
                self.known_users = current_users  # Update known users

            except Exception as e:
                logger.error(f"Error polling chatters: {e}")

            logger.info(f"Polling interval set to {self.poll_interval} seconds.")
            await asyncio.sleep(self.poll_interval)  # Dynamic sleep interval based on activity

    async def fetch_channel_id(self, channel_name):
        """Fetch the channel ID for the given channel name."""
        async for user_info in self.twitch.get_users(logins=[channel_name]):
            if user_info:
                logger.info(f"Found channel ID for {channel_name}: {user_info.id}")
                return user_info.id
        raise Exception(f"Channel {channel_name} not found.")
