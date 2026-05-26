# Getting Started

## Local Setup

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Development Dependencies

```bash
pip install -r requirements-dev.txt
```

### 3. Build Docker Image Locally

```bash
docker build -t email-verification-lambda:latest .
```

Verify the image was created:

```bash
docker images | grep email-verification-lambda
```

## Code Quality

### Run Code Linting and Formatting

Before committing or running tests, ensure code passes flake8 linting checks:

```bash
# Auto-format code to PEP 8 standards
autopep8 --in-place --max-line-length=127 src/handler.py

# Run flake8 lint check
flake8 src/handler.py --max-line-length=127
```

These checks are required by the GitHub Actions workflow. Running them locally prevents CI failures.

## Testing

### Run Unit Tests

```bash
# Run pytest
pytest tests/ -v
```

All tests must pass before code can be merged. Tests validate:

- Happy path: email sends and DynamoDB record created
- Duplicate prevention: existing emails return 409
- Missing fields: invalid input returns 400
- Error handling: SES and DynamoDB failures return 500

### Test Locally with Docker

Run a test container with sample event:

```bash
# Create a test event file (test_event.json)
cat > test_event.json << 'EOF'
{
  "Records": [
    {
      "Sns": {
        "Message": "{\"email\":\"test@example.com\",\"token\":\"abc123xyz\"}"
      }
    }
  ]
}
EOF

# Run the Lambda function locally
docker run --rm \
  -e EMAIL_VERIFICATION_URL="https://example.com" \
  -e DYNAMODB_TABLE_NAME="EmailVerification" \
  -e SES_FROM_DOMAIN="example.com" \
  -v ~/.aws/credentials:/root/.aws/credentials:ro \
  email-verification-lambda:latest \
  handler.handler
```

## Deployment

### 1. Push to Dev Account ECR

```bash
# Login to dev account ECR
aws ecr get-login-password --region $AWS_REGION --profile dev | \
  docker login --username AWS --password-stdin $DEV_ECR_REGISTRY

# Tag image
docker tag email-verification-lambda:latest $DEV_ECR_REGISTRY/email-verification:latest
docker tag email-verification-lambda:latest $DEV_ECR_REGISTRY/email-verification:$(git rev-parse --short HEAD)

# Push to dev ECR
docker push $DEV_ECR_REGISTRY/email-verification:latest
docker push $DEV_ECR_REGISTRY/email-verification:$(git rev-parse --short HEAD)
```

### 2. Push to Demo Account ECR

```bash
# Login to demo account ECR
aws ecr get-login-password --region $AWS_REGION --profile demo | \
  docker login --username AWS --password-stdin $DEMO_ECR_REGISTRY

# Tag for demo
docker tag email-verification-lambda:latest $DEMO_ECR_REGISTRY/email-verification:latest
docker tag email-verification-lambda:latest $DEMO_ECR_REGISTRY/email-verification:$(git rev-parse --short HEAD)

# Push to demo ECR
docker push $DEMO_ECR_REGISTRY/email-verification:latest
docker push $DEMO_ECR_REGISTRY/email-verification:$(git rev-parse --short HEAD)
```

## Environment Variables

Configure these environment variables in Lambda or .env file:

| Variable                 | Description                                                      |
| ------------------------ | ---------------------------------------------------------------- |
| `EMAIL_VERIFICATION_URL` | Base URL for verification links (e.g., `https://myapp.com`)      |
| `DYNAMODB_TABLE_NAME`    | DynamoDB table storing email verification records                |
| `SES_FROM_DOMAIN`        | Domain for sending emails from SES (e.g., `noreply@example.com`) |

## GitHub Actions Workflow

The workflow in `.github/workflows/deploy.yml` automatically:

1. Builds the Docker image on merge to `main`
2. Tags with `:latest` and git SHA short hash
3. Pushes to dev account ECR
4. Pushes to demo account ECR

### Required GitHub Secrets

```
AWS_DEV_ACCESS_KEY_ID
AWS_DEV_SECRET_ACCESS_KEY
AWS_DEMO_ACCESS_KEY_ID
AWS_DEMO_SECRET_ACCESS_KEY
AWS_REGION
DEV_ECR_REGISTRY
DEMO_ECR_REGISTRY
```

## Lambda Configuration

### Memory and Timeout

- Memory: 512 MB (recommended for email operations)
- Timeout: 60 seconds

### IAM Permissions Required

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:PutItem"],
      "Resource": "arn:aws:dynamodb:*:*:table/EmailVerification"
    },
    {
      "Effect": "Allow",
      "Action": ["ses:SendEmail"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

## Monitoring and Logs

Logs are output as JSON using `python-json-logger` for easy parsing in CloudWatch Logs. Example log entry:

```json
{
  "email": "user@example.com",
  "token": "abc123xyz",
  "message_id": "010001796b2f3b42-1234567890",
  "levelname": "INFO",
  "name": "__main__",
  "asctime": "2026-04-02T10:30:45Z"
}
```

## Troubleshooting

### SES Email Not Sending

- Ensure SES is verified in the target AWS account and region
- Check IAM permissions for `ses:SendEmail`
- Verify `SES_FROM_DOMAIN` matches verified sender domain

### DynamoDB Errors

- Verify DynamoDB table exists and has correct name
- Check IAM permissions for `dynamodb:GetItem` and `dynamodb:PutItem`
- Ensure table has `email` as partition key

### Image Push Failures

- Verify AWS credentials for both accounts
- Check ECR repository exists in target account
- Ensure Docker daemon is running
