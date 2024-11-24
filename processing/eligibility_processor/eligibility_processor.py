import os
import boto3
import json
from pymongo import MongoClient
import logging

# Set up logging configuration
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO  # You can change this to DEBUG, ERROR, etc.
)
logger = logging.getLogger()

def get_ssm_parameters():
    logger.info("Fetching SSM parameters...")
    ssm = boto3.client('ssm', region_name='eu-west-1')
    parameter_names = [
        '/patroliaaws/input_queue_url',
        '/patroliaaws/output_queue_url',
        '/patroliamongodb/connection_string'
    ]
    try:
        response = ssm.get_parameters(
            Names=parameter_names,
            WithDecryption=True
        )
        params = {param['Name']: param['Value'] for param in response['Parameters']}
        logger.info(f"SSM parameters fetched successfully: {list(params.keys())}")
        return params
    except Exception as e:
        logger.error(f"Error fetching SSM parameters: {e}")
        raise

def main():
    try:
        # Fetch parameters from SSM
        ssm_params = get_ssm_parameters()
        input_queue_url = ssm_params['/patroliaaws/input_queue_url']
        output_queue_url = ssm_params['/patroliaaws/output_queue_url']
        mongo_connection_string = ssm_params['/patroliamongodb/connection_string']

        logger.info("Connecting to MongoDB...")
        # Connect to MongoDB
        mongo_client = MongoClient(mongo_connection_string)
        db = mongo_client['patrolia']
        allowed_users_collection = db['allowed_users']

        # Initialize the SQS client
        sqs = boto3.client('sqs', region_name='eu-west-1')
        logger.info(f"Connected to SQS. Input Queue URL: {input_queue_url}, Output Queue URL: {output_queue_url}")

        while True:
            logger.info("Polling messages from input queue...")
            # Receive messages from SQS
            response = sqs.receive_message(
                QueueUrl=input_queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20
            )

            messages = response.get('Messages', [])
            logger.info(f"Received {len(messages)} messages.")
            for msg in messages:
                try:
                    body = json.loads(msg['Body'])
                    event_type = body.get('event_type')
                    username = body['username']
                    logger.info(f"Processing {event_type} event for user: {username}")

                    # Check if the user is allowed to chat
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
                        logger.info(f"Processed message event: {result}")
                    elif event_type == 'join':
                        result.update({
                            'timestamp': body['timestamp']
                        })
                        logger.info(f"Processed join event: {result}")

                    # Send result to output queue
                    sqs.send_message(
                        QueueUrl=output_queue_url,
                        MessageBody=json.dumps(result)
                    )
                    logger.info(f"Result sent to output queue for {username}.")

                    # Delete message from input queue
                    sqs.delete_message(
                        QueueUrl=input_queue_url,
                        ReceiptHandle=msg['ReceiptHandle']
                    )
                    logger.info(f"Message for {username} deleted from input queue.")

                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    continue

    except Exception as e:
        logger.error(f"Error in main process: {e}")

if __name__ == '__main__':
    main()
