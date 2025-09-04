import json
import os
import ee
from dotenv import load_dotenv

# Load environment variables from .env file (for local testing)
load_dotenv()

def initialize_gee():
    """Initialize Google Earth Engine with flexible authentication"""
    try:
        # Get project ID from environment variable
        project_id = os.environ.get('GOOGLE_EARTH_ENGINE_PROJECT_ID')
        if not project_id:
            raise ValueError("GOOGLE_EARTH_ENGINE_PROJECT_ID not found in environment variables")
        
        # Check for service account credentials first
        service_account_key = os.environ.get('GOOGLE_SERVICE_ACCOUNT_KEY')
        service_account_email = os.environ.get('GOOGLE_SERVICE_ACCOUNT_EMAIL')
        
        if service_account_key and service_account_email:
            # Use service account authentication (preferred for Lambda)
            import json
            import tempfile
            
            # Parse the service account key (it might be JSON string or file path)
            if (service_account_key.startswith('/') or 
                (len(service_account_key) > 3 and service_account_key[1] == ':') or
                service_account_key.endswith('.json')):
                # It's a file path (absolute, relative, or ends with .json)
                credentials = ee.ServiceAccountCredentials(service_account_email, service_account_key)
            else:
                # It's a JSON string, create temporary file
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    if service_account_key.startswith('{'):
                        # Already JSON string
                        f.write(service_account_key)
                    else:
                        # Base64 encoded JSON (common in CI/CD)
                        import base64
                        decoded_key = base64.b64decode(service_account_key).decode('utf-8')
                        f.write(decoded_key)
                    key_file_path = f.name
                
                credentials = ee.ServiceAccountCredentials(service_account_email, key_file_path)
            
            ee.Initialize(credentials, project=project_id)
            print(f"Initialized GEE with service account: {service_account_email}")
            
        else:
            # Fall back to default authentication (for local testing)
            try:
                ee.Initialize(project=project_id)
                print(f"Initialized GEE with default authentication for project: {project_id}")
            except Exception as auth_error:
                error_msg = (
                    f"Failed to initialize with default auth: {auth_error}\n"
                    "For production Lambda, set GOOGLE_SERVICE_ACCOUNT_EMAIL and GOOGLE_SERVICE_ACCOUNT_KEY"
                )
                raise Exception(error_msg)
        
        return project_id
        
    except Exception as e:
        raise Exception(f"Failed to initialize Google Earth Engine: {str(e)}")

