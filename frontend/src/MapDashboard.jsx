import React, { useState, useEffect, useRef } from 'react';
import { MapContainer, TileLayer, LayersControl, Popup, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import '@geoman-io/leaflet-geoman-free';
import axios from 'axios';
import 'leaflet/dist/leaflet.css';
import '@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css';
import './MapDashboard.css';

// Helper component to initialize Geoman drawing controls
const GeomanControls = ({ onDrawCreated, onDrawDeleted }) => {
  const map = useMapEvents({});
  const [isInitialized, setIsInitialized] = useState(false);
  const drawnLayersRef = useRef([]);
  
  useEffect(() => {
    // Ensure Geoman is loaded and map is ready
    const initializeGeoman = () => {
      console.log('Attempting to initialize Geoman...');
      console.log('Map instance:', map);
      console.log('map.pm exists:', !!map.pm);
      
      // Check if L.PM is available (global Leaflet PM)
      if (typeof L !== 'undefined' && L.PM) {
        console.log('L.PM is available globally');
        
        // Force initialize PM on the map if not already done
        if (!map.pm) {
          console.log('Manually initializing PM on map');
          map.pm = new L.PM.Map(map);
        }
      }
      
      if (map.pm && !isInitialized) {
        try {
          console.log('Initializing Geoman controls...');
          
          // Add controls with specific tools only
          map.pm.addControls({
            position: 'topleft',
            drawRectangle: true,
            drawPolygon: true,
            drawPolyline: false,
            drawCircle: false,
            drawMarker: false,
            drawCircleMarker: false,
            drawText: false,
            editMode: false,
            dragMode: false,
            cutPolygon: false,
            removalMode: true,
            rotateMode: false,
            optionsControls: false,
            customControls: false,
            oneBlock: false,
          });

          // Configure drawing options
          map.pm.setGlobalOptions({
            allowSelfIntersection: false,
          });

          // Add helpful tooltips after toolbar is created
          setTimeout(() => {
            const drawButtons = document.querySelectorAll('.leaflet-pm-icon-button');
            drawButtons.forEach((button, index) => {
              if (index === 0) { // First button (Rectangle)
                button.title = "Draw Rectangle AOI • Click anywhere on map to get pixel values";
                button.setAttribute('aria-label', 'Draw rectangle or click map for pixel values');
              }
              if (index === 1) { // Second button (Polygon)
                button.title = "Draw Polygon AOI • Click anywhere on map to get pixel values";
                button.setAttribute('aria-label', 'Draw polygon or click map for pixel values');
              }
              if (button.classList.contains('leaflet-pm-icon-delete')) { // Delete button
                button.title = "Remove drawn AOI";
              }
            });
          }, 500);

          // Event listeners
          const handleCreate = (e) => {
            console.log('Shape created:', e);
            
            // Remove all previously drawn layers
            drawnLayersRef.current.forEach(layer => {
              try {
                if (map.hasLayer(layer)) {
                  map.removeLayer(layer);
                }
              } catch (error) {
                console.warn('Error removing layer:', error);
              }
            });
            
            // Clear the array and add the new layer
            drawnLayersRef.current = [e.layer];
            
            if (onDrawCreated) {
              onDrawCreated(e);
            }
          };

          const handleRemove = (e) => {
            console.log('Shape removed:', e);
            
            // Remove from our tracking array
            drawnLayersRef.current = drawnLayersRef.current.filter(layer => layer !== e.layer);
            
            if (onDrawDeleted) {
              onDrawDeleted(e);
            }
          };

          // Listen for drawing events
          map.on('pm:create', handleCreate);
          map.on('pm:remove', handleRemove);
          
          setIsInitialized(true);
          console.log('Geoman initialized successfully!');

          // Cleanup function
          return () => {
            map.off('pm:create', handleCreate);
            map.off('pm:remove', handleRemove);
          };
        } catch (error) {
          console.error('Error initializing Geoman controls:', error);
        }
      } else {
        console.warn('Geoman not available or already initialized');
      }
    };

    // Try multiple times with increasing delays
    const timer1 = setTimeout(initializeGeoman, 100);
    const timer2 = setTimeout(initializeGeoman, 500);
    const timer3 = setTimeout(initializeGeoman, 1000);

    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
    };
  }, [map, onDrawCreated, onDrawDeleted, isInitialized]);

  return null;
};

