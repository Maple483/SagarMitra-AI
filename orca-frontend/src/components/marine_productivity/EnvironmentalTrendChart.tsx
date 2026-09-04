import React, { useState } from 'react';
import { TimeseriesData, EnvironmentalVariable } from './types';
import { Info, Clock, Sparkles } from 'lucide-react';

interface EnvironmentalTrendChartProps {
  timeseries: TimeseriesData;
  variable: EnvironmentalVariable;
  species: string;
  lagYears?: number;
}

export const EnvironmentalTrendChart: React.FC<EnvironmentalTrendChartProps> = ({
  timeseries,
  variable,
  species,
  lagYears = 1,
}) => {
  const [showLagShifted, setShowLagShifted] = useState<boolean>(false);
  const [hoveredPoint, setHoveredPoint] = useState<{
    year: number;
    origEnvYear?: number;
    valCatch?: number;
    valEnv?: number;
    type: 'OBSERVED' | 'SCENARIO';
    x: number;
    isShifted?: boolean;
  } | null>(null);

  const years = [
    ...timeseries.observed_years,
    ...timeseries.scenario_years,
  ].sort((a, b) => a - b);

  const width = 800;
  const heightCatch = 140;
  const heightEnv = 140;
  const padLeft = 60;
  const padRight = 40;
  const padTop = 20;
  const padBottom = 25;
  const chartW = width - padLeft - padRight;

  const minYear = years[0];
  const maxYear = years[years.length - 1];
  const getX = (yr: number) => padLeft + ((yr - minYear) / (maxYear - minYear)) * chartW;

  const catchVals = Object.values(timeseries.landings) as number[];
  const minCatch = Math.min(...catchVals, 0);
  const maxCatch = Math.max(...catchVals, 1000) * 1.08;
  const getYCatch = (val: number) =>
    padTop + heightCatch - ((val - minCatch) / (maxCatch - minCatch || 1)) * heightCatch;

  const envVals = Object.values(timeseries.environmental) as number[];
  const minEnv = Math.min(...envVals) * 0.96;
  const maxEnv = Math.max(...envVals) * 1.04;
  const getYEnv = (val: number) =>
    padTop + heightEnv - ((val - minEnv) / (maxEnv - minEnv || 1)) * heightEnv;

  const obsCatchPoints = timeseries.observed_years
    .filter((y) => timeseries.landings[y] !== undefined)
    .map((y) => ({ x: getX(y), y: getYCatch(timeseries.landings[y]), year: y, val: timeseries.landings[y] }));

  const scenCatchPoints = timeseries.scenario_years
    .filter((y) => timeseries.landings[y] !== undefined)
    .map((y) => ({ x: getX(y), y: getYCatch(timeseries.landings[y]), year: y, val: timeseries.landings[y] }));

  const fullScenCatchPoints = [
    obsCatchPoints[obsCatchPoints.length - 1],
    ...scenCatchPoints,
  ].filter(Boolean);

  const makePath = (pts: { x: number; y: number }[]) =>
    pts.reduce((acc, p, i) => `${acc} ${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`, '');

  const obsEnvPoints = timeseries.observed_years
    .filter((y) => timeseries.environmental[y] !== undefined)
    .map((y) => ({ x: getX(y), y: getYEnv(timeseries.environmental[y]), year: y, val: timeseries.environmental[y] }));

  const scenEnvPoints = timeseries.scenario_years
    .filter((y) => timeseries.environmental[y] !== undefined)
    .map((y) => ({ x: getX(y), y: getYEnv(timeseries.environmental[y]), year: y, val: timeseries.environmental[y] }));

  const shiftedObsEnvPoints = timeseries.observed_years
    .filter((y) => timeseries.environmental[y] !== undefined && y + 1 <= maxYear)
    .map((y) => ({
      x: getX(y + 1),
      y: getYEnv(timeseries.environmental[y]),
      origYear: y,
      targetYear: y + 1,
      val: timeseries.environmental[y],
    }));

  const fullScenEnvPoints = [
    obsEnvPoints[obsEnvPoints.length - 1],
    ...scenEnvPoints,
  ].filter(Boolean);

  const dividerX = getX(2012.5);
  const varLabel = variable === 'sst' ? 'Sea Surface Temperature' : 'Chlorophyll-a';
  const varUnit = variable === 'sst' ? '°C' : 'mg/m³';
  const envColor = variable === 'sst' ? '#f59e0b' : '#10b981';

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 shadow-xl">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-2 border-b border-slate-800/80 pb-3">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
            Decoupled Time Series: Observed Baseline (2007–2012) vs Scenario Horizon (2013–2026)
          </h3>
          <p className="text-[11px] text-slate-400">
            Hover over any marker to inspect data point provenance and exact metric values
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* Optional Lag-Shifted Curve Toggle */}
          <button
            type="button"
            onClick={() => setShowLagShifted((v) => !v)}
            className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[10px] font-bold border transition cursor-pointer ${
              showLagShifted
                ? 'border-purple-500/60 bg-purple-500/20 text-purple-300 shadow-sm ring-1 ring-purple-500/30'
                : 'border-slate-700 bg-slate-950/70 text-slate-400 hover:text-slate-200 hover:border-slate-600'
            }`}
            title="Visually offsets the environmental curve 1 year forward (+1 yr) to inspect how spawning ocean conditions align directly with subsequent catch"
          >
            <Clock className="h-3 w-3 text-purple-400" />
            <span>{showLagShifted ? 'Hide Lag-Shifted Curve' : 'Show Lag-Shifted Curve (+1 yr)'}</span>
          </button>

          <div className="flex flex-wrap items-center gap-3 text-[10px] text-slate-300 pl-2 border-l border-slate-800">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-5 bg-emerald-400 rounded-sm"></span>
              Observed Landings (Solid)
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-5 border border-dashed border-cyan-400 rounded-sm"></span>
              Scenario Continuation (Dashed)
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 bg-amber-400 rotate-45"></span>
              Historical Env
            </span>
            {showLagShifted && (
              <span className="flex items-center gap-1 text-purple-300 font-semibold">
                <span className="inline-block h-1 w-4 border-t-2 border-dashed border-purple-400"></span>
                +1-Yr Lagged Env (t→t+1)
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Visual Alignment Explainer Banner */}
      {showLagShifted && (
        <div className="mb-3 flex items-center justify-between rounded-lg border border-purple-500/30 bg-purple-950/30 px-3 py-2 text-xs text-purple-200">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-purple-400 shrink-0" />
            <span>
              <strong>Visual Lag Alignment Enabled:</strong> The environmental curve (purple dashed line) is shifted +1 calendar year forward. Ocean conditions of year <em>t</em> (e.g. 2007) now line up in the exact same vertical column as year <em>t+1</em> catch (e.g. 2008) so you can directly compare recruitment alignment.
            </span>
          </div>
          <span className="rounded bg-purple-900/60 px-2 py-0.5 text-[10px] font-bold text-purple-300 shrink-0 ml-2 font-mono">
            +1 yr offset
          </span>
        </div>
      )}

      <div className="relative overflow-x-auto">
        {/* TOP: Landings Chart */}
        <div className="mb-3">
          <div className="flex justify-between items-center text-[11px] font-semibold text-slate-300 px-1 mb-1">
            <span>Reported Landings — {species} (Metric Tonnes)</span>
            <span className="text-[10px] text-slate-500">Source: CMFRI NMFDC</span>
          </div>
          <svg
            viewBox={`0 0 ${width} ${heightCatch + padTop + padBottom}`}
            className="w-full h-36 select-none overflow-visible"
          >
            <line x1={padLeft} y1={padTop} x2={padLeft} y2={padTop + heightCatch} stroke="#334155" strokeWidth="1" />
            <line x1={padLeft} y1={padTop + heightCatch} x2={width - padRight} y2={padTop + heightCatch} stroke="#334155" strokeWidth="1" />

            <rect x={padLeft} y={padTop} width={dividerX - padLeft} height={heightCatch} fill="rgba(16, 185, 129, 0.04)" />
            <rect x={dividerX} y={padTop} width={width - padRight - dividerX} height={heightCatch} fill="rgba(6, 182, 212, 0.03)" />

            <line x1={dividerX} y1={padTop} x2={dividerX} y2={padTop + heightCatch} stroke="#06b6d4" strokeWidth="1.5" strokeDasharray="4 4" />
            <text x={dividerX} y={padTop - 4} textAnchor="middle" fill="#38bdf8" fontSize="9" fontWeight="bold">
              2012 | 2013 PROJECTION BOUNDARY
            </text>

            <path d={makePath(obsCatchPoints)} fill="none" stroke="#10b981" strokeWidth="2.5" />
            <path d={makePath(fullScenCatchPoints)} fill="none" stroke="#64748b" strokeWidth="1.8" strokeDasharray="5 4" />

            {obsCatchPoints.map((p) => (
              <circle
                key={p.year}
                cx={p.x}
                cy={p.y}
                r="4.5"
                fill="#10b981"
                stroke="#0f172a"
                strokeWidth="1.5"
                className="cursor-pointer transition-all"
                onMouseEnter={() => setHoveredPoint({ year: p.year, valCatch: p.val, type: 'OBSERVED', x: p.x })}
                onMouseLeave={() => setHoveredPoint(null)}
              />
            ))}

            {scenCatchPoints.map((p) => (
              <rect
                key={p.year}
                x={p.x - 3.5}
                y={p.y - 3.5}
                width="7"
                height="7"
                fill="#0f172a"
                stroke="#94a3b8"
                strokeWidth="1.5"
                className="cursor-pointer transition-all"
                onMouseEnter={() => setHoveredPoint({ year: p.year, valCatch: p.val, type: 'SCENARIO', x: p.x })}
                onMouseLeave={() => setHoveredPoint(null)}
              />
            ))}

            <text x={padLeft - 8} y={padTop + 10} textAnchor="end" fill="#64748b" fontSize="9">
              {(maxCatch / 1000).toFixed(0)}k t
            </text>
            <text x={padLeft - 8} y={padTop + heightCatch} textAnchor="end" fill="#64748b" fontSize="9">
              0 t
            </text>
          </svg>
        </div>

        {/* BOTTOM: Environmental Variable Chart */}
        <div>
          <div className="flex justify-between items-center text-[11px] font-semibold text-slate-300 px-1 mb-1">
            <span>
              {varLabel} ({varUnit}) — 50-km Seaward Coastal Exposure Zone
            </span>
            <span className="text-[10px] text-slate-500">
              {variable === 'sst' ? 'NOAA OISST v2.1' : 'ESA OC-CCI v6.0'}
            </span>
          </div>
          <svg
            viewBox={`0 0 ${width} ${heightEnv + padTop + padBottom}`}
            className="w-full h-36 select-none overflow-visible"
          >
            <line x1={padLeft} y1={padTop} x2={padLeft} y2={padTop + heightEnv} stroke="#334155" strokeWidth="1" />
            <line x1={padLeft} y1={padTop + heightEnv} x2={width - padRight} y2={padTop + heightEnv} stroke="#334155" strokeWidth="1" />

            <rect x={padLeft} y={padTop} width={dividerX - padLeft} height={heightEnv} fill="rgba(245, 158, 11, 0.03)" />
            <rect x={dividerX} y={padTop} width={width - padRight - dividerX} height={heightEnv} fill="rgba(6, 182, 212, 0.03)" />

            <line x1={dividerX} y1={padTop} x2={dividerX} y2={padTop + heightEnv} stroke="#06b6d4" strokeWidth="1.5" strokeDasharray="4 4" />

            <path d={makePath(obsEnvPoints)} fill="none" stroke={envColor} strokeWidth="2.5" />
            <path d={makePath(fullScenEnvPoints)} fill="none" stroke="#06b6d4" strokeWidth="1.8" strokeDasharray="5 4" />

            {/* Optional Lag-Shifted Curve (+1 yr offset) */}
            {showLagShifted && (
              <>
                <path
                  d={makePath(shiftedObsEnvPoints)}
                  fill="none"
                  stroke="#c084fc"
                  strokeWidth="2.2"
                  strokeDasharray="4 3"
                />
                {shiftedObsEnvPoints.map((p) => (
                  <circle
                    key={`shifted-${p.origYear}`}
                    cx={p.x}
                    cy={p.y}
                    r="4.5"
                    fill="#7e22ce"
                    stroke="#e9d5ff"
                    strokeWidth="1.5"
                    className="cursor-pointer transition-all hover:scale-125"
                    onMouseEnter={() =>
                      setHoveredPoint({
                        year: p.targetYear,
                        origEnvYear: p.origYear,
                        valEnv: p.val,
                        type: 'OBSERVED',
                        x: p.x,
                        isShifted: true,
                      })
                    }
                    onMouseLeave={() => setHoveredPoint(null)}
                  />
                ))}
              </>
            )}

            {obsEnvPoints.map((p) => (
              <polygon
                key={p.year}
                points={`${p.x},${p.y - 4.5} ${p.x + 4.5},${p.y} ${p.x},${p.y + 4.5} ${p.x - 4.5},${p.y}`}
                fill={envColor}
                stroke="#0f172a"
                strokeWidth="1.5"
                className="cursor-pointer transition-all"
                onMouseEnter={() => setHoveredPoint({ year: p.year, valEnv: p.val, type: 'OBSERVED', x: p.x })}
                onMouseLeave={() => setHoveredPoint(null)}
              />
            ))}

            {scenEnvPoints.map((p) => (
              <rect
                key={p.year}
                x={p.x - 3.5}
                y={p.y - 3.5}
                width="7"
                height="7"
                fill="#0f172a"
                stroke="#06b6d4"
                strokeWidth="1.5"
                className="cursor-pointer transition-all"
                onMouseEnter={() => setHoveredPoint({ year: p.year, valEnv: p.val, type: 'SCENARIO', x: p.x })}
                onMouseLeave={() => setHoveredPoint(null)}
              />
            ))}

            {years.filter((_, idx) => idx % 2 === 0 || idx === years.length - 1).map((yr) => (
              <text
                key={yr}
                x={getX(yr)}
                y={padTop + heightEnv + 16}
                textAnchor="middle"
                fill={yr <= 2012 ? '#10b981' : '#64748b'}
                fontSize="9"
                fontWeight={yr === 2012 || yr === 2026 ? 'bold' : 'normal'}
              >
                {yr}
              </text>
            ))}

            <text x={padLeft - 8} y={padTop + 10} textAnchor="end" fill="#64748b" fontSize="9">
              {maxEnv.toFixed(1)} {varUnit}
            </text>
            <text x={padLeft - 8} y={padTop + heightEnv} textAnchor="end" fill="#64748b" fontSize="9">
              {minEnv.toFixed(1)} {varUnit}
            </text>
          </svg>
        </div>

        {hoveredPoint && (
          <div
            className="pointer-events-none absolute top-4 z-20 -translate-x-1/2 rounded-lg border border-slate-700 bg-slate-950/95 px-3 py-2 text-xs shadow-2xl backdrop-blur-md"
            style={{ left: `${hoveredPoint.x}px` }}
          >
            <div className="flex items-center gap-2 font-bold text-slate-200 border-b border-slate-800 pb-1 mb-1">
              <span>Year {hoveredPoint.year}</span>
              <span
                className={`rounded px-1.5 py-0.5 text-[9px] font-semibold ${
                  hoveredPoint.isShifted
                    ? 'bg-purple-500/20 text-purple-300'
                    : hoveredPoint.type === 'OBSERVED'
                    ? 'bg-emerald-500/20 text-emerald-300'
                    : 'bg-cyan-500/20 text-cyan-300'
                }`}
              >
                {hoveredPoint.isShifted
                  ? 'LAG-SHIFTED ALIGNMENT'
                  : hoveredPoint.type === 'OBSERVED'
                  ? 'OBSERVED RECORD'
                  : 'SCENARIO PROJECTION'}
              </span>
            </div>

            {hoveredPoint.isShifted ? (
              <div className="space-y-1 text-[11px] text-slate-300">
                <div>
                  Shifted {varLabel}:{' '}
                  <span className="font-bold text-purple-300">
                    {hoveredPoint.valEnv?.toFixed(2)} {varUnit}
                  </span>{' '}
                  <span className="text-[10px] text-purple-400 font-semibold">(from Year {hoveredPoint.origEnvYear})</span>
                </div>
                {timeseries.landings[hoveredPoint.year] !== undefined && (
                  <div>
                    Aligned Catch ({hoveredPoint.year}):{' '}
                    <span className="font-bold text-emerald-400">
                      {timeseries.landings[hoveredPoint.year].toLocaleString()} t
                    </span>
                  </div>
                )}
                <div className="text-[10px] text-slate-400 italic pt-1 border-t border-slate-800">
                  Tests spawning conditions in {hoveredPoint.origEnvYear} against harvest in {hoveredPoint.year}.
                </div>
              </div>
            ) : (
              <>
                {timeseries.landings[hoveredPoint.year] !== undefined && (
                  <div className="text-[11px] text-slate-300">
                    Landings: <span className="font-bold text-emerald-400">{timeseries.landings[hoveredPoint.year].toLocaleString()} t</span>
                  </div>
                )}
                {timeseries.environmental[hoveredPoint.year] !== undefined && (
                  <div className="text-[11px] text-slate-300">
                    {varLabel}: <span className="font-bold text-amber-400">{timeseries.environmental[hoveredPoint.year].toFixed(2)} {varUnit}</span>
                  </div>
                )}
                {hoveredPoint.year === 2026 && (
                  <div className="mt-1 text-[10px] font-bold text-cyan-400 border-t border-slate-800 pt-1">
                    ★ 2026 Synthetic Scenario Value
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      <div className="mt-3 flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2.5 text-[10px] text-slate-400">
        <Info className="h-4 w-4 shrink-0 text-cyan-400 mt-0.5" />
        <div>
          <span className="font-semibold text-slate-300">Data Non-Contamination Rule:</span> Empirical correlation and statistical significance are evaluated strictly on the 2007–2012 observed historical records (N ≤ 6). Trajectories for 2013–2026 are deterministic sensitivity scenarios that are never pooled with observations or used to corroborate empirical inferences.
        </div>
      </div>
    </div>
  );
};
