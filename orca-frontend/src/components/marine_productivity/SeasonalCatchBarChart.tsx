import React from 'react';
import { Calendar, AlertCircle } from 'lucide-react';

interface SeasonalCatchBarChartProps {
  seasonalProfile: number[];
  species: string;
  referenceCatch?: number;
}

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTH_FULL = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

export const SeasonalCatchBarChart: React.FC<SeasonalCatchBarChartProps> = ({
  seasonalProfile,
  species,
  referenceCatch = 56000,
}) => {
  const maxPct = Math.max(...seasonalProfile, 0.20);
  const peakIdx = seasonalProfile.indexOf(Math.max(...seasonalProfile));

  const postMonsoonSum = ((seasonalProfile[9] || 0) + (seasonalProfile[10] || 0)) * 100;
  const postMonsoonTonnes = referenceCatch * (postMonsoonSum / 100);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 shadow-xl">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3 border-b border-slate-800/80 pb-2">
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-cyan-400" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
            Seasonal Landings Distribution — {species}
          </h3>
        </div>
        <div className="text-[11px] text-cyan-400 font-semibold">
          Post-Monsoon (Oct–Nov): {postMonsoonSum.toFixed(0)}% of catch (~{postMonsoonTonnes.toLocaleString('en-US', { maximumFractionDigits: 0 })} t)
        </div>
      </div>

      {/* 12-Month Bar Visualization */}
      <div className="grid grid-cols-12 gap-1.5 pt-4 pb-2 items-end h-32">
        {seasonalProfile.map((fraction, idx) => {
          const pct = fraction * 100;
          const tonnes = referenceCatch * fraction;
          const isPeak = idx === peakIdx;
          const isPostMonsoon = idx === 9 || idx === 10;
          const barHeightPct = Math.min(100, Math.max(8, (fraction / maxPct) * 100));

          let barColor = 'bg-slate-700 hover:bg-slate-600';
          if (isPeak) {
            barColor = 'bg-cyan-400 hover:bg-cyan-300 ring-2 ring-cyan-400/40';
          } else if (isPostMonsoon) {
            barColor = 'bg-cyan-600/80 hover:bg-cyan-500';
          }

          return (
            <div key={MONTH_NAMES[idx]} className="flex flex-col items-center h-full justify-end group relative">
              {/* Tooltip on hover */}
              <div className="pointer-events-none absolute -top-12 z-20 hidden group-hover:flex flex-col items-center rounded bg-slate-950 border border-slate-700 px-2 py-1 text-[9px] shadow-lg whitespace-nowrap">
                <span className="font-bold text-slate-200">{MONTH_FULL[idx]}</span>
                <span className="text-cyan-400 font-semibold">{pct.toFixed(1)}% (~{tonnes.toLocaleString('en-US', { maximumFractionDigits: 0 })} t)</span>
              </div>

              {/* Top value indicator for peak */}
              {isPeak && (
                <span className="text-[9px] font-bold text-cyan-300 mb-1">
                  {pct.toFixed(0)}%
                </span>
              )}

              {/* The bar */}
              <div
                className={`w-full rounded-t transition-all duration-200 ${barColor}`}
                style={{ height: `${barHeightPct}%` }}
              />

              {/* Month label */}
              <span className={`text-[10px] mt-1.5 font-medium ${isPeak ? 'text-cyan-300 font-bold' : isPostMonsoon ? 'text-slate-300' : 'text-slate-500'}`}>
                {MONTH_NAMES[idx]}
              </span>
            </div>
          );
        })}
      </div>

      {/* Seasonality Insights & Caveat */}
      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2 text-[10px]">
        <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-2 text-slate-300">
          <span className="font-semibold text-cyan-300">Peak Seasonal Window:</span> {MONTH_FULL[peakIdx]} represents {(seasonalProfile[peakIdx] * 100).toFixed(1)}% of annual commercial catch, following seasonal upwelling cooling (Sept–Oct) and subsequent coastal plankton blooms.
        </div>
        <div className="flex items-start gap-1.5 rounded-lg border border-slate-800 bg-slate-950/40 p-2 text-slate-400">
          <AlertCircle className="h-3.5 w-3.5 shrink-0 text-amber-400 mt-0.5" />
          <span>
            <strong className="text-slate-300">Operational Caveat:</strong> Landings trough during June–August reflects mandatory monsoonal fishing bans and rough seas rather than absence of fish.
          </span>
        </div>
      </div>
    </div>
  );
};