// Helper component to handle map click events
const MapClickHandler = ({ onMapClick }) => {
  const [popup, setPopup] = useState(null);

  useMapEvents({
    click: async (e) => {
      const { lat, lng } = e.latlng;
      
      // Show loading popup immediately
      setPopup({
        position: [lat, lng],
        content: `Fetching data...\nLat: ${lat.toFixed(4)}, Lng: ${lng.toFixed(4)}`,
        loading: true
      });
      
      if (onMapClick) {
        try {
          const result = await onMapClick(lat, lng);
          
          if (result) {
            if (result.error) {
              setPopup({
                position: [lat, lng],
                content: `Error: ${result.error}\nLat: ${lat.toFixed(4)}, Lng: ${lng.toFixed(4)}`,
                loading: false,
                error: true
              });
            } else {
              setPopup({
                position: [lat, lng],
                content: `${result.message}\nDate: ${result.date}\nLat: ${lat.toFixed(4)}, Lng: ${lng.toFixed(4)}`,
                loading: false,
                error: false
              });
            }
          }
        } catch (error) {
          setPopup({
            position: [lat, lng],
            content: `Failed to get data\nLat: ${lat.toFixed(4)}, Lng: ${lng.toFixed(4)}`,
            loading: false,
            error: true
          });
        }
      }
      
      // Auto-hide popup after 5 seconds
      setTimeout(() => {
        setPopup(null);
      }, 5000);
    }
  });

  return popup ? (
    <Popup position={popup.position}>
      <div style={{ 
        whiteSpace: 'pre-line',
        color: popup.error ? '#dc3545' : popup.loading ? '#007bff' : '#28a745',
        fontWeight: '500'
      }}>
        {popup.content}
        {popup.loading && (
          <div style={{ marginTop: '8px', fontSize: '12px', color: '#666' }}>
            Loading...
          </div>
        )}
      </div>
    </Popup>
  ) : null;
};

// Legend component
const MapLegend = ({ dataType }) => {
  const legends = {
    LST: {
      title: 'Land Surface Temperature (°C)',
      gradient: 'linear-gradient(to right, blue, yellow, red)',
      labels: { min: '15°C', max: '40°C' }
    },
    NDVI: {
      title: 'NDVI (Vegetation Index)',
      gradient: 'linear-gradient(to right, brown, yellow, lightgreen, darkgreen)',
      labels: { min: '0', max: '0.8' }
    }
  };

  const legend = legends[dataType] || legends.LST;

  return (
    <div className="map-legend">
      <div className="legend-title">{legend.title}</div>
      <div 
        className="legend-gradient" 
        style={{ background: legend.gradient }}
      ></div>
      <div className="legend-labels">
        <span>{legend.labels.min}</span>
        <span>{legend.labels.max}</span>
      </div>
    </div>
  );
};

