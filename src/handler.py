import json
import logging
import os
import traceback
from datetime import datetime, timezone

import boto3
from pythonjsonlogger import jsonlogger

# Set up JSON logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
ses_client = boto3.client('ses')

# Read environment variables
EMAIL_VERIFICATION_URL = os.getenv('EMAIL_VERIFICATION_URL')
DYNAMODB_TABLE_NAME = os.getenv('DYNAMODB_TABLE_NAME')
SES_FROM_DOMAIN = os.getenv('SES_FROM_DOMAIN')


def handler(event, context):
    """
    Lambda handler for email verification email sending.
    Processes SNS events containing email verification requests.
    """
    try:
        # Log raw event as JSON
        logger.info('Received SNS event', extra={'raw_event': event})
        
        # Parse SNS event to extract inner JSON payload
        sns_message = json.loads(event['Records'][0]['Sns']['Message'])
        logger.info('Parsed SNS message', extra={'sns_message': sns_message})
        
        # Extract email and token from payload
        email = sns_message.get('email')
        token = sns_message.get('token')
        
        logger.info('Extracted email and token', extra={
            'email': email,
            'token': token
        })
        
        # Validate required fields
        if not email or not token:
            logger.error('Missing required fields', extra={
                'email': email,
                'token': token
            })
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing email or token'})
            }
        
        # Construct the verification link
        verification_link = f"{EMAIL_VERIFICATION_URL}/validateEmail?email={email}&token={token}"
        logger.info('Constructed verification link', extra={
            'email': email,
            'verification_link': verification_link
        })
        
        # Check DynamoDB for existing record
        table = dynamodb.Table(DYNAMODB_TABLE_NAME)
        response = table.get_item(Key={'email': email})
        logger.info('DynamoDB query result', extra={
            'email': email,
            'item_exists': 'Item' in response
        })
        
        # If record already exists, prevent duplicate
        if 'Item' in response:
            logger.warning('Duplicate email record found', extra={
                'email': email,
                'message': 'Email verification already processed'
            })
            return {
                'statusCode': 409,
                'body': json.dumps({'message': 'Email already verified or in progress'})
            }
        
        # Send verification email via SES
        try:
            logger.info('Attempting to send SES email', extra={
                'email': email,
                'from_domain': SES_FROM_DOMAIN
            })
            
            ses_response = ses_client.send_email(
                Source=SES_FROM_DOMAIN,
                Destination={'ToAddresses': [email]},
                Message={
                    'Subject': {'Data': 'Email Verification'},
                    'Body': {
                        'Html': {
                            'Data': f'''
                            <html>
                                <body>
                                    <p>Please verify your email by clicking the link below:</p>
                                    <a href="{verification_link}">Verify Email</a>
                                </body>
                            </html>
                            '''
                        }
                    }
                }
            )
            
            logger.info('SES email sent successfully', extra={
                'email': email,
                'message_id': ses_response['MessageId']
            })
            
        except Exception as ses_error:
            logger.error('SES email send failed', extra={
                'email': email,
                'error_type': type(ses_error).__name__,
                'error_message': str(ses_error)
            })
            raise
        
        # Write email record to DynamoDB to block duplicates
        try:
            table.put_item(
                Item={
                    'email': email,
                    'token': token,
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'verified': False
                }
            )
            
            logger.info('Email record written to DynamoDB', extra={
                'email': email,
                'token': token,
                'verified': False
            })
            
        except Exception as dynamo_error:
            logger.error('DynamoDB write failed', extra={
                'email': email,
                'error_type': type(dynamo_error).__name__,
                'error_message': str(dynamo_error)
            })
            raise
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Email verification sent successfully'})
        }
        
    except Exception as error:
        logger.error('Lambda handler error', extra={
            'error_type': type(error).__name__,
            'error_message': str(error),
            'stack_trace': traceback.format_exc()
        })
        
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }
