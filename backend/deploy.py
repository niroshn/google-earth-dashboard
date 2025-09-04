#!/usr/bin/env python3
"""
AWS Lambda Deployment Script for GEE Mapper Backend
Automates the entire deployment process with one command
"""

import os
import sys
import json
import zipfile
import subprocess
import shutil
import tempfile
from pathlib import Path
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class LambdaDeployer:
    def __init__(self):
        self.function_name = "gee-mapper-backend"
        self.region = os.environ.get('AWS_REGION', 'us-east-1')
        self.runtime = 'python3.9'
        self.memory_size = 1024
        self.timeout = 300  # 5 minutes
        
        # Initialize AWS clients
        try:
            self.lambda_client = boto3.client('lambda', region_name=self.region)
            self.apigateway_client = boto3.client('apigateway', region_name=self.region)
            self.iam_client = boto3.client('iam')
        except NoCredentialsError:
            print("[ERROR] AWS credentials not found!")
            print("Set up credentials using:")
            print("  export AWS_ACCESS_KEY_ID=your_access_key")
            print("  export AWS_SECRET_ACCESS_KEY=your_secret_key") 
            print("  export AWS_REGION=us-east-1")
            sys.exit(1)
    
    def check_prerequisites(self):
        """Check if all required tools and credentials are available"""
        print("[CHECK] Checking prerequisites...")
        
        # Check AWS credentials
        try:
            sts = boto3.client('sts')
            identity = sts.get_caller_identity()
            print(f"[OK] AWS credentials valid (Account: {identity['Account']})")
        except Exception as e:
            print(f"[ERROR] AWS credentials error: {e}")
            return False
        
        # Check required files
        required_files = ['lambda_function.py', 'requirements.txt']
        for file in required_files:
            if not os.path.exists(file):
                print(f"[ERROR] Required file missing: {file}")
                return False
        print("[OK] Required files found")
        
        # Check environment variables
        gee_project = os.environ.get('GOOGLE_EARTH_ENGINE_PROJECT_ID')
        if not gee_project:
            print("[WARNING]  GOOGLE_EARTH_ENGINE_PROJECT_ID not set - will need to be configured in Lambda")
        else:
            print(f"[OK] GEE Project ID: {gee_project}")
        
        return True
    
    def create_deployment_package(self):
        """Create deployment ZIP package with all dependencies"""
        print("[PACKAGE] Creating deployment package...")
        
        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = os.path.join(temp_dir, 'package')
            os.makedirs(package_dir)
            
            print("  [INSTALL] Installing dependencies...")
            # Install dependencies to package directory
            result = subprocess.run([
                sys.executable, '-m', 'pip', 'install',
                '-r', 'requirements.txt',
                '-t', package_dir,
                '--no-cache-dir'
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"[ERROR] Failed to install dependencies: {result.stderr}")
                return None
            
            # Copy Lambda function
            shutil.copy2('lambda_function.py', package_dir)
            
            # Copy .env if it exists (for local testing)
            if os.path.exists('.env'):
                shutil.copy2('.env', package_dir)
            
            # Create ZIP file
            zip_path = 'lambda_deployment.zip'
            print(f"  [CREATE] Creating {zip_path}...")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for root, dirs, files in os.walk(package_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arc_path = os.path.relpath(file_path, package_dir)
                        zip_file.write(file_path, arc_path)
            
            print(f"[OK] Deployment package created: {zip_path}")
            return zip_path
    
    def create_iam_role(self):
        """Create or update IAM role for Lambda"""
        print("[IAM] Setting up IAM role...")
        
        role_name = f"{self.function_name}-role"
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole"
                }
            ]
        }
        
        try:
            # Try to get existing role
            response = self.iam_client.get_role(RoleName=role_name)
            role_arn = response['Role']['Arn']
            print(f"[OK] Using existing IAM role: {role_name}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchEntity':
                # Create new role
                print(f"  [CREATE] Creating new IAM role: {role_name}")
                response = self.iam_client.create_role(
                    RoleName=role_name,
                    AssumeRolePolicyDocument=json.dumps(trust_policy),
                    Description=f"IAM role for {self.function_name} Lambda function"
                )
                role_arn = response['Role']['Arn']
                
                # Attach basic Lambda execution policy
                self.iam_client.attach_role_policy(
                    RoleName=role_name,
                    PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
                )
                
                # Wait for role to propagate
                print("  [WAIT] Waiting for IAM role to propagate...")
                time.sleep(10)
                print(f"[OK] Created IAM role: {role_name}")
            else:
                raise
        
        return role_arn
    
    def deploy_lambda_function(self, zip_path, role_arn):
        """Deploy or update Lambda function"""
        print("[LAMBDA] Deploying Lambda function...")
        
        # Read ZIP file
        with open(zip_path, 'rb') as zip_file:
            zip_content = zip_file.read()
        
        # Environment variables
        environment = {
            'Variables': {}
        }
        
        # Add GEE project ID if available
        gee_project = os.environ.get('GOOGLE_EARTH_ENGINE_PROJECT_ID')
        if gee_project:
            environment['Variables']['GOOGLE_EARTH_ENGINE_PROJECT_ID'] = gee_project
        
        # Add service account credentials if available
        service_account_email = os.environ.get('GOOGLE_SERVICE_ACCOUNT_EMAIL')
        service_account_key = os.environ.get('GOOGLE_SERVICE_ACCOUNT_KEY')
        
        if service_account_email and service_account_key:
            environment['Variables']['GOOGLE_SERVICE_ACCOUNT_EMAIL'] = service_account_email
            
            # For Lambda deployment, convert file path to base64 content
            if service_account_key.endswith('.json') and os.path.exists(service_account_key):
                print("  [INFO] Converting service account key file to base64 for Lambda")
                import base64
                with open(service_account_key, 'rb') as f:
                    key_content = base64.b64encode(f.read()).decode('utf-8')
                environment['Variables']['GOOGLE_SERVICE_ACCOUNT_KEY'] = key_content
            else:
                # Already base64 or JSON string
                environment['Variables']['GOOGLE_SERVICE_ACCOUNT_KEY'] = service_account_key
        
        try:
            # Try to update existing function
            response = self.lambda_client.update_function_code(
                FunctionName=self.function_name,
                ZipFile=zip_content
            )
            print(f"[OK] Updated existing Lambda function: {self.function_name}")
            
            # Wait for function to be ready for configuration updates
            print("  [WAIT] Waiting for function update to complete...")
            waiter = self.lambda_client.get_waiter('function_updated')
            waiter.wait(FunctionName=self.function_name)
            
            # Update configuration
            self.lambda_client.update_function_configuration(
                FunctionName=self.function_name,
                Runtime=self.runtime,
                Role=role_arn,
                Handler='lambda_function.lambda_handler',
                Description='GEE Mapper Backend - Geospatial data visualization API',
                Timeout=self.timeout,
                MemorySize=self.memory_size,
                Environment=environment
            )
            print(f"[OK] Updated Lambda function configuration")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                # Create new function
                print(f"  [CREATE] Creating new Lambda function: {self.function_name}")
                response = self.lambda_client.create_function(
                    FunctionName=self.function_name,
                    Runtime=self.runtime,
                    Role=role_arn,
                    Handler='lambda_function.lambda_handler',
                    Code={'ZipFile': zip_content},
                    Description='GEE Mapper Backend - Geospatial data visualization API',
                    Timeout=self.timeout,
                    MemorySize=self.memory_size,
                    Environment=environment,
                    Publish=True
                )
                print(f"[OK] Created Lambda function: {self.function_name}")
            else:
                raise
        
        return response['FunctionArn']
    
    def create_api_gateway(self, lambda_arn):
        """Create or update API Gateway"""
        print("[API] Setting up API Gateway...")
        
        api_name = f"{self.function_name}-api"
        
        try:
            # List existing APIs
            apis = self.apigateway_client.get_rest_apis()
            api_id = None
            
            for api in apis['items']:
                if api['name'] == api_name:
                    api_id = api['id']
                    print(f"[OK] Found existing API Gateway: {api_name}")
                    break
            
            if not api_id:
                # Create new API
                print(f"  [CREATE] Creating new API Gateway: {api_name}")
                api_response = self.apigateway_client.create_rest_api(
                    name=api_name,
                    description='API Gateway for GEE Mapper Backend',
                    endpointConfiguration={'types': ['REGIONAL']}
                )
                api_id = api_response['id']
                print(f"[OK] Created API Gateway: {api_name}")
                
                # Get root resource
                resources = self.apigateway_client.get_resources(restApiId=api_id)
                root_id = next(r['id'] for r in resources['items'] if r['path'] == '/')
                
                # Create /api resource
                api_resource = self.apigateway_client.create_resource(
                    restApiId=api_id,
                    parentId=root_id,
                    pathPart='api'
                )
                api_resource_id = api_resource['id']
                
                # Create endpoints: /api/map and /api/pixel_value
                endpoints = ['map', 'pixel_value']
                
                for endpoint in endpoints:
                    # Create resource
                    resource = self.apigateway_client.create_resource(
                        restApiId=api_id,
                        parentId=api_resource_id,
                        pathPart=endpoint
                    )
                    
                    # Create GET method
                    self.apigateway_client.put_method(
                        restApiId=api_id,
                        resourceId=resource['id'],
                        httpMethod='GET',
                        authorizationType='NONE'
                    )
                    
                    # Create OPTIONS method for CORS
                    self.apigateway_client.put_method(
                        restApiId=api_id,
                        resourceId=resource['id'],
                        httpMethod='OPTIONS',
                        authorizationType='NONE'
                    )
                    
                    # Integration with Lambda
                    lambda_uri = f"arn:aws:apigateway:{self.region}:lambda:path/2015-03-31/functions/{lambda_arn}/invocations"
                    
                    self.apigateway_client.put_integration(
                        restApiId=api_id,
                        resourceId=resource['id'],
                        httpMethod='GET',
                        type='AWS_PROXY',
                        integrationHttpMethod='POST',
                        uri=lambda_uri
                    )
                    
                    # CORS method response (must come before integration response)
                    self.apigateway_client.put_method_response(
                        restApiId=api_id,
                        resourceId=resource['id'],
                        httpMethod='OPTIONS',
                        statusCode='200',
                        responseParameters={
                            'method.response.header.Access-Control-Allow-Headers': True,
                            'method.response.header.Access-Control-Allow-Methods': True,
                            'method.response.header.Access-Control-Allow-Origin': True
                        }
                    )
                    
                    # CORS OPTIONS integration
                    self.apigateway_client.put_integration(
                        restApiId=api_id,
                        resourceId=resource['id'],
                        httpMethod='OPTIONS',
                        type='MOCK',
                        requestTemplates={'application/json': '{"statusCode": 200}'}
                    )
                    
                    # CORS integration response (must come after method response)
                    self.apigateway_client.put_integration_response(
                        restApiId=api_id,
                        resourceId=resource['id'],
                        httpMethod='OPTIONS',
                        statusCode='200',
                        responseParameters={
                            'method.response.header.Access-Control-Allow-Headers': "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
                            'method.response.header.Access-Control-Allow-Methods': "'GET,OPTIONS'",
                            'method.response.header.Access-Control-Allow-Origin': "'*'"
                        }
                    )
                    
                    print(f"  [OK] Created endpoint: /api/{endpoint}")
                
                # Deploy API
                self.apigateway_client.create_deployment(
                    restApiId=api_id,
                    stageName='prod',
                    description='Production deployment'
                )
            
            # Add Lambda permission for API Gateway (always do this)
            # Get AWS account ID for proper ARN format
            sts = boto3.client('sts')
            account_id = sts.get_caller_identity()['Account']
            
            try:
                self.lambda_client.add_permission(
                    FunctionName=self.function_name,
                    StatementId=f"apigateway-{int(time.time())}",
                    Action='lambda:InvokeFunction',
                    Principal='apigateway.amazonaws.com',
                    SourceArn=f"arn:aws:execute-api:{self.region}:{account_id}:{api_id}/*/*/*"
                )
                print("[OK] Added Lambda permission for API Gateway")
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceConflictException':
                    print(f"[WARNING] Could not add Lambda permission: {e}")
                else:
                    print("[OK] Lambda permission already exists")
                
            api_url = f"https://{api_id}.execute-api.{self.region}.amazonaws.com/prod"
            print(f"[OK] API Gateway URL: {api_url}")
            return api_url
            
        except Exception as e:
            print(f"[ERROR] API Gateway setup failed: {e}")
            raise
    
    def cleanup(self, zip_path):
        """Clean up temporary files"""
        if os.path.exists(zip_path):
            os.remove(zip_path)
            print(f"[CLEAN] Cleaned up: {zip_path}")
    
    def deploy(self):
        """Main deployment function"""
        print("[DEPLOY] Starting AWS Lambda deployment...")
        print(f"   Function: {self.function_name}")
        print(f"   Region: {self.region}")
        print(f"   Runtime: {self.runtime}")
        print()
        
        try:
            # Check prerequisites
            if not self.check_prerequisites():
                return False
            
            # Create deployment package
            zip_path = self.create_deployment_package()
            if not zip_path:
                return False
            
            # Create IAM role
            role_arn = self.create_iam_role()
            
            # Deploy Lambda function
            lambda_arn = self.deploy_lambda_function(zip_path, role_arn)
            
            # Create API Gateway
            api_url = self.create_api_gateway(lambda_arn)
            
            # Cleanup
            self.cleanup(zip_path)
            
            print("\n[SUCCESS] Deployment completed successfully!")
            print(f"[URL] API URL: {api_url}")
            print(f"[TEST] Test endpoints:")
            print(f"   • Map tiles: {api_url}/api/map?year=2024&month=7")
            print(f"   • Pixel value: {api_url}/api/pixel_value?lat=-6&lng=-60&year=2024&month=7")
            print()
            print("[INFO] Next steps:")
            print("   1. Update your frontend VITE_API_BASE_URL to use the API URL above")
            print("   2. Test the endpoints in your browser or with curl")
            if not os.environ.get('GOOGLE_EARTH_ENGINE_PROJECT_ID'):
                print("   3. Set GOOGLE_EARTH_ENGINE_PROJECT_ID in Lambda environment variables")
            
            return True
            
        except Exception as e:
            print(f"\n[ERROR] Deployment failed: {e}")
            if 'zip_path' in locals():
                self.cleanup(zip_path)
            return False

def main():
    """Main entry point"""
    if len(sys.argv) > 1 and sys.argv[1] == '--help':
        print("GEE Mapper Lambda Deployment Script")
        print()
        print("Usage: python deploy.py")
        print()
        print("Required environment variables:")
        print("  AWS_ACCESS_KEY_ID         - AWS access key")
        print("  AWS_SECRET_ACCESS_KEY     - AWS secret key")
        print("  AWS_REGION               - AWS region (default: us-east-1)")
        print()
        print("Optional environment variables:")
        print("  GOOGLE_EARTH_ENGINE_PROJECT_ID - GEE project ID")
        print()
        return
    
    deployer = LambdaDeployer()
    success = deployer.deploy()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()