const MapDashboard = () => {
  // State management
  const [tileUrl, setTileUrl] = useState('');
  const [dataType, setDataType] = useState('LST'); // 'LST' or 'NDVI'
  // Initialize with previous month since current month data may not be available
  const currentDate = new Date();
  const previousMonth = new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1);
  const [selectedYear, setSelectedYear] = useState(previousMonth.getFullYear());
  const [selectedMonth, setSelectedMonth] = useState(previousMonth.getMonth() + 1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [customAOI, setCustomAOI] = useState(null); // Custom Area of Interest
  const [useCustomAOI, setUseCustomAOI] = useState(false);
  const [aoiDetails, setAoiDetails] = useState(null); // Details about the drawn shape

  // Generate year and month options for the last 24 months (excluding current month)
  const generateDateOptions = () => {
    const options = [];
    const now = new Date();
    
    // Start from previous month and go back 24 months for more flexibility
    for (let i = 1; i <= 24; i++) {
      const date = new Date(now.getFullYear(), now.getMonth() - i, 1);
      
      // Only include dates from 2020 onwards
      if (date.getFullYear() >= 2020) {
        options.push({
          year: date.getFullYear(),
          month: date.getMonth() + 1,
          monthName: date.toLocaleString('default', { month: 'long' })
        });
      }
    }
    
    return options;
  };

  const dateOptions = generateDateOptions();
  const years = [...new Set(dateOptions.map(option => option.year))].sort((a, b) => b - a);

  // Fetch tile URL from backend API
  const fetchTileUrl = async (year, month, type, aoi = null) => {
    try {
      setLoading(true);
      setError(null);
      
      const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000';
      const params = { year, month, type };
      
      // Add AOI parameters if custom AOI is provided
      if (aoi) {
        params.aoi = JSON.stringify(aoi);
      }
      
      const response = await axios.get(`${apiBaseUrl}/api/map`, { params });
      
      if (response.data && response.data.url) {
        setTileUrl(response.data.url);
      } else {
        throw new Error('Invalid response format');
      }
    } catch (err) {
      console.error(`Error fetching ${type} tile URL:`, err);
      setError(`Failed to load ${type} data. Please try again.`);
      setTileUrl('');
    } finally {
      setLoading(false);
    }
  };

  // Effect to fetch data on mount and when date/type/AOI changes
  useEffect(() => {
    const aoi = useCustomAOI ? customAOI : null;
    fetchTileUrl(selectedYear, selectedMonth, dataType, aoi);
  }, [selectedYear, selectedMonth, dataType, customAOI, useCustomAOI]);

  // Handle year change
  const handleYearChange = (e) => {
    const newYear = parseInt(e.target.value);
    setSelectedYear(newYear);
    
    // Adjust month if the selected month is not available for the new year
    const availableMonths = dateOptions
      .filter(option => option.year === newYear)
      .map(option => option.month);
    
    if (!availableMonths.includes(selectedMonth)) {
      setSelectedMonth(Math.max(...availableMonths));
    }
  };

  // Handle month change
  const handleMonthChange = (e) => {
    setSelectedMonth(parseInt(e.target.value));
  };

  // Get available months for selected year
  const getAvailableMonths = () => {
    return dateOptions
      .filter(option => option.year === selectedYear)
      .sort((a, b) => b.month - a.month);
  };

  // Calculate area in square kilometers
  const calculateArea = (layer) => {
    if (layer.getRadius) {
      // Circle
      const radiusInMeters = layer.getRadius();
      return (Math.PI * radiusInMeters * radiusInMeters) / 1000000; // Convert to km²
    } else if (layer.getBounds) {
      // Rectangle or polygon
      const geoJSON = layer.toGeoJSON();
      if (geoJSON.geometry.type === 'Polygon') {
        // Use Leaflet's built-in area calculation for polygons
        const latLngs = layer.getLatLngs()[0];
        let area = 0;
        for (let i = 0; i < latLngs.length - 1; i++) {
          const p1 = latLngs[i];
          const p2 = latLngs[i + 1];
          area += p1.lng * p2.lat - p2.lng * p1.lat;
        }
        area = Math.abs(area / 2);
        // Convert from degrees² to km² (very rough approximation)
        return area * 12100; // 1 degree ≈ 110 km
      }
    }
    return null;
  };

  // Handle drawing events
  const onDrawCreated = (e) => {
    const { layer } = e;
    const geoJSON = layer.toGeoJSON();
    
    // Calculate shape details
    const area = calculateArea(layer);
    let shapeType = 'unknown';
    let vertexCount = 0;
    
    // Convert to format expected by backend
    let aoiBounds;
    if (geoJSON.geometry.type === 'Polygon') {
      const coordinates = geoJSON.geometry.coordinates[0];
      vertexCount = coordinates.length - 1; // Exclude closure point
      
      // Check if it's a rectangle (4 corners + closure = 5 points)
      if (coordinates.length === 5 && layer.getBounds) { 
        // Rectangle
        shapeType = 'rectangle';
        const bounds = layer.getBounds();
        aoiBounds = {
          type: 'rectangle',
          bounds: [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()]
        };
      } else {
        // Regular polygon
        shapeType = 'polygon';
        aoiBounds = {
          type: 'polygon',
          coordinates: coordinates
        };
      }
    }
    
    // Set AOI details for display
    const details = {
      type: shapeType,
      vertices: vertexCount,
      area: area ? area.toFixed(2) : 'Unknown',
      coordinates: geoJSON.geometry.coordinates[0]?.length || 0
    };
    
    setAoiDetails(details);
    
    if (aoiBounds) {
      setCustomAOI(aoiBounds);
      setUseCustomAOI(true);
    }
  };

  const onDrawDeleted = () => {
    setCustomAOI(null);
    setUseCustomAOI(false);
    setAoiDetails(null);
  };

  // Handle map click events
  const handleMapClick = async (lat, lng) => {
    console.log(`Map clicked at: ${lat}, ${lng}`);
    try {
      const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000';
      const response = await axios.get(`${apiBaseUrl}/api/pixel_value`, {
        params: { 
          lat, 
          lng, 
          year: selectedYear, 
          month: selectedMonth,
          type: dataType
        }
      });
      
      if (response.data && (response.data.temperature_celsius !== undefined || response.data.ndvi_value !== undefined)) {
        return {
          temperature: response.data.temperature_celsius,
          ndvi: response.data.ndvi_value,
          date: response.data.image_date,
          message: response.data.message
        };
      } else if (response.data && response.data.error) {
        return {
          error: response.data.error
        };
      }
    } catch (error) {
      console.error('Error fetching pixel value:', error);
      return {
        error: `Failed to get ${dataType} data for this location`
      };
    }
  };

  return (
    <div className="map-dashboard">
      {/* Controls */}
      <div className="map-controls">
        <div className="controls-row">
          {/* Data Type Toggle */}
          <div className="filter-group">
            <label htmlFor="data-type-select">Data Type:</label>
            <select
              id="data-type-select"
              value={dataType}
              onChange={(e) => setDataType(e.target.value)}
              disabled={loading}
            >
              <option value="LST">LST (Temperature)</option>
              <option value="NDVI">NDVI (Vegetation)</option>
            </select>
          </div>

          {/* Date Filters */}
          <div className="filter-group">
            <label htmlFor="year-select">Year:</label>
            <select
              id="year-select"
              value={selectedYear}
              onChange={handleYearChange}
              disabled={loading}
            >
              {years.map(year => (
                <option key={year} value={year}>
                  {year}
                </option>
              ))}
            </select>
          </div>
          
          <div className="filter-group">
            <label htmlFor="month-select">Month:</label>
            <select
              id="month-select"
              value={selectedMonth}
              onChange={handleMonthChange}
              disabled={loading}
            >
              {getAvailableMonths().map(option => (
                <option key={`${option.year}-${option.month}`} value={option.month}>
                  {option.monthName}
                </option>
              ))}
            </select>
          </div>

          {/* AOI Toggle */}
          <div className="filter-group">
            <label>
              <input
                type="checkbox"
                checked={useCustomAOI}
                onChange={(e) => {
                  setUseCustomAOI(e.target.checked);
                  if (!e.target.checked) {
                    setCustomAOI(null);
                    setAoiDetails(null);
                  }
                }}
                disabled={loading}
              />
              <span style={{ marginLeft: '5px' }}>Use Custom AOI</span>
            </label>
            {customAOI && aoiDetails && (
              <div className="aoi-details" style={{ fontSize: '12px', color: '#e2e8f0', marginLeft: '10px' }}>
                <strong style={{ color: '#63b3ed' }}>{aoiDetails.type.toUpperCase()}</strong> • {aoiDetails.vertices} vertices • {aoiDetails.area} km²
              </div>
            )}
          </div>
        </div>
        
        {loading && <div className="loading-indicator">Loading {dataType} data...</div>}
        {error && <div className="error-message">{error}</div>}
      </div>

      {/* Map Container */}
      <div className="map-container">
        <MapContainer
          center={[-6.0, -60.0]} // Amazon rainforest center coordinates
          zoom={6}
          style={{ height: '100%', width: '100%' }}
        >
          {/* Map Click Handler */}
          <MapClickHandler onMapClick={handleMapClick} />
          
          {/* Drawing Controls */}
          <GeomanControls 
            onDrawCreated={onDrawCreated}
            onDrawDeleted={onDrawDeleted}
          />
          
          {/* Layers Control */}
          <LayersControl position="topright">
            {/* Base Layers */}
            <LayersControl.BaseLayer checked name="OpenStreetMap">
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
            </LayersControl.BaseLayer>
            
            <LayersControl.BaseLayer name="Satellite">
              <TileLayer
                attribution='&copy; <a href="https://www.esri.com/">Esri</a>'
                url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
              />
            </LayersControl.BaseLayer>
            
            {/* Data Overlay Layer */}
            {tileUrl && (
              <LayersControl.Overlay checked name={`${dataType} Data`}>
                <TileLayer
                  url={tileUrl}
                  attribution={`${dataType} Data from Google Earth Engine`}
                  opacity={0.4}
                />
              </LayersControl.Overlay>
            )}
          </LayersControl>
        </MapContainer>
        
        {/* Map Legend */}
        <MapLegend dataType={dataType} />
      </div>
    </div>
  );
};

export default MapDashboard;