from flask import Flask, jsonify, request
from flask_cors import CORS
import ee
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

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
            # Use service account authentication (for production)
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
            # Fall back to user authentication (for local development)
            # This requires: earthengine authenticate && earthengine set_project PROJECT_ID
            try:
                ee.Initialize(project=project_id)
                print(f"Initialized GEE with user authentication for project: {project_id}")
            except Exception as auth_error:
                error_msg = (
                    f"Failed to initialize with user auth: {auth_error}\n"
                    "For local development, run: earthengine authenticate\n"
                    "For production, set GOOGLE_SERVICE_ACCOUNT_EMAIL and GOOGLE_SERVICE_ACCOUNT_KEY"
                )
                raise Exception(error_msg)
        
        return project_id
        
    except Exception as e:
        raise Exception(f"Failed to initialize Google Earth Engine: {str(e)}")

@app.route('/api/map', methods=['GET'])
def get_map():
    try:
        # Get parameters from request
        year = request.args.get('year', default=2024, type=int)
        month = request.args.get('month', default=7, type=int)
        data_type = request.args.get('type', default='LST', type=str).upper()  # LST or NDVI
        aoi_param = request.args.get('aoi')  # Custom Area of Interest
        
        # Validate parameters with current date check
        from datetime import datetime
        current_date = datetime.now()
        
        if not (2000 <= year <= current_date.year):
            return jsonify({"error": f"Year must be between 2000 and {current_date.year}"}), 400
        if not (1 <= month <= 12):
            return jsonify({"error": "Month must be between 1 and 12"}), 400
        if data_type not in ['LST', 'NDVI']:
            return jsonify({"error": "Data type must be 'LST' or 'NDVI'"}), 400
            
        # Don't allow future dates beyond current month
        if year > current_date.year or (year == current_date.year and month > current_date.month):
            return jsonify({"error": "Cannot request future dates"}), 400
        
        # Initialize GEE and get project ID
        project_id = initialize_gee()
        
        # Define Area of Interest (AOI)
        if aoi_param:
            # Parse custom AOI from frontend
            import json
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
            # Fetch MODIS Land Surface Temperature data
            # MODIS/061/MOD11A2 provides 8-day LST composite at 1km resolution with better coverage
            collection = ee.ImageCollection('MODIS/061/MOD11A2')
        else:  # NDVI
            # Fetch Sentinel-2 Surface Reflectance data
            # COPERNICUS/S2_SR_HARMONIZED provides 10m resolution with good temporal coverage
            collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        
        # Create date range for the selected month
        start_date = f'{year}-{month:02d}-01'
        if month == 12:
            end_date = f'{year + 1}-01-01'
        else:
            end_date = f'{year}-{month + 1:02d}-01'
        
        print(f"Filtering {data_type} data for date range: {start_date} to {end_date}")
        
        # Filter by date range using the dynamic dates
        filtered_collection = collection.filterDate(start_date, end_date)
        
        # Filter by the AOI bounds
        filtered_collection = filtered_collection.filterBounds(aoi)
        
        # Apply cloud masking for Sentinel-2 NDVI data
        if data_type == 'NDVI':
            def mask_s2_clouds(image):
                # Simple approach: just scale the values and skip cloud masking for now
                return image.divide(10000)
            
            filtered_collection = filtered_collection.map(mask_s2_clouds)
        
        # Add diagnostics - check collection size
        collection_size = filtered_collection.size()
        print(f"Collection size after filtering: {collection_size.getInfo()}")
        
        # Get image based on data type
        if data_type == 'LST':
            # For LST, get the most recent image
            image = filtered_collection.sort('system:time_start', False).first()
        else:  # NDVI
            # For NDVI, use median composite to get better coverage across AOI
            image = filtered_collection.median()
        
        # Add more detailed diagnostics
        try:
            image_info = image.getInfo()
            print(f"Image info: {image_info}")
            if not image_info:
                error_msg = f"No {data_type} data available for the specified time range and location"
                return jsonify({"error": error_msg})
        except Exception as e:
            return jsonify({"error": f"No data found: {str(e)}"})
        
        # Process image based on data type
        if data_type == 'LST':
            # Select the LST_Day_1km band (Land Surface Temperature - Day)
            lst_band = image.select('LST_Day_1km')
            
            # Apply scale factor (0.02) and convert from Kelvin to Celsius
            # MODIS LST data comes in Kelvin * 50 (scale factor 0.02)
            processed_image = lst_band.multiply(0.02).subtract(273.15)
            
            # Apply smoothing to reduce pixelated appearance
            processed_image = processed_image.focal_mean(2, 'square', 'pixels')
            
            # Define visualization parameters for temperature display
            # Temperature range: 15°C to 40°C, Color palette: blue (cold) to red (hot)
            vis_params = {
                'min': 15,
                'max': 40,
                'palette': ['blue', 'yellow', 'red']
            }
        else:  # NDVI
            # Calculate NDVI from Sentinel-2 bands
            # NDVI = (NIR - Red) / (NIR + Red)
            nir = image.select('B8')  # Near Infrared
            red = image.select('B4')  # Red
            ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
            
            processed_image = ndvi
            
            # Define visualization parameters for NDVI display
            # NDVI range: 0 to 1, Color palette: red (bare soil) to green (vegetation)
            vis_params = {
                'min': 0,
                'max': 0.8,
                'palette': ['brown', 'yellow', 'lightgreen', 'darkgreen']
            }
        
        # Clip the image to the AOI
        processed_image = processed_image.clip(aoi)
        
        # Generate map tile information using getMapId()
        # This creates a map ID and token for tile serving
        try:
            map_id = processed_image.getMapId(vis_params)
            print(f"Map ID response: {map_id}")
        except Exception as e:
            return jsonify({"error": f"Failed to generate map ID: {str(e)}"})
        
        # Check if map ID was generated successfully
        if not map_id or not map_id.get('mapid'):
            return jsonify({"error": f"Failed to generate map tiles. Map ID: {map_id}"})
        
        # Handle the newer GEE API format where token might be empty
        # Use the tile_fetcher's URL template directly
        if 'tile_fetcher' in map_id and hasattr(map_id['tile_fetcher'], 'url_format'):
            # Use tile_fetcher URL format (newer API)
            tile_url = map_id['tile_fetcher'].url_format
        else:
            # Extract the actual map ID from the response
            mapid_value = map_id['mapid']
            if '/' in mapid_value:
                actual_mapid = mapid_value.split('/')[-1]
            else:
                actual_mapid = mapid_value
            
            # Construct the full tile layer URL for Leaflet
            # For newer API without token, use direct mapid access
            if map_id.get('token'):
                tile_url = f"https://earthengine.googleapis.com/v1/projects/{project_id}/maps/{actual_mapid}/tiles/{{z}}/{{x}}/{{y}}?token={map_id['token']}"
            else:
                # Use the full mapid path for newer API
                tile_url = f"https://earthengine.googleapis.com/v1/{map_id['mapid']}/tiles/{{z}}/{{x}}/{{y}}"
        
        # Return the JSON response with the tile URL
        return jsonify({"url": tile_url})
        
    except Exception as e:
        # Return error response with details
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/api/pixel_value', methods=['GET'])
def get_pixel_value():
    try:
        # Get parameters from request
        lat = request.args.get('lat', type=float)
        lng = request.args.get('lng', type=float)
        year = request.args.get('year', default=2024, type=int)
        month = request.args.get('month', default=7, type=int)
        data_type = request.args.get('type', default='LST', type=str).upper()  # LST or NDVI
        
        # Validate parameters
        if lat is None or lng is None:
            return jsonify({"error": "Latitude and longitude are required"}), 400
        if not (-90 <= lat <= 90):
            return jsonify({"error": "Latitude must be between -90 and 90"}), 400
        if not (-180 <= lng <= 180):
            return jsonify({"error": "Longitude must be between -180 and 180"}), 400
        if data_type not in ['LST', 'NDVI']:
            return jsonify({"error": "Data type must be 'LST' or 'NDVI'"}), 400
        from datetime import datetime
        current_date = datetime.now()
        
        if not (2000 <= year <= current_date.year):
            return jsonify({"error": f"Year must be between 2000 and {current_date.year}"}), 400
        if not (1 <= month <= 12):
            return jsonify({"error": "Month must be between 1 and 12"}), 400
            
        # Don't allow future dates beyond current month
        if year > current_date.year or (year == current_date.year and month > current_date.month):
            return jsonify({"error": "Cannot request future dates"}), 400
            
        # Initialize GEE
        initialize_gee()
        
        # Create point geometry from coordinates
        point = ee.Geometry.Point([lng, lat])
        
        # Get data collection based on type
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
            return jsonify({
                "error": f"No {data_type} data available for this location and time period",
                "lat": lat,
                "lng": lng,
                "year": year,
                "month": month
            })
        
        # Get image based on data type
        if data_type == 'LST':
            # For LST, get the most recent image
            image = filtered_collection.sort('system:time_start', False).first()
        else:  # NDVI
            # For NDVI, use median composite to get better coverage across AOI
            image = filtered_collection.median()
        
        # Process based on data type
        if data_type == 'LST':
            # Select LST band and apply MODIS scale factor
            lst_band = image.select('LST_Day_1km')
            processed_band = lst_band.multiply(0.02).subtract(273.15)
            band_name = 'LST_Day_1km'
            unit = '°C'
        else:  # NDVI
            # Calculate NDVI from Sentinel-2 bands
            nir = image.select('B8')  # Near Infrared
            red = image.select('B4')  # Red
            ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
            processed_band = ndvi
            band_name = 'NDVI'
            unit = ''
        
        # Sample the image at the point
        sample = processed_band.sample(point, 1000).first()
        
        # Get the pixel value
        pixel_value = sample.get(band_name).getInfo()
        
        if pixel_value is None:
            return jsonify({
                "error": "No data available at this exact location",
                "lat": lat,
                "lng": lng,
                "year": year,
                "month": month,
                "data_type": data_type
            })
        
        # Get image date for context
        if data_type == 'LST':
            image_date = ee.Date(image.get('system:time_start')).format('YYYY-MM-dd').getInfo()
        else:  # NDVI - median composite doesn't have system:time_start
            image_date = f"{year}-{month:02d} (composite)"
        
        # Format response based on data type
        if data_type == 'LST':
            return jsonify({
                "lat": lat,
                "lng": lng,
                "year": year,
                "month": month,
                "data_type": data_type,
                "temperature_celsius": round(pixel_value, 2),
                "image_date": image_date,
                "message": f"LST Temperature: {round(pixel_value, 2)}°C"
            })
        else:  # NDVI
            return jsonify({
                "lat": lat,
                "lng": lng,
                "year": year,
                "month": month,
                "data_type": data_type,
                "ndvi_value": round(pixel_value, 3),
                "image_date": image_date,
                "message": f"NDVI Value: {round(pixel_value, 3)}"
            })
        
    except Exception as e:
        return jsonify({"error": f"Error getting pixel value: {str(e)}"}), 500

if __name__ == '__main__':
    # Run the Flask app on port 5000 with debug mode
    app.run(debug=True, host='0.0.0.0', port=5000)
