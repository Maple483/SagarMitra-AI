/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect, useRef, useState } from 'react';
import { Send, Ship, Anchor, Layers, X, Activity, ShieldAlert, Download, Upload, MapPin, Trash2, Info, ExternalLink, Plus, MoreVertical, Search, Navigation, Wind, Fish, ArrowLeft, Loader2, GitCompare, Thermometer, Droplets, TrendingUp, TrendingDown, Minus, AlertTriangle } from 'lucide-react';

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

interface ProductivityAnnualRow {
  Year: number;
  catch: number;
  sst?: number;
  chlorophyll?: number;
  sst_anomaly?: number;
  chlorophyll_anomaly?: number;
  catch_z?: number;
  catch_anomaly?: boolean;
  catch_growth_pct?: number;
}

interface ProductivitySeasonalRow {
  Season: string;
  mean_catch: number;
  mean_sst: number;
  mean_chlorophyll: number;
  months: number;
}

interface ProductivityTopSpecies {
  Species: string;
  catch_tonnes: number;
}

interface ProductivityAnalysis {
  state: string;
  species_filter: string | null;
  environment_is_synthetic: boolean;
  annual: ProductivityAnnualRow[];
  seasonal: ProductivitySeasonalRow[];
  top_species: ProductivityTopSpecies[];
  species: string[];
  correlation: { catch_vs_sst: number | null; catch_vs_chlorophyll: number | null };
  anomaly_rule: string;
  anomalies: { Year: number; catch: number; catch_z: number }[];
  explanation: { direction: string; text: string; caution: string; peak_season: string | null };
}

const MOCK_VESSELS: Vessel[] = [
  { id: 'V1', name: 'ORCA-1', type: 'Patrol', speed: '24 knots', status: 'Active Monitoring', lat: 15.4, lng: 73.8 },
  { id: 'V2', name: 'MV Sagar', type: 'Cargo', speed: '12 knots', status: 'In Transit', lat: 18.9, lng: 72.8 },
  { id: 'V3', name: 'INS Vikram', type: 'Navy', speed: '30 knots', status: 'Patrol', lat: 9.9, lng: 76.2 },
  { id: 'V4', name: 'Oceanic 5', type: 'Fishing', speed: '8 knots', status: 'Stationary', lat: 13.0, lng: 80.3 },
];

// ==========================================
// Lightweight inline SVG charts (no external chart library required)
// ==========================================
function MultiLineChart({
  data, lines, xKey, width = 560, height = 220
}: {
  data: any[];
  lines: { key: string; color: string; label: string }[];
  xKey: string;
  width?: number;
  height?: number;
}) {
  if (!data || data.length === 0) return <p className="text-xs text-slate-500 text-center py-8">No data available.</p>;

  const padding = { top: 16, right: 16, bottom: 28, left: 40 };
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;

  const allVals = lines.flatMap(l => data.map(d => Number(d[l.key]) || 0));
  const minV = Math.min(0, ...allVals);
  const maxV = Math.max(1, ...allVals);

  const xFor = (i: number) => padding.left + (data.length === 1 ? innerW / 2 : (i / (data.length - 1)) * innerW);
  const yFor = (v: number) => padding.top + innerH - ((v - minV) / (maxV - minV || 1)) * innerH;

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto min-w-[420px]">
        {/* gridlines */}
        {[0, 0.25, 0.5, 0.75, 1].map((f, i) => (
          <line key={i} x1={padding.left} x2={width - padding.right}
            y1={padding.top + innerH * f} y2={padding.top + innerH * f}
            stroke="#1e293b" strokeWidth="1" />
        ))}
        {/* x labels */}
        {data.map((d, i) => (
          (i === 0 || i === data.length - 1 || data.length <= 8) && (
            <text key={i} x={xFor(i)} y={height - 6} fontSize="9" textAnchor="middle" fill="#64748b">
              {d[xKey]}
            </text>
          )
        ))}
        {/* lines */}
        {lines.map(line => {
          const points = data.map((d, i) => `${xFor(i)},${yFor(Number(d[line.key]) || 0)}`).join(' ');
          return (
            <g key={line.key}>
              <polyline points={points} fill="none" stroke={line.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
              {data.map((d, i) => (
                <circle key={i} cx={xFor(i)} cy={yFor(Number(d[line.key]) || 0)} r="2.5" fill={line.color} />
              ))}
            </g>
          );
        })}
      </svg>
      <div className="flex flex-wrap gap-3 mt-2 px-2">
        {lines.map(line => (
          <div key={line.key} className="flex items-center gap-1.5 text-[11px] text-slate-400">
            <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ backgroundColor: line.color }}></span>
            {line.label}
          </div>
        ))}
      </div>
    </div>
  );
}