def get_map_data(event):
    """Handle map data requests"""
    try:
        # Get parameters from query string
        query_params = event.get('queryStringParameters', {}) or {}
        year = int(query_params.get('year', 2024))
        month = int(query_params.get('month', 7))
        data_type = query_params.get('type', 'LST').upper()
        aoi_param = query_params.get('aoi')  # Custom Area of Interest
        
        # Validate parameters
        from datetime import datetime
        current_date = datetime.now()
        
        if not (2000 <= year <= current_date.year):
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({"error": f"Year must be between 2000 and {current_date.year}"})
            }
        if not (1 <= month <= 12):
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({"error": "Month must be between 1 and 12"})
            }
        if data_type not in ['LST', 'NDVI']:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({"error": "Data type must be 'LST' or 'NDVI'"})
            }
            
        # Don't allow future dates
        if year == current_date.year and month > current_date.month:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({"error": "Cannot request future dates"})
            }
        
        # Initialize GEE and get project ID
        project_id = initialize_gee()
        
        # Define Area of Interest (AOI)
        if aoi_param and aoi_param.strip():
            # Parse custom AOI from frontend
            try:
                aoi_data = json.loads(aoi_param)
                if aoi_data['type'] == 'rectangle':
                    # Rectangle format: [west, south, east, north]
                    bounds = aoi_data['bounds']
                    aoi = ee.Geometry.Rectangle(bounds)
                elif aoi_data['type'] == 'polygon':
                    # Polygon format: coordinates array
                    coordinates = aoi_data['coordinates']
                    aoi = ee.Geometry.Polygon([coordinates])
                else:
                    raise ValueError("Unsupported AOI type")
                print(f"Using custom AOI: {aoi_data['type']}")
            except Exception as e:
                print(f"Error parsing custom AOI: {e}")
                # Fall back to default Amazon region
                aoi = ee.Geometry.Rectangle([-65.0, -10.0, -55.0, -2.0])
        else:
            # Default Area of Interest for Amazon rainforest
            # Coordinates: [west, south, east, north] in degrees - covers central Amazon region
            aoi = ee.Geometry.Rectangle([-65.0, -10.0, -55.0, -2.0])
        
        # Choose collection and processing based on data type
        if data_type == 'LST':
            collection = ee.ImageCollection('MODIS/061/MOD11A2')
        else:  # NDVI
            collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        
        # Create date range for the selected month
        start_date = f'{year}-{month:02d}-01'
        if month == 12:
            end_date = f'{year + 1}-01-01'
        else:
            end_date = f'{year}-{month + 1:02d}-01'
        
        # Filter by date range and AOI bounds
        filtered_collection = collection.filterDate(start_date, end_date).filterBounds(aoi)
        
        # Apply cloud masking for Sentinel-2 NDVI data
        if data_type == 'NDVI':
            def mask_s2_clouds(image):
                # Simple approach: just scale the values and skip cloud masking for now
                return image.divide(10000)
            
            filtered_collection = filtered_collection.map(mask_s2_clouds)
        
        # Get image based on data type
        if data_type == 'LST':
            # For LST, get the most recent image
            image = filtered_collection.sort('system:time_start', False).first()
        else:  # NDVI
            # For NDVI, use median composite to get better coverage across AOI
            image = filtered_collection.median()
        
        # Check if image exists
        try:
            image_info = image.getInfo()
            if not image_info:
                error_msg = f"No {data_type} data available for the specified time range and location"
                return {
                    'statusCode': 404,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({"error": error_msg})
                }
        except Exception as e:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({"error": f"No data found: {str(e)}"})
            }
        
        # Process image based on data type
        if data_type == 'LST':
            # Process LST data
            lst_band = image.select('LST_Day_1km')
            processed_image = lst_band.multiply(0.02).subtract(273.15)
            processed_image = processed_image.focal_mean(2, 'square', 'pixels')
            
            vis_params = {
                'min': 15,
                'max': 40,
                'palette': ['blue', 'yellow', 'red']
            }
        else:  # NDVI
            # Calculate NDVI
            nir = image.select('B8')
            red = image.select('B4')
            ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
            processed_image = ndvi
            
            vis_params = {
                'min': 0,
                'max': 0.8,
                'palette': ['brown', 'yellow', 'lightgreen', 'darkgreen']
            }
        
        # Clip to AOI
        processed_image = processed_image.clip(aoi)
        
        # Generate map tiles
        try:
            map_id = processed_image.getMapId(vis_params)
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({"error": f"Failed to generate map ID: {str(e)}"})
            }
        
        # Check if map ID was generated successfully
        if not map_id or not map_id.get('mapid'):
            return {
                'statusCode': 500,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({"error": f"Failed to generate map tiles. Map ID: {map_id}"})
            }
        
        # Construct tile URL
        mapid_value = map_id['mapid']
        if '/' in mapid_value:
            actual_mapid = mapid_value.split('/')[-1]
        else:
            actual_mapid = mapid_value
        
        if map_id.get('token'):
            tile_url = f"https://earthengine.googleapis.com/v1/projects/{project_id}/maps/{actual_mapid}/tiles/{{z}}/{{x}}/{{y}}?token={map_id['token']}"
        else:
            tile_url = f"https://earthengine.googleapis.com/v1/{map_id['mapid']}/tiles/{{z}}/{{x}}/{{y}}"
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({"url": tile_url})
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({"error": f"Server error: {str(e)}"})
        }

