import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from urllib.parse import quote

from src.handler import handler


class TestEmailVerificationHandler(unittest.TestCase):
    """Unit tests for the email verification Lambda handler."""

    def setUp(self):
        """Set up test fixtures and mock environment variables."""
        self.email = 'test@example.com'
        self.token = 'test-token-12345'
        self.verification_url = 'https://example.com/verify'
        
        # Set environment variables
        os.environ['EMAIL_VERIFICATION_URL'] = self.verification_url
        os.environ['DYNAMODB_TABLE_NAME'] = 'EmailVerification'
        os.environ['SES_FROM_DOMAIN'] = 'noreply@example.com'

    def _create_sns_event(self, email, token):
        """Helper to create a valid SNS event."""
        sns_message = {
            'email': email,
            'token': token
        }
        return {
            'Records': [
                {
                    'Sns': {
                        'Message': json.dumps(sns_message)
                    }
                }
            ]
        }

    @patch('src.handler.boto3.client')
    @patch('src.handler.boto3.resource')
    def test_happy_path_new_email(self, mock_resource, mock_client):
        """
        Test happy path: new email, DynamoDB returns no record, 
        SES sends, DynamoDB writes successfully.
        """
        # Mock DynamoDB
        mock_dynamodb = MagicMock()
        mock_resource.return_value = mock_dynamodb
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {}  # No existing item
        mock_table.put_item.return_value = None  # Success
        
        # Mock SES
        mock_ses = MagicMock()
        mock_client.return_value = mock_ses
        mock_ses.send_email.return_value = {'MessageId': 'test-message-id'}
        
        # Create event
        event = self._create_sns_event(self.email, self.token)
        
        # Call handler
        response = handler(event, None)
        
        # Assertions
        self.assertEqual(response['statusCode'], 200)
        body = json.loads(response['body'])
        self.assertIn('message', body)
        self.assertIn('successfully', body['message'])
        
        # Verify DynamoDB was queried
        mock_table.get_item.assert_called_once_with(Key={'email': self.email})
        
        # Verify SES was called
        mock_ses.send_email.assert_called_once()
        call_args = mock_ses.send_email.call_args
        self.assertEqual(call_args[1]['Destination']['ToAddresses'][0], self.email)
        self.assertEqual(call_args[1]['Source'], 'noreply@example.com')
        
        # Verify DynamoDB write was called
        mock_table.put_item.assert_called_once()
        put_item_call = mock_table.put_item.call_args
        item = put_item_call[1]['Item']
        self.assertEqual(item['email'], self.email)
        self.assertEqual(item['token'], self.token)
        self.assertFalse(item['verified'])

    @patch('src.handler.boto3.client')
    @patch('src.handler.boto3.resource')
    def test_duplicate_email_path(self, mock_resource, mock_client):
        """
        Test duplicate path: DynamoDB returns existing record, 
        function returns early, SES is never called.
        """
        # Mock DynamoDB with existing item
        mock_dynamodb = MagicMock()
        mock_resource.return_value = mock_dynamodb
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {
            'Item': {
                'email': self.email,
                'token': 'old-token',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'verified': False
            }
        }
        
        # Mock SES
        mock_ses = MagicMock()
        mock_client.return_value = mock_ses
        
        # Create event
        event = self._create_sns_event(self.email, self.token)
        
        # Call handler
        response = handler(event, None)
        
        # Assertions - should return 409 Conflict
        self.assertEqual(response['statusCode'], 409)
        body = json.loads(response['body'])
        self.assertIn('message', body)
        
        # Verify SES was NOT called
        mock_ses.send_email.assert_not_called()
        
        # Verify DynamoDB put_item was NOT called
        mock_table.put_item.assert_not_called()

    @patch('src.handler.boto3.client')
    @patch('src.handler.boto3.resource')
    def test_missing_email_field(self, mock_resource, mock_client):
        """Test missing fields path: SNS message has no email, returns 400."""
        # Mock DynamoDB (for precision in assertions)
        mock_dynamodb = MagicMock()
        mock_resource.return_value = mock_dynamodb
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        
        # Mock SES
        mock_ses = MagicMock()
        mock_client.return_value = mock_ses
        
        # Create event with missing email
        sns_message = {'token': self.token}
        event = {
            'Records': [
                {
                    'Sns': {
                        'Message': json.dumps(sns_message)
                    }
                }
            ]
        }
        
        # Call handler
        response = handler(event, None)
        
        # Assertions
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('error', body)
        self.assertIn('Missing', body['error'])
        
        # Verify DynamoDB get_item was never called (validation failed early)
        mock_table.get_item.assert_not_called()
        mock_ses.send_email.assert_not_called()

    @patch('src.handler.boto3.client')
    @patch('src.handler.boto3.resource')
    def test_missing_token_field(self, mock_resource, mock_client):
        """Test missing fields path: SNS message has no token, returns 400."""
        # Mock DynamoDB (for precision in assertions)
        mock_dynamodb = MagicMock()
        mock_resource.return_value = mock_dynamodb
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        
        # Mock SES
        mock_ses = MagicMock()
        mock_client.return_value = mock_ses
        
        # Create event with missing token
        sns_message = {'email': self.email}
        event = {
            'Records': [
                {
                    'Sns': {
                        'Message': json.dumps(sns_message)
                    }
                }
            ]
        }
        
        # Call handler
        response = handler(event, None)
        
        # Assertions
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('error', body)
        self.assertIn('Missing', body['error'])
        
        # Verify DynamoDB get_item was never called (validation failed early)
        mock_table.get_item.assert_not_called()
        mock_ses.send_email.assert_not_called()

    @patch('src.handler.boto3.client')
    @patch('src.handler.boto3.resource')
    def test_ses_failure_path(self, mock_resource, mock_client):
        """
        Test SES failure path: SES throws an exception, 
        function catches it and returns 500.
        """
        # Mock DynamoDB
        mock_dynamodb = MagicMock()
        mock_resource.return_value = mock_dynamodb
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {}  # No existing item
        
        # Mock SES to raise an exception
        mock_ses = MagicMock()
        mock_client.return_value = mock_ses
        mock_ses.send_email.side_effect = Exception('SES service error')
        
        # Create event
        event = self._create_sns_event(self.email, self.token)
        
        # Call handler
        response = handler(event, None)
        
        # Assertions
        self.assertEqual(response['statusCode'], 500)
        body = json.loads(response['body'])
        self.assertIn('error', body)
        
        # Verify SES was called
        mock_ses.send_email.assert_called_once()
        
        # Verify DynamoDB put_item was NOT called (SES failed before that)
        mock_table.put_item.assert_not_called()

    @patch('src.handler.boto3.client')
    @patch('src.handler.boto3.resource')
    def test_dynamodb_write_failure_path(self, mock_resource, mock_client):
        """
        Test DynamoDB write failure path: SES succeeds but DynamoDB write throws,
        function catches and returns 500.
        """
        # Mock DynamoDB
        mock_dynamodb = MagicMock()
        mock_resource.return_value = mock_dynamodb
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {}  # No existing item
        mock_table.put_item.side_effect = Exception('DynamoDB write error')
        
        # Mock SES
        mock_ses = MagicMock()
        mock_client.return_value = mock_ses
        mock_ses.send_email.return_value = {'MessageId': 'test-message-id'}
        
        # Create event
        event = self._create_sns_event(self.email, self.token)
        
        # Call handler
        response = handler(event, None)
        
        # Assertions
        self.assertEqual(response['statusCode'], 500)
        body = json.loads(response['body'])
        self.assertIn('error', body)
        
        # Verify SES was called (email still sent)
        mock_ses.send_email.assert_called_once()
        
        # Verify DynamoDB put_item was attempted
        mock_table.put_item.assert_called_once()

    @patch('src.handler.boto3.client')
    @patch('src.handler.boto3.resource')
    def test_verification_link_format(self, mock_resource, mock_client):
        """Test that verification link is correctly formatted in SES email."""
        # Mock DynamoDB
        mock_dynamodb = MagicMock()
        mock_resource.return_value = mock_dynamodb
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_table.get_item.return_value = {}
        mock_table.put_item.return_value = None
        
        # Mock SES
        mock_ses = MagicMock()
        mock_client.return_value = mock_ses
        mock_ses.send_email.return_value = {'MessageId': 'test-message-id'}
        
        # Create event
        event = self._create_sns_event(self.email, self.token)
        
        # Call handler
        response = handler(event, None)
        
        # Get the call arguments to SES
        call_args = mock_ses.send_email.call_args
        message_body = call_args[1]['Message']['Body']['Html']['Data']
        
        # Verify the link is correctly constructed
        expected_link = f"{self.verification_url}/v1/validateEmail?email={quote(self.email, safe='')}&token={self.token}"
        self.assertIn(expected_link, message_body)

    @patch('src.handler.boto3.client')
    @patch('src.handler.boto3.resource')
    def test_empty_email_string(self, mock_resource, mock_client):
        """Test that empty email string is treated as missing field."""
        # Mock DynamoDB
        mock_dynamodb = MagicMock()
        mock_resource.return_value = mock_dynamodb
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        
        # Mock SES
        mock_ses = MagicMock()
        mock_client.return_value = mock_ses
        
        # Create event with empty email
        sns_message = {'email': '', 'token': self.token}
        event = {
            'Records': [
                {
                    'Sns': {
                        'Message': json.dumps(sns_message)
                    }
                }
            ]
        }
        
        # Call handler
        response = handler(event, None)
        
        # Assertions
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('error', body)

    @patch('src.handler.boto3.client')
    @patch('src.handler.boto3.resource')
    def test_empty_token_string(self, mock_resource, mock_client):
        """Test that empty token string is treated as missing field."""
        # Mock DynamoDB
        mock_dynamodb = MagicMock()
        mock_resource.return_value = mock_dynamodb
        mock_table = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        
        # Mock SES
        mock_ses = MagicMock()
        mock_client.return_value = mock_ses
        
        # Create event with empty token
        sns_message = {'email': self.email, 'token': ''}
        event = {
            'Records': [
                {
                    'Sns': {
                        'Message': json.dumps(sns_message)
                    }
                }
            ]
        }
        
        # Call handler
        response = handler(event, None)
        
        # Assertions
        self.assertEqual(response['statusCode'], 400)
        body = json.loads(response['body'])
        self.assertIn('error', body)


if __name__ == '__main__':
    unittest.main()
