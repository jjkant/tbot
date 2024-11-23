import json
import os
import time
import boto3
from pymongo import MongoClient
import requests

def lambda_handler(event, context):
    # Check if the event is HTTP-like (has httpMethod)
    if not event.get('httpMethod') or event['httpMethod'] != 'POST':
        return {
            'statusCode': 405,
            'body': json.dumps({'error': 'Method Not Allowed'}),
            'headers': {
                'Content-Type': 'application/json'
            }
        }

    try:
        # Parse the JSON body
        if 'body' not in event:
            raise KeyError("Missing 'body' in event.")
        
        body = json.loads(event['body'])
        client_id = body['client_id']
        client_secret = body['client_secret']
        auth_code = body['code']
    except (json.JSONDecodeError, KeyError) as e:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f'Invalid request body: {str(e)}'}),
            'headers': {
                'Content-Type': 'application/json'
            }
        }

    redirect_uri = os.environ.get('FRONTEND_CALLBACK_URL', '')
    if not redirect_uri:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Redirect URI not configured in environment variables.'}),
            'headers': {
                'Content-Type': 'application/json'
            }
        }

    # Exchange authorization code for tokens
    token_url = "https://id.twitch.tv/oauth2/token"
    payload = {
        'client_id': client_id,
        'client_secret': client_secret,
        'code': auth_code,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri
    }

    try:
        response = requests.post(token_url, data=payload)
        response.raise_for_status()
        token_data = response.json()
    except requests.RequestException as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Failed to exchange authorization code: {str(e)}'}),
            'headers': {
                'Content-Type': 'application/json'
            }
        }

    # Extract tokens
    access_token = token_data.get('access_token')
    refresh_token = token_data.get('refresh_token')
    expires_in = token_data.get('expires_in')

    if not access_token or not refresh_token:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Incomplete token data received.'}),
            'headers': {
                'Content-Type': 'application/json'
            }
        }

    # Update MongoDB
    try:
        mongo_uri = os.environ['MONGODB_CONNECTION_STRING']
        client = MongoClient(mongo_uri)
        db = client['twitch_bot']
        config_collection = db['config']

        config_collection.update_one(
            {'_id': 'twitch_user_tokens'},
            {
                '$set': {
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'access_token': access_token,
                    'refresh_token': refresh_token,
                    'expires_in': expires_in,
                    'obtained_at': int(time.time())
                }
            },
            upsert=True
        )
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Database update failed: {str(e)}'}),
            'headers': {
                'Content-Type': 'application/json'
            }
        }

    # Response to the user
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Tokens successfully updated in MongoDB. You can now close this window.'}),
        'headers': {
            'Content-Type': 'application/json'
        }
    }