def get_pixel_value_data(event):
    """Handle pixel value requests"""
    try:
        # Get parameters from query string
        query_params = event.get('queryStringParameters', {}) or {}
        
        try:
            lat = float(query_params.get('lat'))
            lng = float(query_params.get('lng'))
        except (TypeError, ValueError):
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({"error": "Latitude and longitude are required and must be numbers"})
            }
        
        year = int(query_params.get('year', 2024))
        month = int(query_params.get('month', 7))
        data_type = query_params.get('type', 'LST').upper()
        aoi_param = query_params.get('aoi')  # Custom Area of Interest
        
        # Validate parameters
        if not (-90 <= lat <= 90):
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({"error": "Latitude must be between -90 and 90"})
            }
        if not (-180 <= lng <= 180):
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({"error": "Longitude must be between -180 and 180"})
            }
        if data_type not in ['LST', 'NDVI']:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({"error": "Data type must be 'LST' or 'NDVI'"})
            }
        
        from datetime import datetime
        current_date = datetime.now()
        
        if not (2000 <= year <= current_date.year):
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({"error": f"Year must be between 2000 and {current_date.year}"})
            }
        if not (1 <= month <= 12):
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({"error": "Month must be between 1 and 12"})
            }
            
        # Don't allow future dates
        if year == current_date.year and month > current_date.month:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({"error": "Cannot request future dates"})
            }
            
        # Initialize GEE
        initialize_gee()
        
        # Create point geometry
        point = ee.Geometry.Point([lng, lat])
        
        # Get data collection based on type
        if data_type == 'LST':
            collection = ee.ImageCollection('MODIS/061/MOD11A2')
        else:  # NDVI
            collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        
        # Create date range
        start_date = f'{year}-{month:02d}-01'
        if month == 12:
            end_date = f'{year + 1}-01-01'
        else:
            end_date = f'{year}-{month + 1:02d}-01'
        
        # Filter collection
        filtered_collection = collection.filterDate(start_date, end_date).filterBounds(point)
        
        # Apply cloud masking for Sentinel-2 NDVI data
        if data_type == 'NDVI':
            def mask_s2_clouds(image):
                # Simple approach: just scale the values and skip cloud masking for now
                return image.divide(10000)
            
            filtered_collection = filtered_collection.map(mask_s2_clouds)
        
        # Check if any data exists
        collection_size = filtered_collection.size().getInfo()
        if collection_size == 0:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({
                    "error": f"No {data_type} data available for this location and time period",
                    "lat": lat,
                    "lng": lng,
                    "year": year,
                    "month": month,
                    "data_type": data_type
                })
            }
        
        # Get the most recent image
        image = filtered_collection.sort('system:time_start', False).first()
        
        # Process based on data type
        if data_type == 'LST':
            lst_band = image.select('LST_Day_1km')
            processed_band = lst_band.multiply(0.02).subtract(273.15)
            band_name = 'LST_Day_1km'
        else:  # NDVI
            nir = image.select('B8')
            red = image.select('B4')
            ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
            processed_band = ndvi
            band_name = 'NDVI'
        
        # Sample the image at the point
        sample = processed_band.sample(point, 1000).first()
        
        # Check if sample exists
        if sample is None:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({
                    "error": f"No {data_type} data available at this location (possibly due to cloud cover or data gaps)",
                    "lat": lat,
                    "lng": lng,
                    "year": year,
                    "month": month,
                    "data_type": data_type
                })
            }
        
        # Get the pixel value
        try:
            pixel_value = sample.get(band_name).getInfo()
        except Exception as e:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({
                    "error": f"No {data_type} data available at this location (data processing error)",
                    "lat": lat,
                    "lng": lng,
                    "year": year,
                    "month": month,
                    "data_type": data_type
                })
            }
        
        if pixel_value is None:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({
                    "error": "No data available at this exact location",
                    "lat": lat,
                    "lng": lng,
                    "year": year,
                    "month": month,
                    "data_type": data_type
                })
            }
        
        # Get image date
        if data_type == 'LST':
            image_date = ee.Date(image.get('system:time_start')).format('YYYY-MM-dd').getInfo()
        else:  # NDVI - median composite doesn't have system:time_start
            image_date = f"{year}-{month:02d} (composite)"
        
        # Format response based on data type
        if data_type == 'LST':
            response_data = {
                "lat": lat,
                "lng": lng,
                "year": year,
                "month": month,
                "data_type": data_type,
                "temperature_celsius": round(pixel_value, 2),
                "image_date": image_date,
                "message": f"LST Temperature: {round(pixel_value, 2)}°C"
            }
        else:  # NDVI
            response_data = {
                "lat": lat,
                "lng": lng,
                "year": year,
                "month": month,
                "data_type": data_type,
                "ndvi_value": round(pixel_value, 3),
                "image_date": image_date,
                "message": f"NDVI Value: {round(pixel_value, 3)}"
            }
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps(response_data)
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({"error": f"Error getting pixel value: {str(e)}"})
        }

def lambda_handler(event, context):
    """Main Lambda handler function"""
    try:
        # Get the HTTP method and path
        http_method = event.get('httpMethod', 'GET')
        path = event.get('path', '/')
        
        # Handle CORS preflight requests
        if http_method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type',
                },
                'body': ''
            }
        
        # Route based on path
        if path == '/api/map' or path.endswith('/map'):
            return get_map_data(event)
        elif path == '/api/pixel_value' or path.endswith('/pixel_value'):
            return get_pixel_value_data(event)
        else:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({"error": "Not found"})
            }
            
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({"error": f"Lambda error: {str(e)}"})
        }