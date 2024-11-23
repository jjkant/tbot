# eligibility_processor.py

import os
import boto3
import json
from pymongo import MongoClient

def get_parameters():
    ssm = boto3.client('ssm', region_name='eu-west-1')
    params = ssm.get_parameters(
        Names=[
            '/botaws/input_queue_url',
            '/botaws/output_queue_url',
            '/botmongodb/connection_string'
        ],
        WithDecryption=True
    )
    return {param['Name']: param['Value'] for param in params['Parameters']}

params = get_parameters()

sqs = boto3.client('sqs', region_name='eu-west-1')
input_queue_url = params['/botaws/input_queue_url']
output_queue_url = params['/botaws/output_queue_url']

mongo_client = MongoClient(params['/botmongodb/connection_string'])
db = mongo_client['twitch_bot']
allowed_users_collection = db['allowed_users']

def process_messages():
    while True:
        response = sqs.receive_message(
            QueueUrl=input_queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20
        )
        messages = response.get('Messages', [])
        for msg in messages:
            body = json.loads(msg['Body'])
            username = body['username']

            # Check if user is allowed to chat using username
            user_record = allowed_users_collection.find_one({'username': username})
            is_allowed = user_record is not None

            result = {
                'username': username,
                'message': body['message'],
                'timestamp': body['timestamp'],
                'message_id': body.get('message_id'),
                'is_allowed': is_allowed
            }

            # Send result to output queue
            sqs.send_message(
                QueueUrl=output_queue_url,
                MessageBody=json.dumps(result)
            )

            # Delete message from input queue
            sqs.delete_message(
                QueueUrl=input_queue_url,
                ReceiptHandle=msg['ReceiptHandle']
            )

if __name__ == '__main__':
    process_messages()
