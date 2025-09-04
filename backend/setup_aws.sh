#!/bin/bash
# AWS Setup Script for GEE Mapper Deployment

echo "🔧 AWS Lambda Deployment Setup"
echo "=============================="
echo

# Check if running on Windows (Git Bash)
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    echo "🪟 Detected Windows environment"
    PYTHON_CMD="python"
else
    echo "🐧 Detected Unix-like environment" 
    PYTHON_CMD="python3"
fi

# Check if Python is available
if ! command -v $PYTHON_CMD &> /dev/null; then
    echo "❌ Python not found. Please install Python 3.8+"
    exit 1
fi

echo "✅ Python found: $($PYTHON_CMD --version)"

# Check if pip is available
if ! $PYTHON_CMD -m pip --version &> /dev/null; then
    echo "❌ pip not found. Please install pip"
    exit 1
fi

echo "✅ pip found"

# Install required Python packages for deployment
echo
echo "📦 Installing deployment dependencies..."
$PYTHON_CMD -m pip install boto3 botocore --quiet

if [ $? -eq 0 ]; then
    echo "✅ Deployment dependencies installed"
else
    echo "❌ Failed to install deployment dependencies"
    exit 1
fi

# Check AWS credentials
echo
echo "🔍 Checking AWS credentials..."

if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "⚠️  AWS credentials not found in environment variables"
    echo
    echo "Please set up your AWS credentials:"
    echo "Option 1 - Environment Variables:"
    echo "  export AWS_ACCESS_KEY_ID=your_access_key_here"
    echo "  export AWS_SECRET_ACCESS_KEY=your_secret_key_here"
    echo "  export AWS_REGION=us-east-1"
    echo
    echo "Option 2 - AWS CLI:"
    echo "  aws configure"
    echo
    echo "Option 3 - Create .aws_credentials file in this directory:"
    echo "  AWS_ACCESS_KEY_ID=your_access_key_here"
    echo "  AWS_SECRET_ACCESS_KEY=your_secret_key_here"
    echo "  AWS_REGION=us-east-1"
    echo
else
    echo "✅ AWS credentials found in environment"
fi

# Check for Google Earth Engine project ID
if [ -z "$GOOGLE_EARTH_ENGINE_PROJECT_ID" ]; then
    echo "⚠️  GOOGLE_EARTH_ENGINE_PROJECT_ID not set"
    echo "   This can be set later in Lambda environment variables"
else
    echo "✅ Google Earth Engine Project ID: $GOOGLE_EARTH_ENGINE_PROJECT_ID"
fi

echo
echo "🚀 Setup complete! You can now run:"
echo "   python deploy.py"
echo
echo "💡 For help:"
echo "   python deploy.py --help"