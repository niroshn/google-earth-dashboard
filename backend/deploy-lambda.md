# AWS Lambda Deployment Instructions

## Prerequisites

1. **AWS CLI** installed and configured
2. **Google Earth Engine Service Account** JSON key file
3. **AWS IAM permissions** for Lambda deployment

## Deployment Steps

### 1. Prepare Service Account

1. Create GEE service account in Google Cloud Console
2. Download the JSON key file
3. Convert to base64 for Lambda environment variable:
   ```bash
   base64 -w 0 your-service-account.json > service-account-base64.txt
   ```

### 2. Package Lambda Function

```bash
# Navigate to backend directory
cd backend

# Create deployment package directory
mkdir lambda-deployment
cd lambda-deployment

# Install dependencies
pip install earthengine-api python-dotenv -t .

# Copy Lambda function
cp ../lambda_function.py .

# Create deployment zip
zip -r gee-mapper-lambda.zip .
```

### 3. Create Lambda Function

```bash
# Create Lambda function
aws lambda create-function \
  --function-name gee-mapper \
  --runtime python3.9 \
  --role arn:aws:iam::YOUR_ACCOUNT:role/lambda-execution-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://gee-mapper-lambda.zip \
  --timeout 30 \
  --memory-size 512

# Set environment variables
aws lambda update-function-configuration \
  --function-name gee-mapper \
  --environment Variables='{
    "GOOGLE_EARTH_ENGINE_PROJECT_ID":"your-gee-project-id",
    "GOOGLE_SERVICE_ACCOUNT":"your-base64-encoded-service-account-json"
  }'
```

### 4. Create API Gateway

```bash
# Create REST API
aws apigateway create-rest-api --name gee-mapper-api

# Get the API ID from output, then create resources and methods
# This requires multiple API Gateway setup commands...
```

### 5. Alternative: Use AWS SAM Template

Create `template.yaml`:

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  GEEMapperFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: lambda-deployment/
      Handler: lambda_function.lambda_handler
      Runtime: python3.9
      Timeout: 30
      MemorySize: 512
      Environment:
        Variables:
          GOOGLE_EARTH_ENGINE_PROJECT_ID: !Ref GEEProjectId
          GOOGLE_SERVICE_ACCOUNT: !Ref ServiceAccountKey
      Events:
        MapApi:
          Type: Api
          Properties:
            Path: /api/map
            Method: get
        PixelValueApi:
          Type: Api
          Properties:
            Path: /api/pixel_value
            Method: get

Parameters:
  GEEProjectId:
    Type: String
    Description: Google Earth Engine Project ID
  ServiceAccountKey:
    Type: String
    Description: Base64 encoded service account JSON
    NoEcho: true

Outputs:
  ApiGatewayEndpoint:
    Description: "API Gateway endpoint URL"
    Value: !Sub "https://${ServerlessRestApi}.execute-api.${AWS::Region}.amazonaws.com/Prod/"
```

Deploy with SAM:
```bash
sam build
sam deploy --guided
```

## Environment Variables

The Lambda function requires these environment variables:

- `GOOGLE_EARTH_ENGINE_PROJECT_ID`: Your GEE project ID
- `GOOGLE_SERVICE_ACCOUNT`: Base64-encoded service account JSON (optional, uses default credentials if not set)

## Testing

Test the deployed function:

```bash
# Test map endpoint
curl "https://your-api-gateway-url/api/map?year=2024&month=7&type=LST"

# Test pixel value endpoint  
curl "https://your-api-gateway-url/api/pixel_value?lat=-6&lng=-60&year=2024&month=7&type=LST"
```

## Notes

- Lambda timeout is set to 30 seconds to handle GEE processing
- Memory is set to 512MB for optimal performance
- CORS headers are included for frontend integration
- Both LST and NDVI data types are supported
- Amazon rainforest AOI is pre-configured