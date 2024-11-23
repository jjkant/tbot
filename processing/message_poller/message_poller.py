# message_poller.py

import os
import asyncio
from twitchio.ext import commands
import boto3
import json

def get_parameters():
    ssm = boto3.client('ssm', region_name='eu-west-1')
    params = ssm.get_parameters(
        Names=[
            '/bottwitch/bot_oauth_token',
            '/bottwitch/client_id',
            '/bottwitch/channel_name',
            '/botaws/input_queue_url'
        ],
        WithDecryption=True
    )
    return {param['Name']: param['Value'] for param in params['Parameters']}

params = get_parameters()

sqs = boto3.client('sqs', region_name='eu-west-1')
queue_url = params['/botaws/input_queue_url']

class TwitchBot(commands.Bot):

    def __init__(self):
        super().__init__(
            token=params['/bottwitch/bot_oauth_token'],
            client_id=params['/bottwitch/client_id'],
            nick='YourBotNick',
            prefix='!',
            initial_channels=[params['/bottwitch/channel_name']]
        )

    async def event_ready(self):
        print(f"Logged in as | {self.nick}")

    async def event_message(self, message):
        if message.echo:
            return

        # Get message_id if available
        message_id = message.tags.get('id')  # Message ID

        msg_data = {
            'username': message.author.name,
            'message': message.content,
            'timestamp': str(message.timestamp),
            'message_id': message_id
        }

        # Send message data to SQS
        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(msg_data)
        )

if __name__ == '__main__':
    bot = TwitchBot()
    bot.run()
