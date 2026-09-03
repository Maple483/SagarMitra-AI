/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useRef, useState } from 'react';
import { Send, Ship, Anchor, Layers, X, Activity, ShieldAlert, Download, Upload, MapPin, Trash2, Info, ExternalLink, Plus, MoreVertical, Search, Navigation, Wind, Fish } from 'lucide-react';
import { WeatherQuickWidget } from './components/WeatherQuickWidget';
import { WeatherMapDrawer } from './components/WeatherMapDrawer';
import { MarineProductivityModal } from './components/marine_productivity';

declare global {
  interface Window {
    L: any;
  }
}

interface Vessel {
  id: string;
  name: string;
  type: string;
  speed: string;
  status: string;
  lat: number;
  lng: number;
}

interface CustomMarker {
  id: string;
  lat: number;
  lng: number;
  alias: string;
}

interface Message {
  role: string;
  content: string;
  isLoaded?: boolean;
}

const MOCK_VESSELS: Vessel[] = [
  { id: 'V1', name: 'ORCA-1', type: 'Patrol', speed: '24 knots', status: 'Active Monitoring', lat: 15.4, lng: 73.8 },
  { id: 'V2', name: 'MV Sagar', type: 'Cargo', speed: '12 knots', status: 'In Transit', lat: 18.9, lng: 72.8 },
  { id: 'V3', name: 'INS Vikram', type: 'Navy', speed: '30 knots', status: 'Patrol', lat: 9.9, lng: 76.2 },
  { id: 'V4', name: 'Oceanic 5', type: 'Fishing', speed: '8 knots', status: 'Stationary', lat: 13.0, lng: 80.3 },
];

