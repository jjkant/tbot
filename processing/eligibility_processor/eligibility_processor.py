# eligibility_processor.py

import os
import boto3
import json
from pymongo import MongoClient

def get_ssm_parameters():
    ssm = boto3.client('ssm', region_name='eu-west-1')
    parameter_names = [
        '/botaws/input_queue_url',
        '/botaws/output_queue_url',
        '/botmongodb/connection_string'
    ]
    response = ssm.get_parameters(
        Names=parameter_names,
        WithDecryption=True
    )
    params = {param['Name']: param['Value'] for param in response['Parameters']}
    return params

def main():
    ssm_params = get_ssm_parameters()
    input_queue_url = ssm_params['/botaws/input_queue_url']
    output_queue_url = ssm_params['/botaws/output_queue_url']
    mongo_connection_string = ssm_params['/botmongodb/connection_string']

    # Connect to MongoDB
    mongo_client = MongoClient(mongo_connection_string)
    db = mongo_client['twitch_bot']
    allowed_users_collection = db['allowed_users']

    sqs = boto3.client('sqs', region_name='eu-west-1')

    while True:
        response = sqs.receive_message(
            QueueUrl=input_queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20
        )
        messages = response.get('Messages', [])
        for msg in messages:
            body = json.loads(msg['Body'])
            event_type = body.get('event_type')
            username = body['username']

            # Check if user is allowed to chat using username
            user_record = allowed_users_collection.find_one({'username': username})
            is_allowed = user_record is not None

            result = {
                'event_type': event_type,
                'username': username,
                'is_allowed': is_allowed
            }

            if event_type == 'message':
                result.update({
                    'message': body['message'],
                    'timestamp': body['timestamp'],
                    'message_id': body.get('message_id')
                })
            elif event_type == 'join':
                result.update({
                    'timestamp': body['timestamp']
                })

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
    main()
