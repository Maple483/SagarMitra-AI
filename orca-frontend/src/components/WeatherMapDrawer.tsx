import React, { useState, useEffect } from 'react';
import { X, Wind, Compass, ShieldAlert, Waves, Clock, Play, Pause, Navigation, AlertTriangle, MapPin, Check, Sliders, Target } from 'lucide-react';

interface WeatherMapDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  coords: { lat: number; lon: number };
  onUpdateCoords: (lat: number, lon: number) => void;
}

const PORT_PRESETS = [
  { name: 'Mumbai', lat: 18.95, lon: 72.85 },
  { name: 'JNPT', lat: 18.94, lon: 72.95 },
  { name: 'Cochin', lat: 9.96, lon: 76.26 },
  { name: 'Goa', lat: 15.41, lon: 73.80 },
  { name: 'Vizag', lat: 17.68, lon: 83.28 },
  { name: 'Kandla', lat: 23.00, lon: 70.22 }
];

const round = (val: number, dec: number) => Math.round(val * Math.pow(10, dec)) / Math.pow(10, dec);

export const WeatherMapDrawer: React.FC<WeatherMapDrawerProps> = ({ isOpen, onClose, coords, onUpdateCoords }) => {
  const [activeTab, setActiveTab] = useState<'overview' | 'forecast' | 'route' | 'imd'>('overview');
  const [forecastHour, setForecastHour] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [weather, setWeather] = useState<any>(null);

  // Editable Lat/Lon state inside drawer
  const [editLat, setEditLat] = useState(coords.lat.toString());
  const [editLon, setEditLon] = useState(coords.lon.toString());
  const [showEditInputs, setShowEditInputs] = useState(false);

  // Synchronize input fields when parent coords change (e.g. from map click)
  useEffect(() => {
    setEditLat(coords.lat.toString());
    setEditLon(coords.lon.toString());
  }, [coords]);

  const [forecastData, setForecastData] = useState<any>(null);

  // Fetch live weather telemetry for selected map coordinates
  useEffect(() => {
    const fetchLiveWeather = async () => {
      try {
        const resp = await fetch(`http://localhost:8000/api/weather/live?lat=${coords.lat}&lon=${coords.lon}`);
        if (resp.ok) {
          const data = await resp.json();
          setWeather(data);
        }
      } catch (err) {
        console.warn("Live weather API offline");
      }
    };
    if (isOpen) fetchLiveWeather();
  }, [isOpen, coords]);

  useEffect(() => {
    const fetchForecast = async () => {
      try {
        const resp = await fetch(`http://localhost:8000/api/weather/forecast?lat=${coords.lat}&lon=${coords.lon}&days=3`);
        if (resp.ok) {
          const data = await resp.json();
          setForecastData(data);
        }
      } catch (err) {
        console.warn("Forecast API offline");
      }
    };
    if (isOpen && activeTab === 'forecast') fetchForecast();
  }, [isOpen, activeTab, coords]);
  const [routeOrigin, setRouteOrigin] = useState("18.95, 72.85");
  const [routeDest, setRouteDest] = useState("15.45, 73.80");
  const [routeResult, setRouteResult] = useState<any>(null);
  const [evaluating, setEvaluating] = useState(false);

  useEffect(() => {
    let interval: any;
    if (isPlaying) {
      interval = setInterval(() => {
        setForecastHour((prev) => (prev >= 72 ? 0 : prev + 3));
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [isPlaying]);

  useEffect(() => {
    const fetchLive = async () => {
      try {
        const resp = await fetch(`http://localhost:8000/api/weather/live?lat=${coords.lat}&lon=${coords.lon}`);
        if (resp.ok) {
          const data = await resp.json();
          setWeather(data);
        }
      } catch (err) {
        console.warn("Backend API offline");
      }
    };
    if (isOpen) fetchLive();
  }, [isOpen, coords]);

  const handleApplyLocation = () => {
    const lat = parseFloat(editLat);
    const lon = parseFloat(editLon);
    if (!isNaN(lat) && !isNaN(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
      onUpdateCoords(lat, lon);
      setShowEditInputs(false);
    } else {
      alert("Invalid Coordinates: Lat [-90, 90], Lon [-180, 180]");
    }
  };

  const handleMyGPS = () => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const lat = Math.round(pos.coords.latitude * 10000) / 10000;
          const lon = Math.round(pos.coords.longitude * 10000) / 10000;
          onUpdateCoords(lat, lon);
        },
        () => alert("GPS unavailable on HTTP local network. Use port presets or manual inputs.")
      );
    }
  };

  const [routeError, setRouteError] = useState<string | null>(null);

  const handleEvaluateRoute = async () => {
    setEvaluating(true);
    setRouteError(null);
    try {
      const origParts = routeOrigin.split(',').map(s => parseFloat(s.trim()));
      const destParts = routeDest.split(',').map(s => parseFloat(s.trim()));

      if (origParts.length < 2 || destParts.length < 2 || origParts.some(isNaN) || destParts.some(isNaN)) {
        setRouteError("Please enter valid 'Lat, Lon' values for both Origin and Destination (e.g. 18.95, 72.85)");
        setEvaluating(false);
        return;
      }

      const [origLat, origLon] = origParts;
      const [destLat, destLon] = destParts;

      if (origLat < -90 || origLat > 90 || destLat < -90 || destLat > 90 || origLon < -180 || origLon > 180 || destLon < -180 || destLon > 180) {
        setRouteError("Coordinates out of bounds: Lat [-90, 90], Lon [-180, 180]");
        setEvaluating(false);
        return;
      }

      const resp = await fetch('http://localhost:8000/api/weather/route', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          waypoints: [
            { lat: origLat, lon: origLon },
            { lat: destLat, lon: destLon }
          ],
          vessel_profile: {
            vessel_id: "ORCA-VESSEL-1",
            vessel_type: "patrol",
            max_safe_wave_m: 3.0,
            max_safe_wind_kt: 30.0
          },
          speed_through_water_kt: 15.0
        })
      });

      if (resp.ok) {
        const data = await resp.json();
        setRouteResult(data);
      } else {
        const errData = await resp.json().catch(() => ({}));
        setRouteError(errData.detail || "Server rejected route evaluation request.");
      }
    } catch (err) {
      setRouteError("Could not connect to backend FastAPI server at http://localhost:8000.");
    } finally {
      setEvaluating(false);
    }
  };

  if (!isOpen) return null;

  return (
    /* Docks seamlessly next to left chat sidebar on desktop: md:left-[384px] lg:left-[400px] */
    <div className="fixed inset-y-0 left-0 md:left-[384px] lg:left-[400px] z-[1500] w-full md:w-[380px] lg:w-[420px] bg-slate-900/95 backdrop-blur-2xl border-r border-cyan-500/30 text-white shadow-2xl flex flex-col transition-all">
      {/* Drawer Header */}
      <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
        <div className="flex items-center gap-2">
          <Compass className="w-5 h-5 text-cyan-400" />
          <h2 className="text-sm font-bold text-cyan-300">INCOIS & IMD Weather Intelligence</h2>
        </div>
        <button onClick={onClose} className="p-1 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800">
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-slate-800 bg-slate-900/50">
        {[
          { id: 'overview', label: 'Telemetry' },
          { id: 'forecast', label: '72h Forecast' },
          { id: 'route', label: 'Space-Time Route' },
          { id: 'imd', label: 'IMD Alerts' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`flex-1 py-2.5 text-xs font-semibold border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-cyan-400 text-cyan-300 bg-cyan-950/30'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Drawer Content Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Tab 1: Telemetry Overview */}
        {activeTab === 'overview' && (
          <div className="space-y-4">
            {/* Target Location Card with Interactive Controls */}
            <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-3.5 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5 text-cyan-400" /> TARGET LOCATION
                </span>
                <button
                  onClick={() => setShowEditInputs(!showEditInputs)}
                  className="text-xs text-cyan-400 hover:underline flex items-center gap-1"
                >
                  <Sliders className="w-3 h-3" /> {showEditInputs ? "Hide Editor" : "Edit Coords"}
                </button>
              </div>

              {/* Display Coords */}
              {!showEditInputs ? (
                <div className="flex items-center justify-between">
                  <span className="text-base font-bold font-mono text-cyan-300">{coords.lat}° N, {coords.lon}° E</span>
                  <button
                    onClick={handleMyGPS}
                    className="px-2.5 py-1 bg-cyan-950 hover:bg-cyan-900 border border-cyan-500/40 text-cyan-400 rounded-md text-[11px] font-semibold flex items-center gap-1 transition-colors"
                  >
                    <Target className="w-3 h-3" /> My GPS
                  </button>
                </div>
              ) : (
                /* Editable Lat/Lon Inputs */
                <div className="space-y-2 pt-1">
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <span className="text-[10px] text-slate-400">LATITUDE</span>
                      <input
                        type="number"
                        step="0.0001"
                        value={editLat}
                        onChange={(e) => setEditLat(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-700 rounded p-1.5 text-xs text-white mt-0.5 focus:border-cyan-500 outline-none"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400">LONGITUDE</span>
                      <input
                        type="number"
                        step="0.0001"
                        value={editLon}
                        onChange={(e) => setEditLon(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-700 rounded p-1.5 text-xs text-white mt-0.5 focus:border-cyan-500 outline-none"
                      />
                    </div>
                  </div>
                  <button
                    onClick={handleApplyLocation}
                    className="w-full py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded text-xs font-semibold flex items-center justify-center gap-1 transition-colors"
                  >
                    <Check className="w-3.5 h-3.5" /> Update Location
                  </button>
                </div>
              )}

              {/* One-Touch Port Presets */}
              <div className="space-y-1.5 pt-1 border-t border-slate-700/50">
                <span className="text-[10px] text-slate-400 font-medium">Quick Port Presets:</span>
                <div className="flex flex-wrap gap-1.5">
                  {PORT_PRESETS.map((p) => (
                    <button
                      key={p.name}
                      onClick={() => {
                        onUpdateCoords(p.lat, p.lon);
                      }}
                      className={`px-2 py-0.5 rounded text-[11px] font-medium border transition-colors ${
                        coords.lat === p.lat && coords.lon === p.lon
                          ? 'bg-cyan-600 border-cyan-400 text-white font-bold'
                          : 'bg-slate-900/60 border-slate-700 text-slate-300 hover:border-cyan-500/50'
                      }`}
                    >
                      {p.name}
                    </button>
                  ))}
                </div>
              </div>

              {/* Map Click Hint */}
              <div className="p-2 bg-slate-900/80 rounded-lg border border-slate-800 text-[10px] text-slate-400 flex items-center gap-1.5">
                <Target className="w-3 h-3 text-cyan-400 flex-shrink-0" />
                <span>Tip: Click anywhere on the map to instantly inspect live weather.</span>
              </div>
            </div>

            {/* Data Provenance & Metrics */}
            {(() => {
              const isOutsideEEZ = 
                weather?.provenance?.marine_source === 'OUTSIDE_INDIAN_EEZ' || 
                weather?.system_metadata?.data_source === 'OUTSIDE_INDIAN_EEZ';

              const isLand = !isOutsideEEZ && (
                weather?.provenance?.marine_source === 'LANDMASS_INLAND' || 
                weather?.system_metadata?.data_source === 'LANDMASS_INLAND' || 
                weather?.safety_assessment?.warning_level === 'LANDMASS'
              );

              const windSpeed = weather?.wind?.speed_kt ?? weather?.telemetry?.wind_speed_knots ?? weather?.telemetry?.wind_speed_kt ?? (isLand || isOutsideEEZ ? 0.0 : 12.0);
              const windGust = weather?.wind?.gust_kt ?? (weather?.telemetry?.wind_gusts_kmh ? round(weather.telemetry.wind_gusts_kmh / 1.852, 1) : round(windSpeed * 1.3, 1));
              const windDir = weather?.wind?.direction_deg ?? weather?.telemetry?.wind_direction_deg ?? 240;

              const waveHeight = isLand || isOutsideEEZ ? 0.0 : (weather?.waves?.wave_height_m ?? weather?.telemetry?.wave_height_m ?? 1.2);
              const swellHeight = isLand || isOutsideEEZ ? 0.0 : (weather?.waves?.swell_height_m ?? weather?.telemetry?.swell_height_m ?? 0.9);
              const wavePeriod = isLand || isOutsideEEZ ? 0.0 : (weather?.waves?.wave_period_s ?? weather?.telemetry?.wave_period_seconds ?? 7.5);
              const source = weather?.provenance?.marine_source ?? weather?.system_metadata?.data_source ?? (isOutsideEEZ ? "OUTSIDE_INDIAN_EEZ" : isLand ? "LANDMASS_INLAND" : "INCOIS_OSF_GRID");

              return (
                <>
                  <div className="bg-slate-800/60 border border-slate-700/50 rounded-xl p-3 flex items-center justify-between text-xs">
                    <span className="text-slate-400">DATA PROVENANCE</span>
                    <span className="text-emerald-400 font-medium font-mono">
                      {source}
                    </span>
                  </div>

                  {isOutsideEEZ ? (
                    <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 text-center space-y-1">
                      <div className="flex items-center justify-center gap-2 text-slate-300 font-semibold text-xs uppercase tracking-wider">
                        <MapPin className="w-4 h-4 text-amber-400" />
                        <span>COORDINATES OUTSIDE INDIAN EEZ</span>
                      </div>
                      <p className="text-xs text-slate-400">
                        Live oceanography, high wave advisories, and space-time route calculations are restricted to coordinates within the Indian Exclusive Economic Zone (200 NM).
                      </p>
                    </div>
                  ) : isLand ? (
                    <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 text-center space-y-1">
                      <div className="flex items-center justify-center gap-2 text-slate-300 font-semibold text-xs uppercase tracking-wider">
                        <MapPin className="w-4 h-4 text-amber-400" />
                        <span>INLAND LANDMASS COORDINATES</span>
                      </div>
                      <p className="text-xs text-slate-400">
                        Marine surface wind and ocean swell telemetry are suppressed for landmass coordinates. Click on coastal or offshore ocean waters to inspect marine telemetry.
                      </p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 gap-3">
                      <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-3">
                        <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                          <Wind className="w-4 h-4 text-cyan-400" />
                          <span>WIND & GUST</span>
                        </div>
                        <div className="text-xl font-bold text-white">
                          {round(windSpeed, 1)} <span className="text-xs font-normal text-slate-400">kt</span>
                        </div>
                        <div className="text-[11px] text-slate-400 mt-1">
                          Gusts: {round(windGust, 1)} kt | Dir: {windDir}°
                        </div>
                      </div>

                      <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-3">
                        <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                          <Waves className="w-4 h-4 text-blue-400" />
                          <span>WAVE SWELL</span>
                        </div>
                        <div className="text-xl font-bold text-white">
                          {round(waveHeight, 2)} <span className="text-xs font-normal text-slate-400">m</span>
                        </div>
                        <div className="text-[11px] text-slate-400 mt-1">
                          Swell: {round(swellHeight, 1)}m | Period: {wavePeriod}s
                        </div>
                      </div>
                    </div>
                  )}
                </>
              );
            })()}

            {/* Bimodal Cross Sea Alert */}
            {weather?.is_cross_sea && (
              <div className="p-3 bg-amber-950/70 border border-amber-500/50 rounded-xl flex items-center gap-3 text-amber-300">
                <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0" />
                <div className="text-xs">
                  <span className="font-bold block">CROSS SEA HAZARD DETECTED</span>
                  <span>Wind waves and swells arriving at nearly orthogonal angles. High risk of vessel rolling.</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: 72-Hour Forecast Time Slider */}
        {activeTab === 'forecast' && (
          <div className="space-y-4">
            <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Clock className="w-4 h-4 text-cyan-400" />
                  <span className="text-xs font-semibold text-cyan-300">Forecast Time Slider</span>
                </div>
                <span className="text-sm font-bold text-white font-mono">+{forecastHour} Hours</span>
              </div>

              <input
                type="range"
                min="0"
                max="72"
                step="3"
                value={forecastHour}
                onChange={(e) => setForecastHour(parseInt(e.target.value))}
                className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-cyan-400"
              />

              <div className="flex items-center justify-between pt-2">
                <button
                  onClick={() => setIsPlaying(!isPlaying)}
                  className="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors"
                >
                  {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                  {isPlaying ? 'Pause' : 'Play Timeline'}
                </button>
                <span className="text-[11px] text-slate-400">Renders 1 frame at a time</span>
              </div>
            </div>

            {/* Live Forecast Metric Breakdown for Selected Frame */}
            {(() => {
              const selectedFrame = forecastData?.hourly_summary?.find((f: any) => f.hour_offset === forecastHour) || forecastData?.hourly_summary?.[0];
              const isLand = 
                weather?.provenance?.marine_source === 'LANDMASS_INLAND' || 
                weather?.system_metadata?.data_source === 'LANDMASS_INLAND' ||
                weather?.safety_assessment?.warning_level === 'LANDMASS' ||
                weather?.waves?.wave_height_m === 0 ||
                weather?.telemetry?.wave_height_m === 0;

              if (isLand) {
                return (
                  <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 text-center">
                    <span className="text-xs font-semibold text-slate-300 block">INLAND LANDMASS COORDINATES</span>
                    <span className="text-xs text-slate-400">Marine forecast stream suppressed for inland coordinates</span>
                  </div>
                );
              }

              return (
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-3">
                    <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                      <Wind className="w-4 h-4 text-cyan-400" />
                      <span>PREDICTED WIND</span>
                    </div>
                    <div className="text-xl font-bold text-white">
                      {selectedFrame ? selectedFrame.wind_speed_kt : round(weather?.wind?.speed_kt || 12.0, 1)} <span className="text-xs font-normal text-slate-400">kt</span>
                    </div>
                    <div className="text-[11px] text-slate-400 mt-1">
                      Frame: +{forecastHour}h | Direction: {weather?.wind?.direction_deg || 240}°
                    </div>
                  </div>

                  <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-3">
                    <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                      <Waves className="w-4 h-4 text-blue-400" />
                      <span>PREDICTED SWELL</span>
                    </div>
                    <div className="text-xl font-bold text-white">
                      {selectedFrame ? selectedFrame.wave_height_m : round(weather?.waves?.wave_height_m || 1.5, 2)} <span className="text-xs font-normal text-slate-400">m</span>
                    </div>
                    <div className="text-[11px] text-slate-400 mt-1">
                      Period: {selectedFrame?.wave_period_s || 7.5}s | Swell: {round((selectedFrame?.wave_height_m || 1.5) * 0.8, 1)}m
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* 3-Hourly Forecast Breakdown List */}
            <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-3 space-y-2">
              <span className="text-xs font-bold text-slate-300 uppercase tracking-wider block">72-Hour Prediction Stream</span>
              <div className="space-y-1.5 max-h-60 overflow-y-auto pr-1">
                {forecastData?.hourly_summary?.map((step: any, idx: number) => (
                  <div
                    key={idx}
                    onClick={() => setForecastHour(step.hour_offset)}
                    className={`p-2 rounded border flex items-center justify-between text-xs cursor-pointer transition-colors ${
                      forecastHour === step.hour_offset
                        ? 'bg-cyan-950/80 border-cyan-400 text-cyan-300'
                        : 'bg-slate-900/60 border-slate-800 text-slate-300 hover:bg-slate-800'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-cyan-400 font-bold">+{step.hour_offset}h</span>
                      <span className="text-[11px] text-slate-400">{step.timestamp_utc?.substring(11, 16)} UTC</span>
                    </div>
                    <div className="flex items-center gap-3 text-[11px]">
                      <span>Wind: <strong className="text-white">{step.wind_speed_kt} kt</strong></span>
                      <span>Swell: <strong className="text-white">{step.wave_height_m} m</strong></span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Space-Time Route Hazard Evaluator */}
        {activeTab === 'route' && (
          <div className="space-y-4">
            <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 space-y-3">
              <span className="text-xs font-bold text-cyan-300 uppercase tracking-wider block">Space-Time Trajectory Evaluator</span>

              <div className="space-y-2 text-xs">
                <div>
                  <span className="text-slate-400 block mb-1">ORIGIN (Lat, Lon)</span>
                  <input
                    type="text"
                    value={routeOrigin}
                    onChange={(e) => setRouteOrigin(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-white font-mono text-xs"
                  />
                </div>
                <div>
                  <span className="text-slate-400 block mb-1">DESTINATION (Lat, Lon)</span>
                  <input
                    type="text"
                    value={routeDest}
                    onChange={(e) => setRouteDest(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-white font-mono text-xs"
                  />
                </div>
              </div>

              <button
                onClick={handleEvaluateRoute}
                disabled={evaluating}
                className="w-full py-2.5 bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-xs rounded-xl flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
              >
                {evaluating ? "Executing Forward Integration..." : "Evaluate Route Safety"}
              </button>
            </div>

            {routeError && (
              <div className="p-3 bg-red-950/80 border border-red-500/50 rounded-xl flex items-center gap-2 text-red-300 text-xs">
                <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
                <span>{routeError}</span>
              </div>
            )}

            {routeResult && (
              <div className="bg-slate-800/90 border border-cyan-500/30 rounded-xl p-4 space-y-3 text-xs">
                <div className="flex items-center justify-between border-b border-slate-700 pb-2">
                  <span className="text-slate-300 font-semibold">ROUTE HAZARD:</span>
                  <span className={`px-2 py-0.5 rounded font-bold uppercase ${
                    routeResult.overall_hazard_level === 'LOW' ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/40' :
                    routeResult.overall_hazard_level === 'MODERATE' ? 'bg-yellow-950 text-yellow-400 border border-yellow-500/40' :
                    'bg-red-950 text-red-400 border border-red-500/40'
                  }`}>
                    {routeResult.overall_hazard_level}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-slate-300 text-[11px]">
                  <div>Max Wave: <span className="font-bold text-white">{routeResult.max_wave_m}m</span></div>
                  <div>Max Wind: <span className="font-bold text-white">{routeResult.max_wind_kt}kt</span></div>
                  <div>Exceeded Hours: <span className="font-bold text-amber-400">{routeResult.duration_wave_exceeded_hours}h</span></div>
                  <div>Cumulative Exposure: <span className="font-bold text-cyan-400">{routeResult.cumulative_exposure_index}</span></div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 4: Active IMD Alerts */}
        {activeTab === 'imd' && (
          <div className="space-y-3">
            <div className="p-3 bg-red-950/60 border border-red-500/40 rounded-xl space-y-1 text-xs">
              <div className="flex items-center justify-between text-red-300 font-bold">
                <span className="flex items-center gap-1.5">
                  <ShieldAlert className="w-4 h-4 text-red-400" />
                  IMD CYCLONE ASNA - SEVERE CYCLONIC STORM
                </span>
                <span className="text-[10px] bg-red-900 text-red-200 px-1.5 py-0.5 rounded">RED WARNING</span>
              </div>
              <p className="text-[11px] text-red-200/90 pt-1">
                Gale winds 75-90 km/h over Eastcentral Arabian Sea. Fishermen advised not to venture into open ocean.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
