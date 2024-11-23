import json
import os
import time
import boto3
from pymongo import MongoClient
import requests

def lambda_handler(event, context):
    if event['httpMethod'] != 'POST':
        return {
            'statusCode': 405,
            'body': json.dumps({'error': 'Method Not Allowed'}),
            'headers': {
                'Content-Type': 'application/json'
            }
        }

    try:
        body = json.loads(event['body'])
        client_id = body['client_id']
        client_secret = body['client_secret']
        auth_code = body['code']
    except (json.JSONDecodeError, KeyError) as e:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid request body'}),
            'headers': {
                'Content-Type': 'application/json'
            }
        }

    redirect_uri = os.environ['FRONTEND_CALLBACK_URL']  # Must match the redirect URI used in the OAuth flow

    # Exchange authorization code for tokens
    token_url = "https://id.twitch.tv/oauth2/token"
    payload = {
        'client_id': client_id,
        'client_secret': client_secret,
        'code': auth_code,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri
    }

    response = requests.post(token_url, data=payload)
    if response.status_code != 200:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Failed to exchange authorization code.'}),
            'headers': {
                'Content-Type': 'application/json'
            }
        }

    token_data = response.json()
    access_token = token_data['access_token']
    refresh_token = token_data['refresh_token']
    expires_in = token_data['expires_in']

    # Update MongoDB
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

    # Response to the user
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Tokens successfully updated in MongoDB. You can now close this window.'}),
        'headers': {
            'Content-Type': 'application/json'
        }
    }