function BarChart({
  data, valueKey, labelKey, color = '#10b981', width = 560, height = 200
}: {
  data: any[];
  valueKey: string;
  labelKey: string;
  color?: string;
  width?: number;
  height?: number;
}) {
  if (!data || data.length === 0) return <p className="text-xs text-slate-500 text-center py-8">No data available.</p>;

  const padding = { top: 16, right: 16, bottom: 36, left: 40 };
  const innerW = width - padding.left - padding.right;
  const innerH = height - padding.top - padding.bottom;
  const maxV = Math.max(1, ...data.map(d => Number(d[valueKey]) || 0));
  const barW = innerW / data.length;

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto min-w-[420px]">
        {[0, 0.5, 1].map((f, i) => (
          <line key={i} x1={padding.left} x2={width - padding.right}
            y1={padding.top + innerH * f} y2={padding.top + innerH * f}
            stroke="#1e293b" strokeWidth="1" />
        ))}
        {data.map((d, i) => {
          const v = Number(d[valueKey]) || 0;
          const h = (v / maxV) * innerH;
          const x = padding.left + i * barW + barW * 0.15;
          const y = padding.top + innerH - h;
          return (
            <g key={i}>
              <rect x={x} y={y} width={barW * 0.7} height={h} fill={color} rx="2" opacity="0.85" />
              <text x={x + barW * 0.35} y={height - 20} fontSize="8.5" textAnchor="middle" fill="#94a3b8"
                transform={`rotate(-30 ${x + barW * 0.35} ${height - 20})`}>
                {String(d[labelKey]).length > 12 ? String(d[labelKey]).slice(0, 12) + '…' : d[labelKey]}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function CorrelationBadge({ label, value, icon }: { label: string; value: number | null; icon: any }) {
  const strength = value === null ? 'No data' : Math.abs(value) >= 0.5 ? 'Strong' : Math.abs(value) >= 0.2 ? 'Moderate' : 'Weak';
  const color = value === null ? 'text-slate-500 border-slate-700 bg-slate-800/40'
    : value > 0 ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
    : 'text-red-400 border-red-500/30 bg-red-500/10';
  return (
    <div className={`rounded-xl border p-3 flex items-center gap-3 ${color}`}>
      {icon}
      <div>
        <p className="text-[11px] opacity-70">{label}</p>
        <p className="text-lg font-bold leading-none mt-0.5">{value === null ? '—' : value.toFixed(2)}</p>
        <p className="text-[10px] opacity-60 mt-0.5">{strength} correlation</p>
      </div>
    </div>
  );
}

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

  // Marine Productivity — standalone full-screen view, independent of the map
  const [showProductivityView, setShowProductivityView] = useState(false);
  const [productivityRegions, setProductivityRegions] = useState<string[]>([]);
  const [productivityRegionsLoading, setProductivityRegionsLoading] = useState(false);
  const [productivityRegionsError, setProductivityRegionsError] = useState<string | null>(null);

  const [compareMode, setCompareMode] = useState(false);
  const [regionA, setRegionA] = useState('');
  const [regionB, setRegionB] = useState('');
  const [speciesFilter, setSpeciesFilter] = useState('');

  const [analysis, setAnalysis] = useState<ProductivityAnalysis | null>(null);
  const [comparison, setComparison] = useState<any | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

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
      window.L.circle([16.0, 71.0], {
        color: '#ef4444',
        fillColor: '#ef4444',
        fillOpacity: 0.2,
        radius: 120000
      }).bindPopup('<div class="font-bold text-red-600">High Wave Alert: 4.5m swells</div>').addTo(wavesGrp);

      window.L.circle([11.5, 81.5], {
        color: '#ef4444',
        fillColor: '#ef4444',
        fillOpacity: 0.2,
        radius: 80000
      }).bindPopup('<div class="font-bold text-red-600">High Wave Alert: 3.2m swells</div>').addTo(wavesGrp);

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
      // If full multi-segment RouteResponse from backend
      if (route.segments && route.segments.length > 0) {
        route.segments.forEach((seg: any) => {
          const color = seg.risk_level === 'HIGH' ? '#ef4444' : (seg.risk_level === 'MEDIUM' ? '#f59e0b' : '#10b981');
          const polyline = window.L.polyline([
            [seg.start_lat, seg.start_lon],
            [seg.end_lat, seg.end_lon]
          ], {
            color: color,
            weight: 4,
            opacity: 0.9,
            dashArray: seg.risk_level === 'HIGH' ? '6, 6' : undefined
          }).addTo(routesLayerRef.current);

          polyline.bindPopup(`
            <div class="font-bold text-slate-800 text-sm">Safe Nautical Leg (${seg.risk_level} Risk)</div>
            <div class="text-xs text-slate-600 mt-1">
              <b>Leg Distance:</b> ${seg.distance_nm} NM<br/>
              <b>Compass Bearing:</b> ${seg.bearing_deg}°<br/>
              <b>Leg ETE:</b> ${seg.nominal_ete_hours} hrs (at 10 kts)<br/>
              <b>Overall Route:</b> ${route.total_dist_nm} NM (Nominal ETE: ${route.nominal_ete_hours} hrs)
            </div>
          `);
        });

        // Place markers for Start, Waypoints, and Destination
        if (route.waypoints) {
          route.waypoints.forEach((wp: any, idx: number) => {
            const isStart = idx === 0;
            const isEnd = idx === route.waypoints.length - 1;
            const markerColor = isStart ? '#10b981' : (isEnd ? '#06b6d4' : '#f59e0b');
            
            const icon = window.L.divIcon({
              className: 'bg-transparent',
              html: `<div class="flex items-center justify-center w-6 h-6 rounded-full text-white font-bold text-[10px] shadow-md border-2 border-white" style="background-color: ${markerColor}">
                ${isStart ? 'S' : (isEnd ? 'D' : idx)}
              </div>`,
              iconSize: [24, 24],
              iconAnchor: [12, 12]
            });

            window.L.marker([wp.lat, wp.lon], { icon }).addTo(routesLayerRef.current)
              .bindPopup(`
                <div class="font-bold text-slate-800 text-xs">${wp.name}</div>
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
          color: '#10b981',
          dashArray: '8, 8',
          weight: 3,
          opacity: 0.8
        }).addTo(routesLayerRef.current);
        
        polyline.bindPopup(`<div class="font-bold text-emerald-600">Active Route</div>
        <div class="text-xs text-slate-700 mt-1">From: ${route.vesselName || 'Vessel'}<br/>Distance: ${route.distNm || ''} NM<br/>ETA: ${route.time || ''}</div>`);
      }
    });
  }, [routes]);

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
      const icon = window.L.divIcon({
        className: 'bg-transparent',
        html: `<div class="relative flex items-center justify-center w-6 h-6 group">
                 <span class="absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-50 animate-pulse"></span>
                 <span class="relative inline-flex rounded-full h-4 w-4 bg-yellow-500 border-2 border-slate-900 shadow-md"></span>
               </div>`,
        iconSize: [24, 24],
        iconAnchor: [12, 12]
      });
      window.L.marker([cm.lat, cm.lng], { icon })
        .bindPopup(`<div class="font-bold text-yellow-600">${cm.alias}</div><div class="text-xs text-slate-500 mt-1">${cm.lat.toFixed(4)}, ${cm.lng.toFixed(4)}</div>`)
        .addTo(customMarkersLayerRef.current);
    });
  }, [customMarkers]);

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
    contextStr += ` | Map Hazards: High wave alert (4.5m swells) at Lat 16.0, Lng 71.0; High wave alert (3.2m swells) at Lat 11.5, Lng 81.5.]`;
    
    const payloadText = queryText + contextStr;

    try {
      const res = await fetch("http://localhost:8000/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: payloadText })
      });
      const data = await res.json();
      
      setMessages((prev) => [...prev, { role: 'system', content: data.reply }]);
      
      if (data.route && data.route.status === "SUCCESS") {
        setRoutes([data.route]);
      }
      
      if (data.coordinates && mapRef.current) {
        mapRef.current.flyTo([data.coordinates.lat, data.coordinates.lng], 9);
      }
    } catch (err) {
      console.error(err);
      setMessages((prev) => [...prev, { role: 'system', content: 'Error connecting to backend. Ensure backend is running at http://localhost:8000. (Check console for details)' }]);
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

  // ==========================================
  // Marine Productivity — API calls
  // ==========================================
  const fetchProductivityRegions = async () => {
    setProductivityRegionsLoading(true);
    setProductivityRegionsError(null);
    try {
      const res = await fetch("http://localhost:8000/api/marine-productivity/regions");
      if (!res.ok) throw new Error(`Server responded ${res.status}`);
      const data = await res.json();
      const regions: string[] = data.regions || [];
      setProductivityRegions(regions);
      if (regions.length > 0 && !regionA) setRegionA(regions[0]);
      if (regions.length > 1 && !regionB) setRegionB(regions[1]);
    } catch (err) {
      console.error(err);
      setProductivityRegionsError("Could not reach backend. Ensure it is running at http://localhost:8000.");
    } finally {
      setProductivityRegionsLoading(false);
    }
  };

  const openProductivityView = () => {
    setShowProductivityView(true);
    if (productivityRegions.length === 0) fetchProductivityRegions();
  };

  const runProductivityAnalysis = async () => {
    if (!regionA) return;
    setAnalysisLoading(true);
    setAnalysisError(null);
    setAnalysis(null);
    setComparison(null);
    try {
      if (compareMode) {
        if (!regionB) { setAnalysisError("Select a second region to compare."); setAnalysisLoading(false); return; }
        const params = new URLSearchParams({ region_a: regionA, region_b: regionB });
        if (speciesFilter) params.set('species', speciesFilter);
        const res = await fetch(`http://localhost:8000/api/marine-productivity/compare?${params.toString()}`);
        if (!res.ok) throw new Error(`Server responded ${res.status}`);
        setComparison(await res.json());
      } else {
        const params = new URLSearchParams({ state: regionA });
        if (speciesFilter) params.set('species', speciesFilter);
        const res = await fetch(`http://localhost:8000/api/marine-productivity/analysis?${params.toString()}`);
        if (!res.ok) throw new Error(`Server responded ${res.status}`);
        setAnalysis(await res.json());
      }
    } catch (err) {
      console.error(err);
      setAnalysisError("Failed to fetch analysis. Ensure the backend is running and the region has data.");
    } finally {
      setAnalysisLoading(false);
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
          system_context: "Active Wave alert (4.5m swells) at Lat 16.0, Lng 71.0"
        })
      });
      const routeData = await res.json();
      if (routeData.status === "SUCCESS") {
        setRoutes([{ ...routeData, id: newMarkerId, vesselName: nearestVessel.name }]);
        setMessages(prev => [...prev, {
          role: 'system',
          content: `Safe nautical route computed from ${nearestVessel.name} to ${markerAlias} avoiding obstacles. Total Distance: ${routeData.total_dist_nm} NM. Nominal ETE: ${routeData.nominal_ete_hours} hrs at ${speed} knots.`
        }]);
      } else {
        setRoutes([]); // Clear invalid/stale routes so no ghost lines persist on the map
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
    setRoutes(prev => prev.filter(r => r.id !== id));
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
          <div className="flex gap-2 relative">
            <button onClick={() => setShowSettingsMenu(!showSettingsMenu)} className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition-colors" title="Settings">
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
        
        {/* Search Bar (Top Center) */}
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[400] w-full max-w-sm px-4 sm:px-0">
          <form onSubmit={handleSearch} className="relative flex items-center">
            <input 
              type="text" 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search locations or coordinates..." 
              className="w-full bg-slate-900/90 backdrop-blur-md border border-slate-700/50 rounded-full py-3 pl-4 pr-12 text-sm text-white shadow-lg focus:outline-none focus:border-blue-500 transition-all"
            />
            <button type="submit" className="absolute right-2 p-2 text-slate-400 hover:text-white">
              <Search className="w-4 h-4" />
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

        {/* Map Overlay Stats (Top Left) */}
        <div className="absolute top-4 left-4 z-[400] flex flex-col gap-2 hidden sm:flex">
          <div onClick={() => setShowDataSources(true)} className="bg-slate-900/80 backdrop-blur-md border border-slate-700/50 p-3 rounded-xl shadow-lg flex items-center gap-3 hover:bg-slate-800 transition-colors cursor-pointer group">
            <Ship className="text-blue-400 w-5 h-5" />
            <div>
              <p className="text-xs text-slate-400 font-medium flex items-center gap-1">Active Vessels <Info className="w-3 h-3 group-hover:text-blue-400" /></p>
              <p className="text-slate-100 font-bold text-lg leading-none mt-0.5">1,204</p>
            </div>
          </div>
        </div>

        {/* Floating Controls (Top Right) */}
        <div className="absolute top-4 right-4 z-[400] flex flex-col items-end gap-2">
          <div className="flex gap-2">
            <button 
              onClick={() => setShowAddMarker(!showAddMarker)}
              className="bg-slate-900/90 backdrop-blur-md border border-slate-700/50 p-3 rounded-full shadow-lg text-slate-200 hover:text-white hover:bg-slate-800 transition-colors"
              title="Add Custom Marker"
            >
              <MapPin className="w-5 h-5" />
            </button>
            <button 
              onClick={() => setShowLayerControl(!showLayerControl)}
              className="bg-slate-900/90 backdrop-blur-md border border-slate-700/50 p-3 rounded-full shadow-lg text-slate-200 hover:text-white hover:bg-slate-800 transition-colors"
              title="Toggle Layers"
            >
              <Layers className="w-5 h-5" />
            </button>
            <button 
              onClick={openProductivityView}
              className="bg-slate-900/90 backdrop-blur-md border border-slate-700/50 p-3 rounded-full shadow-lg text-slate-200 hover:text-white hover:bg-emerald-600 hover:border-emerald-500 transition-colors"
              title="Marine Productivity"
            >
              <Fish className="w-5 h-5" />
            </button>
          </div>
          
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
              <div className="max-h-40 overflow-y-auto">
                {customMarkers.length === 0 ? (
                  <p className="p-4 text-xs text-slate-500 text-center">No custom markers added yet.</p>
                ) : (
                  <ul className="divide-y divide-slate-800">
                    {customMarkers.map(cm => (
                      <li key={cm.id} className="p-3 flex justify-between items-center hover:bg-slate-800/50">
                        <div>
                          <p className="text-sm font-bold text-yellow-500">{cm.alias}</p>
                          <p className="text-[10px] text-slate-400">{cm.lat.toFixed(4)}, {cm.lng.toFixed(4)}</p>
                        </div>
                        <button onClick={() => deleteCustomMarker(cm.id)} className="text-slate-500 hover:text-red-400 p-1">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </li>
                    ))}
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

      {/* ============================================================
          Marine Productivity — standalone full-screen view.
          Slides over the entire app; completely separate from the map.
      ============================================================ */}
      {showProductivityView && (
        <div className="fixed inset-0 z-[1500] bg-slate-950 flex flex-col animate-in slide-in-from-right duration-300 overflow-y-auto">
          {/* Header */}
          <div className="sticky top-0 z-10 bg-slate-950/95 backdrop-blur-md border-b border-slate-800 px-4 sm:px-6 py-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setShowProductivityView(false)}
                className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition-colors"
                title="Back to Dashboard"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <div className="w-10 h-10 rounded-lg bg-emerald-600/20 flex items-center justify-center border border-emerald-500/30">
                <Fish className="text-emerald-400 w-6 h-6" />
              </div>
              <div>
                <h1 className="text-slate-100 font-bold text-lg leading-tight">Marine Productivity</h1>
                <p className="text-emerald-400/70 text-xs font-medium tracking-wider uppercase">Landings vs. SST &amp; Chlorophyll Analytics</p>
              </div>
            </div>
            <button
              onClick={() => setCompareMode(!compareMode)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                compareMode
                  ? 'bg-emerald-600 border-emerald-500 text-white'
                  : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'
              }`}
            >
              <GitCompare className="w-4 h-4" /> Compare Regions
            </button>
          </div>

          {/* Controls */}
          <div className="px-4 sm:px-6 py-4 border-b border-slate-800 bg-slate-900/50">
            {productivityRegionsLoading && (
              <p className="text-xs text-slate-500 flex items-center gap-2"><Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading coastal regions...</p>
            )}
            {productivityRegionsError && (
              <div className="flex items-center gap-2 text-xs text-red-400">
                <AlertTriangle className="w-3.5 h-3.5" /> {productivityRegionsError}
                <button onClick={fetchProductivityRegions} className="underline hover:text-red-300">Retry</button>
              </div>
            )}
            {!productivityRegionsLoading && !productivityRegionsError && productivityRegions.length > 0 && (
              <div className="flex flex-wrap items-end gap-3">
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] uppercase tracking-wider text-slate-500">{compareMode ? 'Region A' : 'Coastal Region'}</label>
                  <select
                    value={regionA}
                    onChange={e => setRegionA(e.target.value)}
                    className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white min-w-[180px] focus:outline-none focus:border-emerald-500"
                  >
                    {productivityRegions.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                </div>

                {compareMode && (
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] uppercase tracking-wider text-slate-500">Region B</label>
                    <select
                      value={regionB}
                      onChange={e => setRegionB(e.target.value)}
                      className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white min-w-[180px] focus:outline-none focus:border-emerald-500"
                    >
                      {productivityRegions.map(r => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </div>
                )}

                <div className="flex flex-col gap-1">
                  <label className="text-[10px] uppercase tracking-wider text-slate-500">Species (optional)</label>
                  <input
                    type="text"
                    value={speciesFilter}
                    onChange={e => setSpeciesFilter(e.target.value)}
                    placeholder="e.g. Sardines"
                    className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white w-40 focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <button
                  onClick={runProductivityAnalysis}
                  disabled={analysisLoading || !regionA}
                  className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors"
                >
                  {analysisLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Activity className="w-4 h-4" />}
                  Run Analysis
                </button>
              </div>
            )}
          </div>

          {/* Content */}
          <div className="flex-1 p-4 sm:p-6 space-y-6 max-w-5xl w-full mx-auto">
            {analysisError && (
              <div className="flex items-center gap-2 text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-xl p-4">
                <AlertTriangle className="w-4 h-4 shrink-0" /> {analysisError}
              </div>
            )}

            {!analysis && !comparison && !analysisLoading && !analysisError && (
              <div className="flex flex-col items-center justify-center text-center gap-3 py-24 text-slate-500">
                <Fish className="w-10 h-10 opacity-50" />
                <p className="text-sm">Select a region {compareMode ? 'pair' : ''} and run analysis to see landings, SST &amp; chlorophyll trends.</p>
              </div>
            )}

            {/* Single-region analysis */}
            {analysis && !compareMode && (
              <>
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
                  <div className="flex items-start justify-between flex-wrap gap-2 mb-3">
                    <div>
                      <h2 className="text-slate-100 font-bold text-base">{analysis.state}</h2>
                      {analysis.species_filter && <p className="text-xs text-slate-500">Species: {analysis.species_filter}</p>}
                    </div>
                    <span className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${
                      analysis.explanation.direction === 'increasing' ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' :
                      analysis.explanation.direction === 'decreasing' ? 'text-red-400 border-red-500/30 bg-red-500/10' :
                      'text-slate-400 border-slate-700 bg-slate-800/50'
                    }`}>
                      {analysis.explanation.direction === 'increasing' ? <TrendingUp className="w-3.5 h-3.5" /> :
                       analysis.explanation.direction === 'decreasing' ? <TrendingDown className="w-3.5 h-3.5" /> :
                       <Minus className="w-3.5 h-3.5" />}
                      {analysis.explanation.direction}
                    </span>
                  </div>
                  <p className="text-sm text-slate-300 leading-relaxed">{analysis.explanation.text}</p>
                  <p className="text-xs text-amber-400/80 mt-3 flex items-start gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {analysis.explanation.caution}
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <CorrelationBadge label="Catch vs. SST" value={analysis.correlation.catch_vs_sst} icon={<Thermometer className="w-6 h-6" />} />
                  <CorrelationBadge label="Catch vs. Chlorophyll" value={analysis.correlation.catch_vs_chlorophyll} icon={<Droplets className="w-6 h-6" />} />
                </div>

                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
                  <h3 className="text-sm font-bold text-slate-300 mb-4">Annual Catch (tonnes)</h3>
                  <MultiLineChart
                    data={analysis.annual}
                    xKey="Year"
                    lines={[{ key: 'catch', color: '#10b981', label: 'Catch (tonnes)' }]}
                  />
                </div>

                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
                  <h3 className="text-sm font-bold text-slate-300 mb-4">SST &amp; Chlorophyll Trends</h3>
                  <MultiLineChart
                    data={analysis.annual}
                    xKey="Year"
                    lines={[
                      { key: 'sst', color: '#f97316', label: 'SST (°C)' },
                      { key: 'chlorophyll', color: '#06b6d4', label: 'Chlorophyll (mg/m³)' },
                    ]}
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
                    <h3 className="text-sm font-bold text-slate-300 mb-4">Seasonal Mean Catch</h3>
                    <BarChart data={analysis.seasonal} valueKey="mean_catch" labelKey="Season" color="#10b981" />
                  </div>
                  <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5">
                    <h3 className="text-sm font-bold text-slate-300 mb-4">Top Species by Catch</h3>
                    <BarChart data={analysis.top_species} valueKey="catch_tonnes" labelKey="Species" color="#0ea5e9" />
                  </div>
                </div>

                {analysis.anomalies.length > 0 && (
                  <div className="bg-slate-900 border border-amber-500/20 rounded-2xl p-5">
                    <h3 className="text-sm font-bold text-amber-400 mb-3 flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4" /> Catch Anomalies ({analysis.anomaly_rule})
                    </h3>
                    <ul className="space-y-1.5">
                      {analysis.anomalies.map((a, i) => (
                        <li key={i} className="flex justify-between text-xs text-slate-300 bg-slate-800/50 rounded-lg px-3 py-2">
                          <span>Year {a.Year}</span>
                          <span className="font-mono">{a.catch.toFixed(1)} t (z={a.catch_z.toFixed(2)})</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}

            {/* Comparison view */}
            {comparison && compareMode && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[comparison.region_a, comparison.region_b].map((r: any, idx: number) => (
                  <div key={idx} className="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4">
                    <h2 className="text-slate-100 font-bold text-base flex items-center gap-2">
                      <span className={`w-2.5 h-2.5 rounded-full ${idx === 0 ? 'bg-emerald-500' : 'bg-cyan-500'}`}></span>
                      {r.state}
                    </h2>
                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div className="bg-slate-800/50 rounded-lg p-2.5">
                        <p className="text-[10px] text-slate-500">Mean Catch</p>
                        <p className="text-sm font-bold text-slate-100 mt-0.5">{r.mean_catch.toFixed(0)} t</p>
                      </div>
                      <div className="bg-slate-800/50 rounded-lg p-2.5">
                        <p className="text-[10px] text-slate-500">Mean SST</p>
                        <p className="text-sm font-bold text-slate-100 mt-0.5">{r.mean_sst.toFixed(1)}°C</p>
                      </div>
                      <div className="bg-slate-800/50 rounded-lg p-2.5">
                        <p className="text-[10px] text-slate-500">Mean Chl.</p>
                        <p className="text-sm font-bold text-slate-100 mt-0.5">{r.mean_chlorophyll.toFixed(2)}</p>
                      </div>
                    </div>
                    <CorrelationBadge label="Catch vs. SST" value={r.correlation.catch_vs_sst} icon={<Thermometer className="w-5 h-5" />} />
                    <CorrelationBadge label="Catch vs. Chlorophyll" value={r.correlation.catch_vs_chlorophyll} icon={<Droplets className="w-5 h-5" />} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
