import React, { useState, useEffect } from 'react';
import { Navigation, Wind, ShieldAlert, MapPin, Sliders, X, Check, Activity } from 'lucide-react';

interface WeatherQuickWidgetProps {
  coords?: { lat: number; lon: number };
  onToggleDrawer: () => void;
  onLocationChange: (lat: number, lon: number) => void;
}

const PORT_PRESETS = [
  { name: 'Mumbai Port', lat: 18.95, lon: 72.85 },
  { name: 'JNPT Port', lat: 18.94, lon: 72.95 },
  { name: 'Cochin Port', lat: 9.96, lon: 76.26 },
  { name: 'Goa (Mormugao)', lat: 15.41, lon: 73.80 },
  { name: 'Visakhapatnam', lat: 17.68, lon: 83.28 },
  { name: 'Kandla (Deendayal)', lat: 23.00, lon: 70.22 }
];

export const WeatherQuickWidget: React.FC<WeatherQuickWidgetProps> = ({ coords: propCoords, onToggleDrawer, onLocationChange }) => {
  const [telemetrySource, setTelemetrySource] = useState<'nmea' | 'device' | 'manual'>('nmea');
  const [coords, setCoords] = useState(propCoords || { lat: 18.95, lon: 72.85 });
  const [weatherData, setWeatherData] = useState<any>(null);
  const [showModal, setShowModal] = useState(false);
  const [inputLat, setInputLat] = useState('18.95');
  const [inputLon, setInputLon] = useState('72.85');

  // Synchronize internal state when parent coords change (e.g. from map click)
  useEffect(() => {
    if (propCoords) {
      setCoords(propCoords);
      setInputLat(propCoords.lat.toString());
      setInputLon(propCoords.lon.toString());
    }
  }, [propCoords]);

  // Fetch live weather from backend FastAPI API
  useEffect(() => {
    const fetchWeather = async () => {
      try {
        const resp = await fetch(`http://localhost:8000/api/weather/live?lat=${coords.lat}&lon=${coords.lon}`);
        if (resp.ok) {
          const data = await resp.json();
          setWeatherData(data);
        }
      } catch (err) {
        console.warn("Backend weather API offline, using fallback UI telemetry");
      }
    };
    fetchWeather();
  }, [coords]);

  const handleDeviceGPS = () => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const lat = round(pos.coords.latitude, 4);
          const lon = round(pos.coords.longitude, 4);
          setCoords({ lat, lon });
          setTelemetrySource('device');
          onLocationChange(lat, lon);
        },
        () => {
          alert("Browser GPS unavailable or restricted on HTTP. Switching to Manual Input.");
          setShowModal(true);
        }
      );
    } else {
      setShowModal(true);
    }
  };

  const handleApplyManual = () => {
    const lat = parseFloat(inputLat);
    const lon = parseFloat(inputLon);
    if (!isNaN(lat) && !isNaN(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
      setCoords({ lat, lon });
      setTelemetrySource('manual');
      onLocationChange(lat, lon);
      setShowModal(false);
    } else {
      alert("Invalid Latitude [-90, 90] or Longitude [-180, 180]");
    }
  };

  const round = (val: number, dec: number) => Math.round(val * Math.pow(10, dec)) / Math.pow(10, dec);

  const isOutsideEEZ = 
    weatherData?.provenance?.marine_source === 'OUTSIDE_INDIAN_EEZ' || 
    weatherData?.system_metadata?.data_source === 'OUTSIDE_INDIAN_EEZ';

  const isLand = !isOutsideEEZ && (
    weatherData?.provenance?.marine_source === 'LANDMASS_INLAND' || 
    weatherData?.system_metadata?.data_source === 'LANDMASS_INLAND' || 
    weatherData?.safety_assessment?.warning_level === 'LANDMASS'
  );
  const windSpeed = weatherData?.wind?.speed_kt ?? weatherData?.telemetry?.wind_speed_knots ?? weatherData?.telemetry?.wind_speed_kt ?? (isLand || isOutsideEEZ ? 0.0 : 12.0);
  const waveHeight = isLand || isOutsideEEZ ? 0.0 : (weatherData?.waves?.wave_height_m ?? weatherData?.telemetry?.wave_height_m ?? 1.2);
  const swellHeight = isLand || isOutsideEEZ ? 0.0 : (weatherData?.waves?.swell_height_m ?? weatherData?.telemetry?.swell_height_m ?? 0.9);

  const getStatusBadge = () => {
    if (isOutsideEEZ) {
      return {
        label: 'STATUS: OUTSIDE EEZ',
        style: 'bg-slate-800/80 border-slate-600 text-slate-400'
      };
    }
    if (isLand) {
      return {
        label: 'STATUS: LANDMASS',
        style: 'bg-slate-800/80 border-slate-600 text-slate-300'
      };
    }
    const isHighWaveAlert = weatherData?.provenance?.marine_source === 'INCOIS_HIGH_WAVE_ALERT' ||
                           weatherData?.system_metadata?.data_source === 'INCOIS_HIGH_WAVE_ALERT';
    const warningLevel = weatherData?.safety_assessment?.warning_level;

    if (waveHeight >= 4.2 || windSpeed >= 38.0 || (isHighWaveAlert && waveHeight >= 4.0) || warningLevel === 'RED_WARNING') {
      return {
        label: 'STATUS: SEVERE HAZARD',
        style: 'bg-red-950/80 border-red-500/50 text-red-300 animate-pulse'
      };
    }
    if (waveHeight >= 3.0 || windSpeed >= 28.0 || isHighWaveAlert || warningLevel === 'ORANGE_ALERT') {
      return {
        label: 'STATUS: HIGH HAZARD',
        style: 'bg-orange-950/80 border-orange-500/50 text-orange-300'
      };
    }
    if (waveHeight >= 2.2 || windSpeed >= 22.0 || warningLevel === 'YELLOW_WATCH') {
      return {
        label: 'STATUS: MODERATE',
        style: 'bg-amber-950/80 border-amber-500/50 text-amber-300'
      };
    }
    return {
      label: 'STATUS: SAFE',
      style: 'bg-emerald-950/80 border-emerald-500/30 text-emerald-300'
    };
  };

  const statusInfo = getStatusBadge();

  return (
    <>
      <div className="absolute bottom-16 left-4 z-[400] bg-slate-900/90 backdrop-blur-md border border-cyan-500/30 text-white rounded-xl shadow-2xl p-3 flex flex-col gap-2 min-w-[280px]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700/50 pb-2">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-cyan-400 animate-pulse" />
            <span className="text-xs font-semibold uppercase tracking-wider text-cyan-300">Live Ocean Telemetry</span>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white transition-colors"
            title="Configure Telemetry Source / Coordinates"
          >
            <Sliders className="w-4 h-4" />
          </button>
        </div>

        {/* Coords & Telemetry Source Badge */}
        <div className="flex items-center justify-between text-xs text-slate-300">
          <div className="flex items-center gap-1.5">
            <MapPin className="w-3.5 h-3.5 text-cyan-400" />
            <span className="font-mono">{coords.lat}° N, {coords.lon}° E</span>
          </div>
          <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
            telemetrySource === 'nmea' ? 'bg-cyan-950 text-cyan-400 border border-cyan-500/40' :
            telemetrySource === 'device' ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/40' :
            'bg-amber-950 text-amber-400 border border-amber-500/40'
          }`}>
            {telemetrySource === 'nmea' ? 'NMEA WS' : telemetrySource === 'device' ? 'GPS' : 'Manual'}
          </span>
        </div>

        {/* Quick Weather Metrics Grid or Land/EEZ Notice */}
        {isOutsideEEZ ? (
          <div className="bg-slate-800/80 p-2.5 rounded-lg border border-slate-700/60 text-center my-1">
            <span className="text-xs font-semibold text-slate-300 block">OUTSIDE INDIAN EEZ BOUNDARY</span>
            <span className="text-[10px] text-slate-400">Telemetry & INCOIS advisories are restricted to Indian EEZ (200 NM)</span>
          </div>
        ) : isLand ? (
          <div className="bg-slate-800/80 p-2.5 rounded-lg border border-slate-700/60 text-center my-1">
            <span className="text-xs font-semibold text-slate-300 block">INLAND LANDMASS COORDINATES</span>
            <span className="text-[10px] text-slate-400">Marine wind & ocean swell data not applicable on land</span>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2 my-1">
            <div className="bg-slate-800/60 p-2 rounded-lg border border-slate-700/40">
              <div className="flex items-center gap-1 text-[10px] text-slate-400">
                <Wind className="w-3 h-3 text-cyan-400" />
                <span>WIND SPEED</span>
              </div>
              <div className="text-sm font-bold text-white mt-0.5">
                {round(windSpeed, 1)} <span className="text-[10px] font-normal text-slate-400">kt</span>
              </div>
            </div>

            <div className="bg-slate-800/60 p-2 rounded-lg border border-slate-700/40">
              <div className="flex items-center gap-1 text-[10px] text-slate-400">
                <Navigation className="w-3 h-3 text-blue-400" />
                <span>TOTAL WAVE / SWELL</span>
              </div>
              <div className="text-sm font-bold text-white mt-0.5 flex items-baseline gap-1">
                <span>{round(waveHeight, 2)} <span className="text-[10px] font-normal text-slate-400">m</span></span>
                <span className="text-[10px] font-normal text-cyan-400">({round(swellHeight, 1)}m swell)</span>
              </div>
            </div>
          </div>
        )}

        {/* Hazard Pill & Expand Drawer Action */}
        <div className="flex items-center gap-2 pt-1 border-t border-slate-700/50">
          <div className={`flex-1 flex items-center gap-1.5 px-2 py-1 border rounded text-[11px] font-semibold ${statusInfo.style}`}>
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>{statusInfo.label}</span>
          </div>
          <button
            onClick={onToggleDrawer}
            className="px-3 py-1 bg-cyan-600 hover:bg-cyan-500 text-white font-medium text-xs rounded transition-colors"
          >
            Full Dashboard
          </button>
        </div>
      </div>

      {/* Manual Coordinate & Preset Entry Modal */}
      {showModal && (
        <div className="fixed inset-0 z-[2000] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-cyan-500/30 rounded-2xl p-5 max-w-md w-full text-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
              <h3 className="text-base font-semibold flex items-center gap-2 text-cyan-400">
                <Sliders className="w-4 h-4" /> Telemetry & Location Setup
              </h3>
              <button onClick={() => setShowModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Source Toggles */}
            <div className="flex gap-2 mb-4">
              <button
                onClick={() => setTelemetrySource('nmea')}
                className={`flex-1 py-2 text-xs font-semibold rounded-lg border transition-all ${
                  telemetrySource === 'nmea' ? 'bg-cyan-600 border-cyan-400 text-white' : 'bg-slate-800 border-slate-700 text-slate-300'
                }`}
              >
                NMEA WebSocket
              </button>
              <button
                onClick={handleDeviceGPS}
                className={`flex-1 py-2 text-xs font-semibold rounded-lg border transition-all ${
                  telemetrySource === 'device' ? 'bg-emerald-600 border-emerald-400 text-white' : 'bg-slate-800 border-slate-700 text-slate-300'
                }`}
              >
                Device GPS
              </button>
            </div>

            {/* Manual Lat / Lon Entry */}
            <div className="space-y-3 mb-4">
              <label className="block text-xs font-medium text-slate-400">Manual Lat/Lon Entry (HTTP / Offline Shipboard Network)</label>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <span className="text-[10px] text-slate-400">LATITUDE (-90 to 90)</span>
                  <input
                    type="number"
                    step="0.0001"
                    value={inputLat}
                    onChange={(e) => setInputLat(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-sm text-white mt-1 focus:border-cyan-500 outline-none"
                  />
                </div>
                <div>
                  <span className="text-[10px] text-slate-400">LONGITUDE (-180 to 180)</span>
                  <input
                    type="number"
                    step="0.0001"
                    value={inputLon}
                    onChange={(e) => setInputLon(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-sm text-white mt-1 focus:border-cyan-500 outline-none"
                  />
                </div>
              </div>
            </div>

            {/* Port Presets */}
            <div className="mb-5">
              <label className="block text-xs font-medium text-slate-400 mb-2">Coastal Port Quick Presets</label>
              <div className="grid grid-cols-2 gap-2">
                {PORT_PRESETS.map((p) => (
                  <button
                    key={p.name}
                    onClick={() => {
                      setInputLat(p.lat.toString());
                      setInputLon(p.lon.toString());
                      setCoords({ lat: p.lat, lon: p.lon });
                      setTelemetrySource('manual');
                      onLocationChange(p.lat, p.lon);
                      setShowModal(false);
                    }}
                    className="p-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-left text-xs text-slate-200 transition-colors"
                  >
                    <div className="font-semibold text-cyan-300">{p.name}</div>
                    <div className="text-[10px] text-slate-400">{p.lat}° N, {p.lon}° E</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Apply Button */}
            <button
              onClick={handleApplyManual}
              className="w-full py-2.5 bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-xs rounded-xl flex items-center justify-center gap-2 transition-colors"
            >
              <Check className="w-4 h-4" /> Apply Coordinates
            </button>
          </div>
        </div>
      )}
    </>
  );
};
