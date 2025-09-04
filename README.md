# google-earth-dashboard


## 🚦 Quick Start

### Prerequisites
- **Node.js** (v16+) and npm
- **Python** (v3.8+) and pip
- **Google Earth Engine** account ([Sign up here](https://earthengine.google.com))
- **Google Cloud Project** with Earth Engine API enabled

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python -m venv venv
source venv/Scripts/activate  # Windows Git Bash
# source venv/bin/activate    # macOS/Linux

# Install Python dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and add your Google Earth Engine Project ID

# Option 1: User Authentication (for local development)
earthengine authenticate
earthengine set_project YOUR_PROJECT_ID

# Option 2: Service Account Authentication (recommended for production)
# 1. Create a service account in Google Cloud Console
# 2. Grant it "Earth Engine Resource Admin" and "Service Usage Consumer" roles  
# 3. Download the JSON key file and place it in the backend/ directory
# 4. Update .env with:
#    GOOGLE_SERVICE_ACCOUNT_EMAIL=your-service-account@your-project.iam.gserviceaccount.com
#    GOOGLE_SERVICE_ACCOUNT_KEY=your-service-account-key.json
# 
# IMPORTANT: The JSON key file should be placed in the backend/ folder.
# It will be automatically excluded from git for security.

# Start the Flask server
python app.py
```

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install Node.js dependencies
npm install

# Set up environment variables
cp .env.example .env
# Default configuration points to localhost:5000

# Start the React development server
npm run dev
```

### 3. Access the Application

Open your browser and navigate to:
- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:5000/api/map

## 📊 API Endpoints

### `GET /api/map`
Retrieves LST tile URL for map visualization.

**Parameters:**
- `year` (optional): Year for data query (2000-2024, default: 2024)
- `month` (optional): Month for data query (1-12, default: 7)

**Response:**
```json
{
  "url": "https://earthengine.googleapis.com/v1/projects/PROJECT_ID/maps/MAP_ID/tiles/{z}/{x}/{y}"
}
```

### `GET /api/pixel_value`
Gets temperature value at specific coordinates.

**Parameters:**
- `lat`: Latitude (-90 to 90)
- `lng`: Longitude (-180 to 180)
- `year`: Year for data query (2000-2024)
- `month`: Month for data query (1-12)

**Response:**
```json
{
  "lat": -6.0,
  "lng": -60.0,
  "temperature_celsius": 28.5,
  "image_date": "2024-07-15",
  "message": "LST Temperature: 28.5°C"
}
```

## 🌍 Use Cases & Applications

### 🔬 **Scientific Research**
- **Climate Change Studies**: Monitor temperature trends in the Amazon
- **Deforestation Impact**: Analyze temperature changes after forest loss
- **Urban Heat Islands**: Compare city vs forest temperatures
- **Agricultural Planning**: Soil temperature monitoring for crop timing

### 🏢 **Commercial Applications**
- **Environmental Consulting**: Client reports with interactive visualizations
- **Insurance Risk Assessment**: Climate risk analysis for policies
- **Real Estate Development**: Environmental impact assessments
- **Carbon Credit Verification**: Forest monitoring for offset projects

### 🎓 **Educational Use**
- **University Courses**: Interactive Earth science demonstrations
- **Research Training**: Hands-on satellite data analysis
- **Public Outreach**: Making climate data accessible to everyone
- **K-12 Education**: Visual learning about climate and geography

## 🚀 Deployment

### Backend: AWS Lambda (Automated)

**One-Command Deployment** with automated setup:

```bash
# Navigate to backend directory
cd backend

# Set up AWS credentials in your terminal (safer than files)
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key  
export AWS_REGION=us-east-1

# Set Google Earth Engine Project ID
export GOOGLE_EARTH_ENGINE_PROJECT_ID=your-production-gee-project-id

# Install deployment dependencies
pip install boto3 botocore

# Deploy with one command!
python deploy.py
```

The deployment script automatically handles:
- ✅ **Dependency Packaging**: Creates deployment ZIP with all requirements
- ✅ **IAM Role Creation**: Sets up Lambda execution role with proper permissions
- ✅ **Lambda Function**: Creates/updates function with optimal settings (1GB RAM, 5min timeout)
- ✅ **API Gateway**: Sets up REST API with CORS-enabled endpoints
- ✅ **Environment Variables**: Configures GEE project ID in Lambda
- ✅ **Error Handling**: Comprehensive validation and rollback on failures

**Output Example:**
```
🚀 Starting AWS Lambda deployment...
✅ AWS credentials valid (Account: 123456789012)
✅ Required files found
📦 Creating deployment package...
🔐 Setting up IAM role...
🚀 Deploying Lambda function...
🌐 Setting up API Gateway...

🎉 Deployment completed successfully!
📡 API URL: https://abc123def.execute-api.us-east-1.amazonaws.com/prod
🔗 Test endpoints:
   • Map tiles: https://abc123def.execute-api.us-east-1.amazonaws.com/prod/api/map?year=2024&month=7
   • Pixel value: https://abc123def.execute-api.us-east-1.amazonaws.com/prod/api/pixel_value?lat=-6&lng=-60&year=2024&month=7
```

### Frontend: Vercel
```bash
# Connect GitHub repository to Vercel
# Set build command: npm run build
# Set environment variable: VITE_API_BASE_URL=https://your-lambda-api-url-from-above
```

## 🔧 Configuration

### Environment Variables

**Backend (.env):**
```env
# Google Earth Engine Configuration
GOOGLE_EARTH_ENGINE_PROJECT_ID=your-gee-project-id

# For production: Service Account Authentication
GOOGLE_SERVICE_ACCOUNT_EMAIL=your-service-account@your-project.iam.gserviceaccount.com
GOOGLE_SERVICE_ACCOUNT_KEY=your-service-account-key.json

# AWS Configuration (for deployment)
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_REGION=us-east-1
```

**⚠️ Security Notes:**
- Place your Google Cloud service account JSON key file in the `backend/` directory
- The JSON key file will be automatically excluded from git via `.gitignore`
- Never commit service account credentials to version control

**Frontend (.env):**
```env
VITE_API_BASE_URL=http://127.0.0.1:5000
```
