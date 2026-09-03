import React from 'react';
import { Fish, Calendar } from 'lucide-react';
import { MaritimeState, EnvironmentalVariable } from './types';

interface ProductivityHeaderProps {
  states: string[];
  selectedState: MaritimeState;
  onSelectState: (s: MaritimeState) => void;
  speciesList: string[];
  selectedSpecies: string;
  onSelectSpecies: (sp: string) => void;
  selectedVariable: EnvironmentalVariable;
  onSelectVariable: (v: EnvironmentalVariable) => void;
  selectedLag: number;
  onSelectLag: (lag: number) => void;
}

export const ProductivityHeader: React.FC<ProductivityHeaderProps> = ({
  states,
  selectedState,
  onSelectState,
  speciesList,
  selectedSpecies,
  onSelectSpecies,
  selectedVariable,
  onSelectVariable,
  selectedLag,
  onSelectLag,
}) => {
  return (
    <div className="border-b border-slate-800 bg-slate-900/90 p-4 sm:p-5 backdrop-blur-md">
      {/* Title Section */}
      <div className="flex items-center gap-3 mb-5 pr-12">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 shadow-sm">
          <Fish className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-base sm:text-lg font-bold text-slate-100 tracking-tight">
            Fisheries Landings & Marine Productivity Analyst
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Correlating sea surface temperature & chlorophyll with marine fish landings across Indian coastal waters
          </p>
        </div>
      </div>

      {/* Control Filters Bar */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {/* Coastal Maritime State */}
        <div>
          <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
            Coastal Maritime State
          </label>
          <select
            value={selectedState}
            onChange={(e) => onSelectState(e.target.value as MaritimeState)}
            className="w-full h-[38px] rounded-lg border border-slate-700 bg-slate-950 px-3 text-xs font-medium text-slate-100 shadow-inner focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 cursor-pointer transition"
          >
            {states.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        {/* Target Commercial Species */}
        <div>
          <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
            Target Commercial Species
          </label>
          <select
            value={selectedSpecies}
            onChange={(e) => onSelectSpecies(e.target.value)}
            className="w-full h-[38px] rounded-lg border border-slate-700 bg-slate-950 px-3 text-xs font-medium text-slate-100 shadow-inner focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 cursor-pointer transition"
          >
            {speciesList.map((sp) => (
              <option key={sp} value={sp}>
                {sp}
              </option>
            ))}
          </select>
        </div>

        {/* Environmental Parameter Toggle */}
        <div>
          <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">
            Environmental Variable
          </label>
          <div className="grid grid-cols-2 gap-1 rounded-lg border border-slate-700 bg-slate-950 p-1 h-[38px]">
            <button
              type="button"
              onClick={() => onSelectVariable('sst')}
              className={`rounded-md px-2 text-xs font-semibold transition flex items-center justify-center cursor-pointer ${
                selectedVariable === 'sst'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              SST (°C)
            </button>
            <button
              type="button"
              onClick={() => onSelectVariable('chlorophyll')}
              className={`rounded-md px-2 text-xs font-semibold transition flex items-center justify-center cursor-pointer ${
                selectedVariable === 'chlorophyll'
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Chlorophyll (mg/m³)
            </button>
          </div>
        </div>

        {/* Effect Timing / Lag Horizon Toggle */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Analysis Timing (Lag)
            </label>
            <span className="text-[10px] text-slate-500 hidden sm:inline" title="1-Year Lag evaluates how environmental conditions affect larval recruitment and subsequent catch 1 year later">
              {selectedLag === 1 ? 'Next year impact' : 'Same year impact'}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-1 rounded-lg border border-slate-700 bg-slate-950 p-1 h-[38px]">
            <button
              type="button"
              onClick={() => onSelectLag(1)}
              title="1-Year Lag: Correlates environmental conditions with catch 1 year later (models spawning and recruitment delay)"
              className={`flex items-center justify-center gap-1.5 rounded-md px-2 text-xs font-semibold transition cursor-pointer ${
                selectedLag === 1
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Calendar className="h-3 w-3" />
              <span>1-Year Lag</span>
            </button>
            <button
              type="button"
              onClick={() => onSelectLag(0)}
              title="Same Year: Correlates environmental conditions with catch during the same calendar year"
              className={`flex items-center justify-center gap-1.5 rounded-md px-2 text-xs font-semibold transition cursor-pointer ${
                selectedLag === 0
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Calendar className="h-3 w-3" />
              <span>Same Year</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
