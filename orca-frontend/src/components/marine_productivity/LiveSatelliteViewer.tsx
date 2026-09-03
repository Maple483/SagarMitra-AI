import React, { useEffect, useRef, useState } from 'react';
import { Globe, Maximize2, Minimize2, Info, CloudSun, Calendar } from 'lucide-react';
import { EnvironmentalVariable } from './types';

declare global {
  interface Window {
    L: any;
  }
}

interface LiveSatelliteViewerProps {
  initialVariable?: EnvironmentalVariable;
}

const WMS_URL = 'https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi';
const INDIA_BOUNDS: [[number, number], [number, number]] = [[2.0, 64.0], [26.0, 96.0]];
const INDIA_CENTER: [number, number] = [15.5, 77.5];

export const LiveSatelliteViewer: React.FC<LiveSatelliteViewerProps> = ({
  initialVariable = 'sst',
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const wmsLayerRef = useRef<any>(null);

  const [activeLayer, setActiveLayer] = useState<'sst' | 'chl'>(
    initialVariable === 'sst' ? 'sst' : 'chl'
  );
  const [chlMode, setChlMode] = useState<'clear' | 'latest'>('clear');
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Clear-sky post-monsoon date with full, rich chlorophyll coverage across Arabian Sea & Bay of Bengal
  const CLEAR_SKY_DATE = '2026-01-15';

  const layerConfigs = {
    sst: {
      id: 'GHRSST_L4_MUR_Sea_Surface_Temperature',
      title: 'Sea Surface Temperature (MUR L4)',
      range: '0°C to 32°C',
      source: 'NASA EOSDIS GIBS · GHRSST L4 Gap-Free Blended Analysis',
    },
    chl: {
      id: 'VIIRS_NOAA20_Chlorophyll_a',
      title: chlMode === 'clear' 
        ? 'Chlorophyll-a (VIIRS · Clear-Sky Observation)'
        : 'Chlorophyll-a (VIIRS · Real-Time Swath)',
      range: '0.01 to 20 mg/m³',
      source: 'NASA EOSDIS GIBS · NOAA-20 / VIIRS Global Ocean Color',
    },
  };

  const createWmsLayer = (layerKey: 'sst' | 'chl', currentChlMode: 'clear' | 'latest') => {
    const config = layerConfigs[layerKey];
    const wmsParams: any = {
      layers: config.id,
      format: 'image/png',
      transparent: true,
      version: '1.3.0',
      opacity: 0.85,
      attribution: 'NASA EOSDIS GIBS',
    };

    // For Chlorophyll in clear mode, pass 2026-01-15 for vibrant, gap-free ocean blooms
    // For SST, omit TIME so GIBS automatically uses its verified latest daily analysis (avoids 404/blank tiles)
    if (layerKey === 'chl' && currentChlMode === 'clear') {
      wmsParams.time = CLEAR_SKY_DATE;
    }

    return window.L.tileLayer.wms(WMS_URL, wmsParams);
  };

  useEffect(() => {
    if (!mapContainerRef.current || !window.L) return;

    // Clean up any stale leaflet id on container to prevent 'Map container is already initialized' error
    if ((mapContainerRef.current as any)._leaflet_id) {
      (mapContainerRef.current as any)._leaflet_id = null;
    }

    try {
      if (!mapInstanceRef.current) {
        const map = window.L.map(mapContainerRef.current, {
          zoomControl: true,
          scrollWheelZoom: true,
          minZoom: 4,
          maxZoom: 9,
          maxBounds: INDIA_BOUNDS,
          maxBoundsViscosity: 1.0,
        }).setView(INDIA_CENTER, 5);

        // Free dark ocean basemap from Esri (NO API KEY REQUIRED, zero watermarks)
        window.L.tileLayer(
          'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
          {
            attribution: '&copy; Esri, NOAA, USGS',
            maxZoom: 16,
          }
        ).addTo(map);

        // Subtle boundary / label reference overlay
        window.L.tileLayer(
          'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}',
          {
            attribution: '',
            maxZoom: 16,
            opacity: 0.45,
          }
        ).addTo(map);

        // Add initial NASA GIBS WMS layer
        const wms = createWmsLayer(activeLayer, chlMode).addTo(map);
        wmsLayerRef.current = wms;
        mapInstanceRef.current = map;
      }
    } catch (err) {
      console.warn('Leaflet satellite map initialization error:', err);
    }

    const timer = setTimeout(() => {
      try {
        mapInstanceRef.current?.invalidateSize();
      } catch (_) {}
    }, 200);

    return () => {
      clearTimeout(timer);
      if (mapInstanceRef.current) {
        try {
          mapInstanceRef.current.remove();
        } catch (_) {}
        mapInstanceRef.current = null;
      }
    };
  }, []);

  // Update layer when activeLayer or chlMode changes
  useEffect(() => {
    if (!mapInstanceRef.current || !window.L) return;

    try {
      if (wmsLayerRef.current) {
        mapInstanceRef.current.removeLayer(wmsLayerRef.current);
      }
      const newWms = createWmsLayer(activeLayer, chlMode).addTo(mapInstanceRef.current);
      wmsLayerRef.current = newWms;
    } catch (err) {
      console.warn('Leaflet layer switch error:', err);
    }
  }, [activeLayer, chlMode]);

  const toggleFullscreen = () => {
    setIsFullscreen((prev) => !prev);
    setTimeout(() => {
      mapInstanceRef.current?.invalidateSize();
    }, 250);
  };

  return (
    <div
      className={`rounded-xl border border-slate-800 bg-slate-900/70 shadow-xl transition-all duration-300 ${
        isFullscreen
          ? 'fixed inset-4 z-[9999] flex flex-col bg-slate-950 p-6'
          : 'relative p-4'
      }`}
    >
      {/* Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3 border-b border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          <Globe className="h-4 w-4 text-cyan-400" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
            NASA GIBS Satellite Oceanography (Indian Maritime Waters)
          </h3>
          <span className="flex items-center gap-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 px-2 py-0.5 text-[9px] font-bold text-emerald-400">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            NASA GIBS FEED
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Chlorophyll View Mode Toggle (Only visible when Chlorophyll is selected) */}
          {activeLayer === 'chl' && (
            <div className="flex rounded-lg border border-slate-700 bg-slate-950 p-0.5 text-xs font-medium">
              <button
                type="button"
                onClick={() => setChlMode('clear')}
                title="Clear-Sky Observation: Complete, uninterrupted chlorophyll coverage across Indian coastal waters"
                className={`flex items-center gap-1 rounded px-2.5 py-1 text-[11px] transition ${
                  chlMode === 'clear'
                    ? 'bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/40 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <CloudSun className="h-3 w-3" />
                <span>Clear-Sky Pass</span>
              </button>
              <button
                type="button"
                onClick={() => setChlMode('latest')}
                title="Real-Time Swath: Latest daily optical pass (cloud cover during monsoon is masked as dark nodata)"
                className={`flex items-center gap-1 rounded px-2.5 py-1 text-[11px] transition ${
                  chlMode === 'latest'
                    ? 'bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/40 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Calendar className="h-3 w-3" />
                <span>Today's Swath</span>
              </button>
            </div>
          )}

          {/* Layer Selector */}
          <div className="flex rounded-lg border border-slate-700 bg-slate-950 p-0.5 text-xs font-medium">
            <button
              type="button"
              onClick={() => setActiveLayer('sst')}
              className={`rounded px-2.5 py-1 transition ${
                activeLayer === 'sst'
                  ? 'bg-amber-500/20 text-amber-300 font-bold border border-amber-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              MUR SST
            </button>
            <button
              type="button"
              onClick={() => setActiveLayer('chl')}
              className={`rounded px-2.5 py-1 transition ${
                activeLayer === 'chl'
                  ? 'bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              VIIRS Chl-a
            </button>
          </div>

          <button
            type="button"
            onClick={toggleFullscreen}
            className="rounded-lg border border-slate-700 bg-slate-950 p-1.5 text-slate-400 hover:text-cyan-400 transition"
            title={isFullscreen ? 'Exit Fullscreen' : 'Open Fullscreen'}
          >
            {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {/* Map Container */}
      <div className="relative w-full flex-1 min-h-[340px] rounded-lg overflow-hidden border border-slate-800 shadow-inner">
        <div ref={mapContainerRef} className="w-full h-full min-h-[340px]" />

        {/* Legend Overlay */}
        <div className="absolute bottom-3 left-3 z-[1000] rounded-lg border border-slate-700/80 bg-slate-950/90 p-2.5 text-[10px] backdrop-blur-md shadow-xl max-w-xs">
          <div className="font-bold text-slate-200 mb-1 flex items-center justify-between">
            <span>{layerConfigs[activeLayer].title}</span>
          </div>
          {/* Gradient Bar */}
          <div
            className="h-2.5 w-48 rounded-full border border-slate-600 mb-1"
            style={{
              background:
                activeLayer === 'sst'
                  ? 'linear-gradient(to right, #000080, #00ffff, #ffff00, #ff0000)'
                  : 'linear-gradient(to right, #0a1f33, #005f73, #0a9396, #94d2bd, #ee9b00, #ae2012)',
            }}
          />
          <div className="flex justify-between text-[9px] text-slate-400 font-mono">
            {activeLayer === 'sst' ? (
              <>
                <span>&lt; 0°C</span>
                <span>12°C</span>
                <span>24°C</span>
                <span>≥ 32°C</span>
              </>
            ) : (
              <>
                <span>&lt; 0.01</span>
                <span>0.1</span>
                <span>1.0</span>
                <span>≥ 20 mg/m³</span>
              </>
            )}
          </div>
          {activeLayer === 'chl' && chlMode === 'latest' && (
            <div className="mt-1 text-[9px] text-amber-400/90 font-medium">
              ℹ️ Dark areas = Monsoon cloud cover & orbital gaps (100% loaded)
            </div>
          )}
          <div className="mt-1.5 text-[8px] text-slate-500">
            Source: {layerConfigs[activeLayer].source}
          </div>
        </div>

        {/* Attribution Badge */}
        <div className="absolute top-2 right-2 z-[1000] rounded-md bg-slate-950/80 border border-slate-800 px-2 py-1 text-[9px] text-slate-400">
          Imagery: NASA EOSDIS GIBS · Basemap: Esri
        </div>
      </div>

      {/* Optical Sensor Cloud Cover Notice (for Chlorophyll) */}
      {activeLayer === 'chl' && (
        <div className="mt-2.5 flex items-start gap-2 rounded-lg border border-cyan-500/20 bg-cyan-950/20 p-2 text-[10px] text-cyan-300">
          <Info className="h-3.5 w-3.5 shrink-0 text-cyan-400 mt-0.5" />
          <div>
            <strong className="text-cyan-200">Why are parts of the Chlorophyll map dark?</strong> Optical ocean-color satellites (VIIRS) rely on visible sunlight and cannot see through monsoon clouds. Any cloudy or stormy pixel is automatically masked out as nodata. Use the <span className="font-semibold text-white">Clear-Sky Pass</span> button above to view full, unobstructed chlorophyll blooms across the entire Indian coastline.
          </div>
        </div>
      )}

      {/* General Decoupling Disclaimer */}
      {activeLayer === 'sst' && (
        <div className="mt-2.5 flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-950/50 p-2 text-[10px] text-slate-400">
          <Info className="h-3.5 w-3.5 shrink-0 text-cyan-400 mt-0.5" />
          <div>
            <strong className="text-slate-300">Gap-Free Microwave Analysis:</strong> MUR Sea Surface Temperature blends infrared, satellite microwave radiometers (which penetrate through clouds), and in-situ buoys to provide 100% continuous ocean coverage.
          </div>
        </div>
      )}
    </div>
  );
};