export default function App() {
  const mapRef = useRef<any>(null);
  const vesselLayerRef = useRef<any>(null);
  const waveLayerRef = useRef<any>(null);
  const eezLayerRef = useRef<any>(null);
  const customMarkersLayerRef = useRef<any>(null);
  const cycloneLayerRef = useRef<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [messages, setMessages] = useState<Message[]>([
    { role: 'system', content: 'ORCA Marine Intelligence Platform initialized. Awaiting queries... (Tip: Ask about a "hazard" or "storm")' }
  ]);
  const [inputValue, setInputValue] = useState('');
  
  const [layers, setLayers] = useState({
    vessels: true,
    waves: false,
    eez: true, // Default to true now to highlight India
    cyclones: true // IMD Live Cyclone & Gale Warnings
  });
  
  const [selectedVessel, setSelectedVessel] = useState<Vessel | null>(null);
  const [showLayerControl, setShowLayerControl] = useState(false);
  const [isProductivityModalOpen, setIsProductivityModalOpen] = useState(false);
  
  const [mouseCoords, setMouseCoords] = useState({ lat: 0, lng: 0 });
  const [customMarkers, setCustomMarkers] = useState<CustomMarker[]>([]);
  const [showAddMarker, setShowAddMarker] = useState(false);
  const [markerInput, setMarkerInput] = useState({ lat: '', lng: '', alias: '' });
  const [showDataSources, setShowDataSources] = useState(false);
  const [loading, setLoading] = useState(false);
  
  const [showSettingsMenu, setShowSettingsMenu] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [contextMenu, setContextMenu] = useState<{lat: number, lng: number, x: number, y: number, isTemp?: boolean, approxName?: string} | null>(null);
  
  const [tempMarker, setTempMarker] = useState<{lat: number, lng: number} | null>(null);
  const tempMarkerLayerRef = useRef<any>(null);
  
  const [routes, setRoutes] = useState<any[]>([]);
  const routesLayerRef = useRef<any>(null);
  const [activeMarkerId, setActiveMarkerId] = useState<string | null>(null);
  const [showAllRoutes, setShowAllRoutes] = useState<boolean>(true);

  const [isWeatherDrawerOpen, setIsWeatherDrawerOpen] = useState(false);
  const [weatherCoords, setWeatherCoords] = useState({ lat: 18.95, lon: 72.85 });

  useEffect(() => {
    const initMap = () => {
      if (!window.L || mapRef.current) return;

      const map = window.L.map('marine-map', {
        zoomControl: false,
      }).setView([17.0, 73.0], 5);

      window.L.control.zoom({ position: 'bottomright' }).addTo(map);

      window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        className: 'dark-map',
        maxZoom: 20
      }).addTo(map);

      // Track mouse coordinates
      map.on('mousemove', (e: any) => {
        setMouseCoords({ lat: e.latlng.lat, lng: e.latlng.lng });
      });

      // Context menu for right click
      map.on('contextmenu', (e: any) => {
        setContextMenu({
          lat: e.latlng.lat,
          lng: e.latlng.lng,
          x: e.originalEvent.clientX,
          y: e.originalEvent.clientY
        });
      });
      map.on('click', (e: any) => { 
        setContextMenu(null); 
        setShowSettingsMenu(false); 
        const clickLat = Math.round(e.latlng.lat * 10000) / 10000;
        const clickLon = Math.round(e.latlng.lng * 10000) / 10000;
        setWeatherCoords({ lat: clickLat, lon: clickLon });
        setTempMarker(prev => {
          if (prev) return null; // clicking empty map removes existing temp marker
          return { lat: e.latlng.lat, lng: e.latlng.lng };
        });
      });
      map.on('dragstart', () => { setContextMenu(null); setShowSettingsMenu(false); });

      // Create Layer Groups
      const vesselsGrp = window.L.layerGroup();
      const wavesGrp = window.L.layerGroup();
      const eezGrp = window.L.layerGroup();
      customMarkersLayerRef.current = window.L.layerGroup().addTo(map);
      tempMarkerLayerRef.current = window.L.layerGroup().addTo(map);
      routesLayerRef.current = window.L.layerGroup().addTo(map);

      // 1. Vessels
      MOCK_VESSELS.forEach(v => {
        const icon = window.L.divIcon({
          className: 'bg-transparent',
          html: `<div class="w-4 h-4 bg-blue-500 rounded-full border-2 border-blue-200 shadow-[0_0_15px_rgba(59,130,246,0.8)] cursor-pointer hover:bg-blue-400 transition-colors"></div>`,
          iconSize: [16, 16],
          iconAnchor: [8, 8]
        });
        const marker = window.L.marker([v.lat, v.lng], { icon });
        marker.on('click', () => setSelectedVessel(v));
        vesselsGrp.addLayer(marker);
      });

      // 2. High Waves
      window.L.circle([15.5, 71.0], {
        color: '#ef4444',
        fillColor: '#ef4444',
        fillOpacity: 0.2,
        radius: 180000
      }).bindPopup('<div class="font-bold text-red-600">High Wave Alert: 4.5m swells (180 km radius)</div>').addTo(wavesGrp);

      window.L.circle([11.5, 81.5], {
        color: '#ef4444',
        fillColor: '#ef4444',
        fillOpacity: 0.2,
        radius: 160000
      }).bindPopup('<div class="font-bold text-red-600">High Wave Alert: 3.2m swells (160 km radius)</div>').addTo(wavesGrp);

      // 3. Indian EEZ & IMBL Maritime Boundaries (Matching Official Marine Regions / UNCLOS Dataset)
      const eezOuterBoundary: [number, number][] = [
        [23.85, 68.10],  // Sir Creek / Pakistan Maritime Boundary
        [21.80, 66.10],  // Kutch Outer Continental Shelf
        [20.40, 65.80],  // Saurashtra Outer EEZ Limit
        [17.50, 68.30],  // Maharashtra Outer EEZ 200 NM Limit
        [14.50, 69.20],  // Goa Outer EEZ Limit
        [12.50, 68.50],  // West of Northern Lakshadweep
        [10.00, 68.30],  // West of Central Lakshadweep
        [8.00, 69.50],   // Southwest of Lakshadweep
        [7.60, 71.00],   // Eight Degree Channel West
        [7.60, 73.50],   // Eight Degree Channel Median Line (India-Maldives Boundary)
        [7.80, 74.80],   // Eight Degree Channel East
        [4.784, 77.023], // Point T: India - Sri Lanka - Maldives Trijunction (Southward Arrowhead Point)
        [7.20, 78.60],   // Wadge Bank / Gulf of Mannar Entry
        [8.60, 79.20],   // Gulf of Mannar Median Line
        [9.15, 79.52],   // Adam's Bridge / Rameswaram (IMBL Treaty)
        [9.80, 79.80],   // Palk Bay Median Line
        [10.20, 80.30],  // Palk Strait Exit (North of Jaffna / Point Pedro)
        [11.50, 83.50],  // Bay of Bengal (East of Tamil Nadu)
        [13.50, 85.00],  // Bay of Bengal (East of Andhra Pradesh)
        [16.00, 86.50],  // Bay of Bengal (East of Visakhapatnam)
        [18.00, 88.50],  // Bay of Bengal (East of Odisha)
        [21.15, 89.40],  // India - Bangladesh Maritime Boundary (UNCLOS 2014 Award)
        [21.65, 89.15]   // West Bengal Coast
      ];

      // Outer Maritime Boundary Line (Dashed Blue Line exclusively in the Ocean)
      window.L.polyline(eezOuterBoundary, {
        color: '#3b82f6',
        weight: 2.5,
        dashArray: '6, 8',
        opacity: 0.95
      }).bindPopup('<div class="font-bold text-blue-600">Indian EEZ & Maritime Boundary (UNCLOS / 1974 & 1976 IMBL Treaties)</div>').addTo(eezGrp);

      // Light Sea Tint Polygon (No stroke on mainland coast)
      const eezSeaPolygon: [number, number][] = [
        ...eezOuterBoundary,
        [20.5, 86.8], [19.0, 84.8], [17.0, 82.5], [13.0, 80.3], [10.0, 79.8],
        [8.1, 77.5], [10.0, 75.8], [13.0, 74.8], [15.5, 73.8], [19.0, 72.8],
        [21.0, 72.0], [23.0, 68.5], [23.70, 68.05]
      ];
      window.L.polygon(eezSeaPolygon, {
        stroke: false,
        fill: true,
        fillColor: '#3b82f6',
        fillOpacity: 0.08
      }).addTo(eezGrp);

      // 4. IMD Live Cyclone & Gale Warning Bulletins Layer
      const cyclonesGrp = window.L.layerGroup();
      cycloneLayerRef.current = cyclonesGrp;

      // Fetch Live IMD Cyclone Bulletins & Gale Polygons from Backend
      fetch('http://localhost:8000/api/weather/cyclone_alerts')
        .then(res => res.json())
        .then(data => {
          if (data && data.bulletins) {
            data.bulletins.forEach((bulletin: any) => {
              const isRed = bulletin.warning_level === 'RED_WARNING';
              const strokeColor = isRed ? '#ef4444' : '#f97316';
              const fillColor = isRed ? '#dc2626' : '#ea580c';

              // 1. Gale Warning Danger Polygon (35kt+ / 50kt+ winds)
              if (bulletin.gale_warning_polygon && bulletin.gale_warning_polygon.length > 0) {
                window.L.polygon(bulletin.gale_warning_polygon, {
                  color: strokeColor,
                  weight: 2,
                  dashArray: '6, 6',
                  fill: true,
                  fillColor: fillColor,
                  fillOpacity: 0.18
                }).bindPopup(`
                  <div class="p-2 min-w-[200px]">
                    <div class="flex items-center gap-1.5 font-bold ${isRed ? 'text-red-500' : 'text-orange-400'} text-xs uppercase tracking-wider mb-1">
                      <span>⚠️ ${bulletin.warning_level.replace('_', ' ')}</span>
                    </div>
                    <div class="text-sm font-bold text-slate-800">${bulletin.name}</div>
                    <div class="text-xs text-slate-600 mt-1">Category: <b>${bulletin.intensity_category}</b></div>
                    <div class="text-xs text-slate-600">Gale Winds: <b>${bulletin.max_sustained_winds_kmh} km/h</b> (Gusts: ${bulletin.max_gusts_kmh} km/h)</div>
                    <div class="text-xs text-slate-600">Pressure: <b>${bulletin.central_pressure_hpa} hPa</b> | Motion: ${bulletin.movement_direction} at ${bulletin.movement_speed_kmh} km/h</div>
                    <div class="text-[11px] text-slate-700 bg-slate-100 p-1.5 rounded mt-2 border border-slate-200">
                      ${bulletin.fishermen_warning_text}
                    </div>
                  </div>
                `).addTo(cyclonesGrp);
              }

              // 2. Cyclone Eye / Center Marker
              const eyeIcon = window.L.divIcon({
                className: 'cyclone-eye-icon',
                html: `
                  <div class="w-8 h-8 rounded-full ${isRed ? 'bg-red-600' : 'bg-orange-600'} border-2 border-white flex items-center justify-center text-white text-xs font-black shadow-lg animate-pulse">
                    🌀
                  </div>
                `,
                iconSize: [32, 32],
                iconAnchor: [16, 16]
              });

              window.L.marker([bulletin.center_lat, bulletin.center_lon], { icon: eyeIcon })
                .bindPopup(`
                  <div class="p-2">
                    <div class="font-bold text-sm text-red-600 flex items-center gap-1">
                      🌀 Center of ${bulletin.name}
                    </div>
                    <div class="text-xs text-slate-600 mt-1">Eye Coordinates: ${bulletin.center_lat.toFixed(2)}°N, ${bulletin.center_lon.toFixed(2)}°E</div>
                    <div class="text-xs font-medium text-slate-800">Max Winds: ${bulletin.max_sustained_winds_kmh} km/h</div>
                  </div>
                `).addTo(cyclonesGrp);

              // 3. Projected Forecast Track
              if (bulletin.predicted_track && bulletin.predicted_track.length > 1) {
                const trackCoords = bulletin.predicted_track.map((t: any) => [t.lat, t.lon]);
                window.L.polyline(trackCoords, {
                  color: strokeColor,
                  weight: 3,
                  dashArray: '4, 8',
                  opacity: 0.85
                }).bindPopup(`<b>${bulletin.name} Projected Track (Next 24-48h)</b>`).addTo(cyclonesGrp);
              }
            });
          }
        })
        .catch(err => console.warn('Could not fetch live cyclone alerts:', err));

      // Store refs and add default layers
      vesselLayerRef.current = vesselsGrp;
      waveLayerRef.current = wavesGrp;
      eezLayerRef.current = eezGrp;
      
      vesselsGrp.addTo(map);
      eezGrp.addTo(map);
      cyclonesGrp.addTo(map);

      mapRef.current = map;
      
      // Fix Leaflet container size bug (gray tiles)
      setTimeout(() => {
        map.invalidateSize();
      }, 250);
      
      window.addEventListener('resize', () => {
        if (mapRef.current) {
          mapRef.current.invalidateSize();
        }
      });
    };

    if (window.L) {
      initMap();
    } else {
      const scriptCheckInterval = setInterval(() => {
        if (window.L) {
          initMap();
          clearInterval(scriptCheckInterval);
        }
      }, 100);
      return () => clearInterval(scriptCheckInterval);
    }

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  // Handle Layer Toggles
  useEffect(() => {
    if (!mapRef.current) return;
    
    if (layers.vessels && vesselLayerRef.current) mapRef.current.addLayer(vesselLayerRef.current);
    else if (vesselLayerRef.current) mapRef.current.removeLayer(vesselLayerRef.current);
    
    if (layers.waves && waveLayerRef.current) mapRef.current.addLayer(waveLayerRef.current);
    else if (waveLayerRef.current) mapRef.current.removeLayer(waveLayerRef.current);
    
    if (layers.eez && eezLayerRef.current) mapRef.current.addLayer(eezLayerRef.current);
    else if (eezLayerRef.current) mapRef.current.removeLayer(eezLayerRef.current);

    if (layers.cyclones && cycloneLayerRef.current) mapRef.current.addLayer(cycloneLayerRef.current);
    else if (cycloneLayerRef.current) mapRef.current.removeLayer(cycloneLayerRef.current);
  }, [layers]);

  // Sync Routes to Leaflet
  useEffect(() => {
    if (!routesLayerRef.current || !window.L || !mapRef.current) return;
    routesLayerRef.current.clearLayers();
    
    routes.forEach(route => {
      const isRouteActive = activeMarkerId ? (route.id === activeMarkerId || route.markerId === activeMarkerId) : true;
      if (!showAllRoutes && !isRouteActive) return;

      const baseOpacity = isRouteActive ? 0.95 : 0.45;
      const baseWeight = isRouteActive ? 5 : 2.5;

      // If full multi-segment RouteResponse from backend
      if (route.segments && route.segments.length > 0) {
        route.segments.forEach((seg: any) => {
          const color = seg.risk_level === 'HIGH' ? '#ef4444' : (seg.risk_level === 'MEDIUM' ? '#f59e0b' : (isRouteActive ? '#10b981' : '#06b6d4'));
          const polyline = window.L.polyline([
            [seg.start_lat, seg.start_lon],
            [seg.end_lat, seg.end_lon]
          ], {
            color: color,
            weight: baseWeight,
            opacity: baseOpacity,
            dashArray: seg.risk_level === 'HIGH' ? '6, 6' : undefined
          }).addTo(routesLayerRef.current);

          polyline.bindPopup(`
            <div class="font-bold text-slate-800 text-sm">Safe Nautical Leg (${seg.risk_level} Risk)</div>
            <div class="text-xs text-slate-600 mt-1">
              <b>Leg Distance:</b> ${seg.distance_nm} NM<br/>
              <b>Compass Bearing:</b> ${seg.bearing_deg}°<br/>
              <b>Leg ETE:</b> ${seg.nominal_ete_hours} hrs (at 10 kts)<br/>
              <b>Overall Route (${route.alias || route.vesselName || 'Vessel'}):</b> ${route.total_dist_nm} NM (Nominal ETE: ${route.nominal_ete_hours} hrs)
            </div>
          `);
        });

        // Place markers for Start, Waypoints, and Destination
        if (route.waypoints) {
          route.waypoints.forEach((wp: any, idx: number) => {
            const isStart = idx === 0;
            const isEnd = idx === route.waypoints.length - 1;
            const markerColor = isStart ? '#10b981' : (isEnd ? '#06b6d4' : '#f59e0b');
            const size = isRouteActive ? 24 : 18;
            
            const icon = window.L.divIcon({
              className: 'bg-transparent',
              html: `<div class="flex items-center justify-center rounded-full text-white font-bold text-[10px] shadow-md border-2 border-white ${isRouteActive ? 'ring-2 ring-cyan-400' : 'opacity-70'}" style="width: ${size}px; height: ${size}px; background-color: ${markerColor}">
                ${isStart ? 'S' : (isEnd ? 'D' : idx)}
              </div>`,
              iconSize: [size, size],
              iconAnchor: [size / 2, size / 2]
            });

            window.L.marker([wp.lat, wp.lon], { icon }).addTo(routesLayerRef.current)
              .bindPopup(`
                <div class="font-bold text-slate-800 text-xs">${wp.name} ${route.alias ? `· ${route.alias}` : ''}</div>
                <div class="text-[11px] text-slate-600">
                  Lat: ${wp.lat}, Lon: ${wp.lon}<br/>
                  Cumulative Distance: ${wp.cumulative_distance_nm} NM
                </div>
              `);
          });
        }
      } else if (route.start && route.end) {
        // Fallback for simple 2-point routes
        const polyline = window.L.polyline([route.start, route.end], {
          color: isRouteActive ? '#10b981' : '#06b6d4',
          dashArray: '8, 8',
          weight: baseWeight,
          opacity: baseOpacity
        }).addTo(routesLayerRef.current);
        
        polyline.bindPopup(`<div class="font-bold text-emerald-600">Active Route (${route.alias || route.vesselName || 'Vessel'})</div>
        <div class="text-xs text-slate-700 mt-1">From: ${route.vesselName || 'Vessel'}<br/>Distance: ${route.distNm || ''} NM<br/>ETA: ${route.time || ''}</div>`);
      }
    });
  }, [routes, activeMarkerId, showAllRoutes]);

  // Sync Temp Marker to Leaflet
  useEffect(() => {
    if (!tempMarkerLayerRef.current || !window.L || !mapRef.current) return;
    tempMarkerLayerRef.current.clearLayers();
    
    if (tempMarker) {
      const icon = window.L.divIcon({
        className: 'bg-transparent',
        html: `<div class="relative flex items-center justify-center w-8 h-8 group -mt-4">
                 <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#f43f5e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="drop-shadow-lg text-rose-500 cursor-grab active:cursor-grabbing">
                     <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/>
                     <circle cx="12" cy="10" r="3"/>
                 </svg>
                 <div class="absolute top-10 whitespace-nowrap bg-slate-900 border border-slate-700 text-xs text-slate-200 px-2 py-1 rounded shadow-lg pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity z-50">Draggable (Right-click for options)</div>
               </div>`,
        iconSize: [32, 32],
        iconAnchor: [16, 32]
      });
      
      const marker = window.L.marker([tempMarker.lat, tempMarker.lng], { icon, draggable: true });
      
      marker.on('dragend', (e: any) => {
        const pos = e.target.getLatLng();
        setTempMarker({ lat: pos.lat, lng: pos.lng });
      });

      marker.on('contextmenu', async (e: any) => {
        window.L.DomEvent.stopPropagation(e);
        
        let approxName = "Unknown Marine Region";
        try {
            const res = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${e.latlng.lat}&lon=${e.latlng.lng}&zoom=10`);
            if (res.ok) {
                const data = await res.json();
                if (data && data.name) approxName = data.name;
                else if (data && data.display_name) approxName = data.display_name.split(',')[0];
            }
        } catch(err) {}

        setContextMenu({
            lat: e.latlng.lat,
            lng: e.latlng.lng,
            x: e.originalEvent.clientX,
            y: e.originalEvent.clientY,
            isTemp: true,
            approxName
        });
      });
      
      marker.addTo(tempMarkerLayerRef.current);
    }
  }, [tempMarker]);

  // Sync Custom Markers to Leaflet
  useEffect(() => {
    if (!customMarkersLayerRef.current || !window.L || !mapRef.current) return;
    customMarkersLayerRef.current.clearLayers();
    
    customMarkers.forEach(cm => {
      const isSelected = activeMarkerId === cm.id;
      const associatedRoute = routes.find(r => r.id === cm.id || r.markerId === cm.id);

      const icon = window.L.divIcon({
        className: 'bg-transparent',
        html: `<div class="relative flex items-center justify-center w-7 h-7 group cursor-pointer">
                 <span class="absolute inline-flex h-full w-full rounded-full ${isSelected ? 'bg-cyan-400 opacity-80 animate-ping' : 'bg-yellow-400 opacity-50 animate-pulse'}"></span>
                 <span class="relative inline-flex items-center justify-center rounded-full h-5 w-5 ${isSelected ? 'bg-cyan-500 border-2 border-white text-white' : 'bg-yellow-500 border-2 border-slate-900 text-slate-900'} shadow-md text-[10px] font-bold">
                   📍
                 </span>
               </div>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14]
      });

      const marker = window.L.marker([cm.lat, cm.lng], { icon });

      const container = document.createElement('div');
      container.className = 'p-1';
      container.innerHTML = `
        <div class="font-bold text-sm ${isSelected ? 'text-cyan-600' : 'text-slate-800'}">${cm.alias}</div>
        <div class="text-[11px] text-slate-500 mt-0.5">${cm.lat.toFixed(4)}, ${cm.lng.toFixed(4)}</div>
        ${associatedRoute ? `
          <div class="mt-2 p-1.5 bg-slate-100 rounded text-[11px] text-slate-700">
            <div><b>Route Distance:</b> ${associatedRoute.total_dist_nm} NM</div>
            <div><b>Nominal ETE:</b> ${associatedRoute.nominal_ete_hours} hrs (${associatedRoute.vesselName || 'Vessel'})</div>
            ${associatedRoute.max_risk_level ? `<div><b>Risk Level:</b> <span class="font-bold ${associatedRoute.max_risk_level === 'HIGH' ? 'text-rose-600' : 'text-emerald-600'}">${associatedRoute.max_risk_level}</span></div>` : ''}
          </div>
        ` : '<div class="mt-1 text-[10px] text-slate-400 italic">No route calculated yet</div>'}
        <div class="mt-2.5 flex gap-1.5">
          <button id="btn-focus-${cm.id}" class="flex-1 bg-cyan-600 hover:bg-cyan-500 text-white font-bold py-1 px-2 rounded text-[11px] transition">
            ${associatedRoute ? 'Focus Route' : 'Compute Route'}
          </button>
          <button id="btn-del-${cm.id}" class="bg-rose-100 hover:bg-rose-200 text-rose-700 py-1 px-2 rounded text-[11px] transition">
            Delete
          </button>
        </div>
      `;

      marker.bindPopup(container);

      marker.on('popupopen', () => {
        const focusBtn = document.getElementById(`btn-focus-${cm.id}`);
        const delBtn = document.getElementById(`btn-del-${cm.id}`);
        if (focusBtn) {
          focusBtn.onclick = () => {
            computeRouteForMarker(cm);
          };
        }
        if (delBtn) {
          delBtn.onclick = () => {
            deleteCustomMarker(cm.id);
          };
        }
      });

      marker.on('click', () => {
        setActiveMarkerId(cm.id);
      });

      marker.addTo(customMarkersLayerRef.current);
    });
  }, [customMarkers, activeMarkerId, routes]);

  // Chat-to-Map Bridge
  const triggerMapEvent = (lat: number, lng: number, label: string) => {
    if (!mapRef.current) return;
    const alertIcon = window.L.divIcon({
      className: 'bg-transparent',
      html: `<div class="relative flex h-8 w-8">
               <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
               <span class="relative inline-flex rounded-full h-8 w-8 bg-red-600 border-2 border-slate-900 shadow-lg flex items-center justify-center">
                 <span class="text-[14px] font-bold text-white">!</span>
               </span>
             </div>`,
      iconSize: [32, 32],
      iconAnchor: [16, 16]
    });
    
    const alertMarker = window.L.marker([lat, lng], { icon: alertIcon }).addTo(mapRef.current);
    alertMarker.bindPopup(`<div class="font-bold text-red-600">${label}</div>`).openPopup();
    mapRef.current.flyTo([lat, lng], 6, { animate: true, duration: 1.5 });
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    try {
      const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchQuery)}`);
      const data = await res.json();
      setSearchResults(data);
    } catch (err) {
      console.error("Search failed", err);
    }
  };

  const handleSelectSearchResult = (result: any) => {
    const lat = parseFloat(result.lat);
    const lon = parseFloat(result.lon);
    if (mapRef.current) {
      mapRef.current.flyTo([lat, lon], 10);
    }
    setSearchResults([]);
    setSearchQuery('');
  };

  const handleContextAddMarker = () => {
    if (!contextMenu) return;
    setMarkerInput({ lat: contextMenu.lat.toFixed(4), lng: contextMenu.lng.toFixed(4), alias: contextMenu.approxName || '' });
    setShowAddMarker(true);
    setContextMenu(null);
    setTempMarker(null);
  };

  const handleContextAddToChat = () => {
    if (!contextMenu) return;
    setInputValue(prev => prev + (prev.endsWith(' ') || prev.length === 0 ? '' : ' ') + `[Lat: ${contextMenu.lat.toFixed(4)}, Lng: ${contextMenu.lng.toFixed(4)}] `);
    setContextMenu(null);
  };

  const quickPrompts = [
    "What is the live wind speed off the coast of Goa?",
    "Is vessel Alpha-7 at latitude 14.5 and longitude 71.8 safe?",
    "Scan boundary violation for vessel SeaKing at lat 15.0 long 72.0"
  ];

  const handleSendQuery = async (queryText: string) => {
    if (!queryText.trim()) return;
    
    setMessages(prev => [...prev, { role: 'user', content: queryText }]);
    setInputValue('');
    setLoading(true);

    // Context Injection for LLM Awareness
    let contextStr = `\n\n[SYSTEM CONTEXT: Do not acknowledge this block directly. Known Custom Markers: `;
    if (customMarkers.length > 0) {
contextStr += customMarkers.map(m => `"${m.alias}" is at Lat ${m.lat.toFixed(4)}, Lng ${m.lng.toFixed(4)}`).join('; ');
    } else {
      contextStr += `None.`;
    }
    if (routes.length > 0) {
      contextStr += ` | Active Routes: ` + routes.map(r => `From ${r.vesselName} to ${r.distNm} NM away (ETA: ${r.time})`).join('; ');
    }
    contextStr += ` | Map Hazards: Active Wave alert (4.5m swells, radius 180km) at Lat 15.5, Lng 71.0; Active Wave alert (3.2m swells, radius 160km) at Lat 11.5, Lng 81.5.]`;
    
    const payloadText = queryText + contextStr;

    try {
      const res = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: payloadText })
      });
      const data = await res.json();
      
      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply }]);
      
      if (data.route) {
        setRoutes([data.route]);
      }
      
      if (data.coordinates && mapRef.current) {
        mapRef.current.flyTo([data.coordinates.lat, data.coordinates.lng], 9);
      }
    } catch (err) {
      console.error(err);
      setMessages((prev) => [...prev, { role: 'assistant', content: 'Offline / Gateway Error: Backend not reachable.' }]);
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    handleSendQuery(inputValue);
  };

  const toggleLayer = (layer: keyof typeof layers) => {
    setLayers(prev => ({ ...prev, [layer]: !prev[layer] }));
  };

  // Compute / Focus Route for an existing custom marker
  const computeRouteForMarker = async (marker: CustomMarker) => {
    setActiveMarkerId(marker.id);
    if (mapRef.current) mapRef.current.flyTo([marker.lat, marker.lng], 7);

    // If route already exists in routes state, notify user
    const existing = routes.find(r => r.id === marker.id || r.markerId === marker.id);
    if (existing) {
      setMessages(prev => [...prev, {
        role: 'system',
        content: `Activated route to ${marker.alias}: ${existing.total_dist_nm} NM (Nominal ETE: ${existing.nominal_ete_hours} hrs from ${existing.vesselName || 'Vessel'}).`
      }]);
      return;
    }

    const target = window.L.latLng(marker.lat, marker.lng);
    let nearestVessel = MOCK_VESSELS[0];
    let minDist = Infinity;
    MOCK_VESSELS.forEach(v => {
      const dist = target.distanceTo(window.L.latLng(v.lat, v.lng));
      if (dist < minDist) {
        minDist = dist;
        nearestVessel = v;
      }
    });

    const speed = parseInt(nearestVessel.speed) || 12;

    try {
      const res = await fetch("http://localhost:8000/api/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start_lat: nearestVessel.lat,
          start_lon: nearestVessel.lng,
          target_lat: marker.lat,
          target_lon: marker.lng,
          vessel_name: nearestVessel.name,
          speed_knots: speed,
          system_context: "Active Wave alert (4.5m swells, radius 180km) at Lat 15.5, Lng 71.0; Active Wave alert (3.2m swells, radius 160km) at Lat 11.5, Lng 81.5"
        })
      });
      const routeData = await res.json();
      if (routeData.status === "SUCCESS") {
        setRoutes(prev => [
          ...prev.filter(r => r.id !== marker.id && r.markerId !== marker.id),
          { ...routeData, id: marker.id, markerId: marker.id, alias: marker.alias, vesselName: nearestVessel.name }
        ]);
        const advisory = routeData.message ? `${routeData.message} ` : '';
        setMessages(prev => [...prev, {
          role: 'system',
          content: `${advisory}Route to ${marker.alias}: ${routeData.total_dist_nm} NM (Nominal ETE: ${routeData.nominal_ete_hours} hrs from ${nearestVessel.name}).`
        }]);
      } else {
        setMessages(prev => [...prev, {
          role: 'system',
          content: `Warning: Unable to resolve route to ${marker.alias}: ${routeData.message || 'Target lies outside Indian EEZ jurisdiction'}.`
        }]);
      }
    } catch (err) {
      console.error("Failed to compute route for marker:", err);
    }
  };

  // Add Custom Marker with Dynamic A* Pathfinding
  const handleAddCustomMarker = async (e: React.FormEvent) => {
    e.preventDefault();
    const lat = parseFloat(markerInput.lat);
    const lng = parseFloat(markerInput.lng);
    if (isNaN(lat) || isNaN(lng) || !markerInput.alias) return;
    
    const newMarkerId = Date.now().toString();
    const markerAlias = markerInput.alias;
    setCustomMarkers(prev => [...prev, { id: newMarkerId, lat, lng, alias: markerAlias }]);
    setActiveMarkerId(newMarkerId);
    setMarkerInput({ lat: '', lng: '', alias: '' });
    setShowAddMarker(false);
    setTempMarker(null);
    if (mapRef.current) mapRef.current.flyTo([lat, lng], 7);

    // Find nearest vessel
    const target = window.L.latLng(lat, lng);
    let nearestVessel = MOCK_VESSELS[0];
    let minDist = Infinity;
    MOCK_VESSELS.forEach(v => {
      const dist = target.distanceTo(window.L.latLng(v.lat, v.lng));
      if (dist < minDist) {
        minDist = dist;
        nearestVessel = v;
      }
    });

    const speed = parseInt(nearestVessel.speed) || 12;

    try {
      const res = await fetch("http://localhost:8000/api/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start_lat: nearestVessel.lat,
          start_lon: nearestVessel.lng,
          target_lat: lat,
          target_lon: lng,
          vessel_name: nearestVessel.name,
          speed_knots: speed,
          system_context: "Active Wave alert (4.5m swells, radius 180km) at Lat 15.5, Lng 71.0; Active Wave alert (3.2m swells, radius 160km) at Lat 11.5, Lng 81.5"
        })
      });
      const routeData = await res.json();
      if (routeData.status === "SUCCESS") {
        setRoutes(prev => [
          ...prev.filter(r => r.id !== newMarkerId && r.markerId !== newMarkerId),
          { ...routeData, id: newMarkerId, markerId: newMarkerId, alias: markerAlias, vesselName: nearestVessel.name }
        ]);
        const advisory = routeData.message ? `${routeData.message} ` : '';
        setMessages(prev => [...prev, {
          role: 'system',
          content: `${advisory}Safe nautical route computed from ${nearestVessel.name} to ${markerAlias}. Total Distance: ${routeData.total_dist_nm} NM. Nominal ETE: ${routeData.nominal_ete_hours} hrs at ${speed} knots.`
        }]);
      } else {
        setMessages(prev => [...prev, {
          role: 'system',
          content: `Warning: Unable to resolve a route from ${nearestVessel.name} to ${markerAlias}: ${routeData.message || 'Target lies outside Indian EEZ jurisdiction'}.`
        }]);
      }
    } catch (err) {
      console.error("Failed to compute A* route:", err);
    }
  };

  const deleteCustomMarker = (id: string) => {
    setCustomMarkers(prev => prev.filter(m => m.id !== id));
    setRoutes(prev => prev.filter(r => r.id !== id && r.markerId !== id));
    if (activeMarkerId === id) {
      setActiveMarkerId(null);
    }
  };

  // Import / Export Chat
  const exportChat = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(messages));
    const downloadAnchorNode = document.createElement('a');
    downloadAnchorNode.setAttribute("href", dataStr);
    downloadAnchorNode.setAttribute("download", "orca_chat_history.json");
    document.body.appendChild(downloadAnchorNode);
    downloadAnchorNode.click();
    downloadAnchorNode.remove();
  };

  const importChat = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const loaded = JSON.parse(event.target?.result as string);
        if (Array.isArray(loaded)) {
          const markedAsLoaded = loaded.map(m => ({ ...m, isLoaded: true }));
          setMessages(markedAsLoaded);
        }
      } catch (err) {
        console.error("Failed to parse chat JSON");
      }
    };
    reader.readAsText(file);
  };

  return (
    <div className="flex flex-col md:flex-row h-screen w-full bg-slate-950 font-sans overflow-hidden">
      
      {/* Left Chat Panel */}
      <div className="w-full md:w-96 lg:w-[400px] h-[50vh] md:h-full flex flex-col bg-slate-900 border-b md:border-b-0 md:border-r border-slate-800 shadow-2xl z-10 shrink-0">
        <div className="p-4 bg-slate-950 flex items-center justify-between border-b border-slate-800 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-600/20 flex items-center justify-center border border-blue-500/30">
              <Anchor className="text-blue-400 w-6 h-6" />
            </div>
            <div>
              <h1 className="text-blue-50 font-bold text-lg leading-tight tracking-wide">ORCA Dashboard</h1>
              <p className="text-blue-400/60 text-xs font-medium tracking-wider uppercase">Marine Intelligence</p>
            </div>
          </div>
          <div className="flex items-center gap-2 relative">
            <button
              onClick={() => setIsProductivityModalOpen(true)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 bg-cyan-500/15 hover:bg-cyan-500/25 text-cyan-300 border border-cyan-500/30 rounded-lg text-xs font-semibold transition shadow-sm cursor-pointer"
              title="Open Marine Productivity & Fisheries Analyst"
            >
              <Fish className="w-3.5 h-3.5 text-cyan-400" />
              <span>Productivity</span>
            </button>
            <button onClick={() => setShowSettingsMenu(!showSettingsMenu)} className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition-colors cursor-pointer" title="Settings">
              <MoreVertical className="w-5 h-5" />
            </button>
            {showSettingsMenu && (
              <div className="absolute top-full right-0 mt-2 w-48 bg-slate-800 border border-slate-700 rounded-lg shadow-xl py-1 z-50 animate-in fade-in slide-in-from-top-2">
                <button onClick={() => { exportChat(); setShowSettingsMenu(false); }} className="w-full text-left px-4 py-2 text-sm text-slate-200 hover:bg-slate-700 flex items-center gap-2">
                  <Download className="w-4 h-4" /> Export Chat
                </button>
                <button onClick={() => { fileInputRef.current?.click(); setShowSettingsMenu(false); }} className="w-full text-left px-4 py-2 text-sm text-slate-200 hover:bg-slate-700 flex items-center gap-2">
                  <Upload className="w-4 h-4" /> Import Chat
                </button>
              </div>
            )}
            <input type="file" accept=".json" ref={fileInputRef} onChange={importChat} className="hidden" />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin scrollbar-thumb-slate-700">
          {messages.map((msg, idx) => (
            <div key={idx} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
              <div className={`
                max-w-[85%] p-3 rounded-2xl text-sm leading-relaxed relative
                ${msg.role === 'user' 
                  ? 'bg-blue-600 text-white rounded-br-sm shadow-[0_0_15px_rgba(37,99,235,0.2)]' 
                  : 'bg-slate-800 text-slate-200 rounded-bl-sm border border-slate-700'}
              `}>
                {msg.content}
                {msg.isLoaded && (
                  <div className="absolute -top-2 -right-2 bg-slate-700 text-[9px] px-1.5 py-0.5 rounded text-slate-300 border border-slate-600">
                    Old Chat
                  </div>
                )}
              </div>
              <span className="text-[10px] text-slate-500 mt-1 px-1">
                {msg.role === 'user' ? 'You' : 'ORCA System'}
              </span>
            </div>
          ))}
          {loading && (
            <div className="flex flex-col items-start">
              <div className="max-w-[85%] p-3 rounded-2xl text-sm leading-relaxed bg-slate-800 text-slate-400 rounded-bl-sm border border-slate-700 flex items-center gap-2">
                <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse delay-75"></div>
                <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse delay-150"></div>
              </div>
            </div>
          )}
        </div>

        <div className="p-4 bg-slate-950 border-t border-slate-800 shrink-0 flex flex-col">
          <div className="flex gap-2 mb-3 overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-slate-800">
            {quickPrompts.map((prompt, idx) => (
              <button 
                key={idx}
                onClick={() => handleSendQuery(prompt)}
                disabled={loading}
                className="text-xs bg-slate-800 hover:bg-slate-700 text-blue-400 px-3 py-1.5 rounded-full border border-blue-500/30 whitespace-nowrap transition-colors disabled:opacity-50"
              >
                {prompt}
              </button>
            ))}
          </div>
          <form onSubmit={handleSendMessage} className="relative flex items-center">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Query marine data (e.g., hazard)..."
              className="w-full bg-slate-900 border border-slate-700 rounded-full py-3 pl-4 pr-12 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
            />
            <button
              type="submit"
              disabled={!inputValue.trim()}
              className="absolute right-2 p-2 bg-blue-600 rounded-full text-white hover:bg-blue-500 disabled:opacity-50 disabled:hover:bg-blue-600 transition-colors"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      </div>

      {/* Right Map Panel */}
      <div className="flex-1 h-[50vh] md:h-full relative bg-slate-950 z-0">
        <div id="marine-map" className="absolute inset-0 w-full h-full"></div>
        
        {/* Quick Marine Weather Telemetry Widget */}
        <WeatherQuickWidget 
          coords={weatherCoords}
          onToggleDrawer={() => setIsWeatherDrawerOpen(true)}
          onLocationChange={(lat, lon) => setWeatherCoords({ lat, lon })}
        />

        {/* Map-Retained Weather Drawer Overlay */}
        <WeatherMapDrawer
          isOpen={isWeatherDrawerOpen}
          onClose={() => setIsWeatherDrawerOpen(false)}
          coords={weatherCoords}
          onUpdateCoords={(lat, lon) => {
            setWeatherCoords({ lat, lon });
            if (mapRef.current) mapRef.current.flyTo([lat, lon], 9);
          }}
        />
        
        {/* Top Floating Action Bar: Non-Colliding Responsive Layout */}
        <div className="absolute top-4 inset-x-4 z-[450] flex items-center justify-between pointer-events-none gap-3">
          {/* Top Left: Active Vessels Badge */}
          <div className="pointer-events-auto shrink-0 hidden sm:block">
            <div onClick={() => setShowDataSources(true)} className="bg-slate-900/90 backdrop-blur-md border border-slate-700/60 px-3 py-2 rounded-xl shadow-lg flex items-center gap-2.5 hover:bg-slate-800 transition-colors cursor-pointer group">
              <Ship className="text-blue-400 w-4 h-4" />
              <div>
                <p className="text-[10px] text-slate-400 font-medium flex items-center gap-1">Active Vessels <Info className="w-2.5 h-2.5 group-hover:text-blue-400" /></p>
                <p className="text-slate-100 font-bold text-sm leading-none mt-0.5">1,204</p>
              </div>
            </div>
          </div>

          {/* Top Center: Search Bar */}
          <div className="pointer-events-auto flex-1 max-w-xs md:max-w-sm">
            <form onSubmit={handleSearch} className="relative flex items-center">
              <input 
                type="text" 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search locations or coordinates..." 
                className="w-full bg-slate-900/90 backdrop-blur-md border border-slate-700/60 rounded-full py-2 pl-3.5 pr-9 text-xs text-white shadow-lg focus:outline-none focus:border-blue-500 transition-all"
              />
              <button type="submit" className="absolute right-2 p-1 text-slate-400 hover:text-white">
                <Search className="w-3.5 h-3.5" />
              </button>
            </form>
            {searchResults.length > 0 && (
              <div className="mt-2 bg-slate-900/95 backdrop-blur-md border border-slate-700/50 rounded-xl shadow-2xl overflow-hidden max-h-60 overflow-y-auto">
                <ul className="divide-y divide-slate-800">
                  {searchResults.map((res: any, idx) => (
                    <li key={idx}>
                      <button onClick={() => handleSelectSearchResult(res)} className="w-full text-left px-4 py-3 hover:bg-slate-800 transition-colors">
                        <p className="text-sm font-medium text-slate-200 truncate">{res.display_name}</p>
                        <p className="text-[10px] text-slate-500 mt-0.5">Lat: {parseFloat(res.lat).toFixed(4)}, Lng: {parseFloat(res.lon).toFixed(4)}</p>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Top Right: Floating Action Buttons */}
          <div className="pointer-events-auto flex items-center gap-2 shrink-0">
            <button
              onClick={() => {
                console.log("[ORCA] Opening Marine Productivity Modal");
                setIsProductivityModalOpen(true);
              }}
              className="flex items-center gap-1.5 bg-slate-900/95 backdrop-blur-md border border-cyan-400/60 px-3.5 py-2 rounded-full shadow-xl text-cyan-300 hover:text-white hover:bg-slate-800 transition-all font-semibold text-xs ring-2 ring-cyan-500/30 cursor-pointer"
              title="Marine Productivity & Fisheries Analyst"
            >
              <Fish className="w-4 h-4 text-cyan-400" />
              <span className="hidden sm:inline">Marine Productivity</span>
            </button>
            <button 
              onClick={() => setShowAddMarker(!showAddMarker)}
              className="bg-slate-900/90 backdrop-blur-md border border-slate-700/50 p-2.5 rounded-full shadow-lg text-slate-200 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
              title="Add Custom Marker"
            >
              <MapPin className="w-4 h-4" />
            </button>
            <button 
              onClick={() => setShowLayerControl(!showLayerControl)}
              className="bg-slate-900/90 backdrop-blur-md border border-slate-700/50 p-2.5 rounded-full shadow-lg text-slate-200 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
              title="Toggle Layers"
            >
              <Layers className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Layer Controls Dropdown Menu (Top Right) */}
        <div className="absolute top-16 right-4 z-[450] flex flex-col items-end gap-2">
          
          {showLayerControl && (
            <div className="bg-slate-900/95 backdrop-blur-md border border-slate-700/50 rounded-xl shadow-2xl p-4 w-56 flex flex-col gap-3">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Map Layers</h3>
              
              <label className="flex items-center justify-between cursor-pointer group">
                <span className="text-sm font-medium text-slate-200 group-hover:text-blue-400 transition-colors flex items-center gap-2">
                  <Ship className="w-4 h-4" /> Vessels
                </span>
                <input type="checkbox" checked={layers.vessels} onChange={() => toggleLayer('vessels')} className="w-4 h-4 rounded border-slate-600 text-blue-600 focus:ring-blue-500 bg-slate-800" />
              </label>

              <label className="flex items-center justify-between cursor-pointer group">
                <span className="text-sm font-medium text-slate-200 group-hover:text-red-400 transition-colors flex items-center gap-2">
                  <Activity className="w-4 h-4" /> High Waves
                </span>
                <input type="checkbox" checked={layers.waves} onChange={() => toggleLayer('waves')} className="w-4 h-4 rounded border-slate-600 text-blue-600 focus:ring-blue-500 bg-slate-800" />
              </label>

              <label className="flex items-center justify-between cursor-pointer group">
                <span className="text-sm font-medium text-slate-200 group-hover:text-cyan-400 transition-colors flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4" /> EEZ Geofence
                </span>
                <input type="checkbox" checked={layers.eez} onChange={() => toggleLayer('eez')} className="w-4 h-4 rounded border-slate-600 text-blue-600 focus:ring-blue-500 bg-slate-800" />
              </label>

              <label className="flex items-center justify-between cursor-pointer group">
                <span className="text-sm font-medium text-slate-200 group-hover:text-amber-400 transition-colors flex items-center gap-2">
                  <Wind className="w-4 h-4 text-red-500" /> IMD Cyclones & Gales
                </span>
                <input type="checkbox" checked={layers.cyclones} onChange={() => toggleLayer('cyclones')} className="w-4 h-4 rounded border-slate-600 text-red-600 focus:ring-red-500 bg-slate-800" />
              </label>
            </div>
          )}

          {showAddMarker && (
            <div className="bg-slate-900/95 backdrop-blur-md border border-slate-700/50 rounded-xl shadow-2xl w-72 flex flex-col overflow-hidden">
              <div className="p-3 bg-slate-800/50 border-b border-slate-700 flex items-center justify-between">
                <span className="text-sm font-bold text-slate-200">Custom Markers</span>
                <button onClick={() => setShowAddMarker(false)} className="text-slate-400 hover:text-white"><X className="w-4 h-4" /></button>
              </div>
              <form onSubmit={handleAddCustomMarker} className="p-4 flex flex-col gap-3 border-b border-slate-700">
                <div className="flex gap-2">
                  <input type="number" step="any" placeholder="Lat" value={markerInput.lat} onChange={e => setMarkerInput({...markerInput, lat: e.target.value})} className="w-1/2 bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-sm text-white" required />
                  <input type="number" step="any" placeholder="Lng" value={markerInput.lng} onChange={e => setMarkerInput({...markerInput, lng: e.target.value})} className="w-1/2 bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-sm text-white" required />
                </div>
                <input type="text" placeholder="Alias (e.g. Area 51)" value={markerInput.alias} onChange={e => setMarkerInput({...markerInput, alias: e.target.value})} className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-sm text-white" required />
                <button type="submit" className="w-full bg-blue-600 hover:bg-blue-500 text-white rounded py-1.5 text-sm font-medium flex justify-center items-center gap-2 transition-colors">
                  <Plus className="w-4 h-4" /> Add to Map
                </button>
              </form>
              <div className="flex items-center justify-between px-3.5 py-2 bg-slate-950/80 border-b border-slate-800 text-[11px]">
                <span className="text-slate-400 font-medium">Pointers ({customMarkers.length})</span>
                {customMarkers.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setShowAllRoutes(prev => !prev)}
                    className={`px-2 py-0.5 rounded text-[10px] font-bold border transition ${
                      showAllRoutes 
                        ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40' 
                        : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200'
                    }`}
                  >
                    {showAllRoutes ? 'All Routes' : 'Single Route'}
                  </button>
                )}
              </div>
              <div className="max-h-56 overflow-y-auto">
                {customMarkers.length === 0 ? (
                  <p className="p-4 text-xs text-slate-500 text-center">No custom markers added yet. Right-click map or use form above.</p>
                ) : (
                  <ul className="divide-y divide-slate-800/80">
                    {customMarkers.map(cm => {
                      const isSelected = activeMarkerId === cm.id;
                      const associatedRoute = routes.find(r => r.id === cm.id || r.markerId === cm.id);
                      return (
                        <li 
                          key={cm.id} 
                          onClick={() => computeRouteForMarker(cm)}
                          className={`p-3 flex justify-between items-center cursor-pointer transition ${
                            isSelected 
                              ? 'bg-cyan-950/40 border-l-2 border-cyan-400 text-cyan-200' 
                              : 'hover:bg-slate-800/50 text-slate-300'
                          }`}
                        >
                          <div className="flex-1 min-w-0 pr-2">
                            <div className="flex items-center gap-1.5">
                              <span className="text-xs">📍</span>
                              <p className={`text-xs font-bold truncate ${isSelected ? 'text-cyan-300' : 'text-yellow-400'}`}>
                                {cm.alias}
                              </p>
                              {associatedRoute && (
                                <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono border border-emerald-500/30">
                                  {associatedRoute.total_dist_nm} NM
                                </span>
                              )}
                            </div>
                            <p className="text-[10px] text-slate-400 mt-0.5 ml-4">{cm.lat.toFixed(4)}, {cm.lng.toFixed(4)}</p>
                          </div>
                          <div className="flex items-center gap-1">
                            <button 
                              type="button"
                              onClick={(e) => { e.stopPropagation(); computeRouteForMarker(cm); }}
                              title="Focus Route"
                              className={`p-1.5 rounded transition ${isSelected ? 'bg-cyan-500/30 text-cyan-300' : 'text-slate-400 hover:text-cyan-300 hover:bg-slate-800'}`}
                            >
                              <Navigation className="w-3.5 h-3.5" />
                            </button>
                            <button 
                              type="button"
                              onClick={(e) => { e.stopPropagation(); deleteCustomMarker(cm.id); }}
                              title="Delete Marker"
                              className="p-1.5 rounded text-slate-500 hover:text-red-400 hover:bg-slate-800 transition"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Selected Vessel Card (Bottom Right, above Zoom controls) */}
        {selectedVessel && (
          <div className="absolute bottom-6 md:bottom-12 right-12 md:right-4 z-[400] w-64 bg-slate-900/95 backdrop-blur-md border border-blue-500/30 rounded-xl shadow-2xl overflow-hidden animate-in slide-in-from-right-4 fade-in duration-300">
            <div className="p-3 bg-blue-600/10 border-b border-blue-500/20 flex justify-between items-center">
              <div className="flex items-center gap-2">
                <Ship className="w-4 h-4 text-blue-400" />
                <h3 className="font-bold text-slate-100 text-sm">{selectedVessel.name}</h3>
              </div>
              <button onClick={() => setSelectedVessel(null)} className="text-slate-400 hover:text-white transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-4 flex flex-col gap-3 text-sm">
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Type</span>
                <span className="font-medium text-slate-200">{selectedVessel.type}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Speed</span>
                <span className="font-medium text-slate-200">{selectedVessel.speed}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-slate-400">Status</span>
                <span className="font-medium text-emerald-400 bg-emerald-400/10 px-2 py-0.5 rounded text-xs">{selectedVessel.status}</span>
              </div>
              <div className="flex justify-between items-center mt-2 pt-2 border-t border-slate-700/50">
                <span className="text-slate-500 text-xs">GPS</span>
                <span className="text-slate-400 text-xs font-mono">{selectedVessel.lat.toFixed(4)}, {selectedVessel.lng.toFixed(4)}</span>
              </div>
            </div>
          </div>
        )}

        {/* Live Coordinates (Bottom Left) */}
        <div className="absolute bottom-4 left-4 z-[400] pointer-events-none">
          <div className="bg-slate-950/80 backdrop-blur-sm border border-slate-800 px-3 py-1.5 rounded text-[10px] font-mono text-slate-400 shadow-sm">
            LAT: {mouseCoords.lat.toFixed(4)} &nbsp;|&nbsp; LNG: {mouseCoords.lng.toFixed(4)}
          </div>
        </div>
      </div>

      {/* Context Menu Overlay */}
      {contextMenu && (
        <div 
          className="fixed z-[1000] bg-slate-900 border border-slate-700 shadow-2xl rounded-lg py-1 w-56 animate-in fade-in zoom-in-95 duration-100"
          style={{ 
            top: Math.min(contextMenu.y, window.innerHeight - 150), 
            left: Math.min(contextMenu.x, window.innerWidth - 240) 
          }}
        >
          <div className="px-4 py-2 border-b border-slate-800 mb-1">
            {contextMenu.approxName && (
              <p className="text-sm font-bold text-slate-200 truncate">{contextMenu.approxName}</p>
            )}
            <p className="text-[10px] text-slate-500 font-mono">
              {contextMenu.lat.toFixed(4)}, {contextMenu.lng.toFixed(4)}
            </p>
          </div>
          
          <button onClick={handleContextAddMarker} className="w-full text-left px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 flex items-center gap-2 transition-colors">
            <MapPin className="w-4 h-4 text-yellow-500" /> 
            {contextMenu.isTemp ? "Save Location & Route" : "Add Custom Marker"}
          </button>
          <button onClick={handleContextAddToChat} className="w-full text-left px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 flex items-center gap-2 transition-colors">
            <Send className="w-4 h-4 text-blue-500" /> Use in Chat
          </button>
          {contextMenu.isTemp && (
            <button onClick={() => { setTempMarker(null); setContextMenu(null); }} className="w-full text-left px-4 py-2 text-sm text-red-400 hover:bg-slate-800 flex items-center gap-2 transition-colors border-t border-slate-800 mt-1 pt-2">
              <X className="w-4 h-4" /> Remove Pointer
            </button>
          )}
        </div>
      )}

      {/* Data Sources Modal */}
      {showDataSources && (
        <div className="fixed inset-0 z-[1000] bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="p-5 border-b border-slate-800 flex justify-between items-center bg-slate-950">
              <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <Activity className="w-5 h-5 text-blue-500" /> System Data Sources
              </h2>
              <button onClick={() => setShowDataSources(false)} className="text-slate-400 hover:text-white"><X className="w-5 h-5" /></button>
            </div>
            <div className="p-6 space-y-6">
              <div>
                <h3 className="text-sm font-bold text-slate-300 mb-2">Active Vessels Tracking</h3>
                <p className="text-sm text-slate-400 leading-relaxed">
                  The active vessels count represents a live aggregate of commercial, patrol, and stationary marine traffic within the monitored Exclusive Economic Zone (EEZ).
                </p>
              </div>
              <div className="space-y-3">
                <h3 className="text-sm font-bold text-slate-300">Integrated APIs & Endpoints</h3>
                <a href="https://incois.gov.in" target="_blank" rel="noreferrer" className="flex items-center justify-between p-3 rounded-xl border border-slate-700/50 bg-slate-800/50 hover:bg-slate-800 hover:border-slate-600 transition-all group">
                  <div>
                    <p className="text-sm font-bold text-blue-400 group-hover:text-blue-300">INCOIS (ERDDAP)</p>
                    <p className="text-xs text-slate-500 mt-0.5">Ocean State Forecasts & Potential Fishing Zones</p>
                  </div>
                  <ExternalLink className="w-4 h-4 text-slate-500 group-hover:text-slate-300" />
                </a>
                <a href="https://mosdac.gov.in" target="_blank" rel="noreferrer" className="flex items-center justify-between p-3 rounded-xl border border-slate-700/50 bg-slate-800/50 hover:bg-slate-800 hover:border-slate-600 transition-all group">
                  <div>
                    <p className="text-sm font-bold text-blue-400 group-hover:text-blue-300">MOSDAC Data Pipeline</p>
                    <p className="text-xs text-slate-500 mt-0.5">Atmospheric data, cyclones, and chlorophyll</p>
                  </div>
                  <ExternalLink className="w-4 h-4 text-slate-500 group-hover:text-slate-300" />
                </a>
                <a href="https://bhuvan.nrsc.gov.in" target="_blank" rel="noreferrer" className="flex items-center justify-between p-3 rounded-xl border border-slate-700/50 bg-slate-800/50 hover:bg-slate-800 hover:border-slate-600 transition-all group">
                  <div>
                    <p className="text-sm font-bold text-blue-400 group-hover:text-blue-300">Bhuvan Web Services</p>
                    <p className="text-xs text-slate-500 mt-0.5">Dynamic reverse-geocoding & EEZ spatial boundaries</p>
                  </div>
                  <ExternalLink className="w-4 h-4 text-slate-500 group-hover:text-slate-300" />
                </a>
              </div>
            </div>
            <div className="p-4 bg-slate-950 border-t border-slate-800 flex justify-end">
              <button onClick={() => setShowDataSources(false)} className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-lg transition-colors">
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Marine Productivity & Fisheries Analyst Modal */}
      <MarineProductivityModal
        isOpen={isProductivityModalOpen}
        onClose={() => setIsProductivityModalOpen(false)}
      />

    </div>
  );
}
