import React, { useEffect, useState } from 'react';
import { X, RefreshCw, AlertTriangle, Fish, Search, Sparkles } from 'lucide-react';
import {
  MaritimeState,
  EnvironmentalVariable,
  FisheriesAnalystResponse,
  TimeseriesData,
} from './types';
import { ProductivityHeader } from './ProductivityHeader';
import { EnvironmentalTrendChart } from './EnvironmentalTrendChart';
import { SeasonalCatchBarChart } from './SeasonalCatchBarChart';
import { LiveSatelliteViewer } from './LiveSatelliteViewer';
import { ExplainableAnalystCard } from './ExplainableAnalystCard';
import { CalculationAuditDrawer } from './CalculationAuditDrawer';

interface MarineProductivityModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultState?: MaritimeState;
}

export const MarineProductivityModal: React.FC<MarineProductivityModalProps> = ({
  isOpen,
  onClose,
  defaultState = 'Karnataka',
}) => {
  const [states, setStates] = useState<string[]>([]);
  const [selectedState, setSelectedState] = useState<MaritimeState>(defaultState);
  const [speciesList, setSpeciesList] = useState<string[]>([]);
  const [selectedSpecies, setSelectedSpecies] = useState<string>('Sardine');
  const [selectedVariable, setSelectedVariable] = useState<EnvironmentalVariable>('sst');
  const [selectedLag, setSelectedLag] = useState<number>(1);
  const [queryInput, setQueryInput] = useState<string>('');

  const [timeseries, setTimeseries] = useState<TimeseriesData | null>(null);
  const [analysis, setAnalysis] = useState<FisheriesAnalystResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Load available regions on mount
  useEffect(() => {
    if (!isOpen) return;
    fetch('http://localhost:8000/api/marine-productivity/regions')
      .then((r) => r.json())
      .then((data) => {
        setStates(data);
        if (data.length > 0 && !data.includes(selectedState)) {
          setSelectedState(data[0] as MaritimeState);
        }
      })
      .catch((err) => console.error('Failed to load regions:', err));
  }, [isOpen]);

  // Load available species when state changes
  useEffect(() => {
    if (!isOpen || !selectedState) return;
    fetch(`http://localhost:8000/api/marine-productivity/species?state=${encodeURIComponent(selectedState)}`)
      .then((r) => r.json())
      .then((data) => {
        setSpeciesList(data);
        if (data.length > 0 && !data.includes(selectedSpecies)) {
          setSelectedSpecies(data[0]);
        }
      })
      .catch((err) => console.error('Failed to load species:', err));
  }, [isOpen, selectedState]);

  // Fetch timeseries and explain analysis
  const executeAnalysis = async (userQuery?: string) => {
    if (!selectedState || !selectedSpecies) return;
    setLoading(true);
    setError(null);

    try {
      // 1. Fetch timeseries
      const tsUrl = `http://localhost:8000/api/marine-productivity/timeseries?state=${encodeURIComponent(
        selectedState
      )}&species=${encodeURIComponent(selectedSpecies)}&variable=${selectedVariable}`;
      const tsRes = await fetch(tsUrl);
      if (!tsRes.ok) throw new Error('Failed to load timeseries data');
      const tsData: TimeseriesData = await tsRes.json();
      setTimeseries(tsData);

      // 2. Fetch explain analysis
      const explainPayload = {
        state: selectedState,
        species: selectedSpecies,
        environmental_variable: selectedVariable,
        lag_years: selectedLag,
        query_text: userQuery || queryInput || undefined,
      };

      const explainRes = await fetch('http://localhost:8000/api/marine-productivity/explain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(explainPayload),
      });
      if (!explainRes.ok) throw new Error('Failed to compute scientific analysis');
      const explainData: FisheriesAnalystResponse = await explainRes.json();
      setAnalysis(explainData);
    } catch (err: any) {
      console.error(err);
      setError(err.message || 'Error running marine productivity analysis');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen && selectedState && selectedSpecies) {
      executeAnalysis();
    }
  }, [isOpen, selectedState, selectedSpecies, selectedVariable, selectedLag]);

  const SUGGESTED_QUERIES = [
    'Why did sardine landings increase between 2007 and 2012 in Karnataka?',
    'Is sea surface temperature correlated with fish catch?',
    'How does the monsoon season impact sardine availability?',
    'Show chlorophyll trends and sardine landings in Kerala',
  ];

  const parseQueryEntities = (q: string) => {
    const qLower = q.toLowerCase();
    for (const s of states) {
      if (qLower.includes(s.toLowerCase())) {
        setSelectedState(s as MaritimeState);
        break;
      }
    }
    for (const sp of speciesList) {
      if (qLower.includes(sp.toLowerCase())) {
        setSelectedSpecies(sp);
        break;
      }
    }
    if (qLower.includes('chlorophyll') || qLower.includes('chl') || qLower.includes('plankton')) {
      setSelectedVariable('chlorophyll');
    } else if (qLower.includes('sst') || qLower.includes('temperature') || qLower.includes('warm') || qLower.includes('heat')) {
      setSelectedVariable('sst');
    }
  };

  const handleQuerySubmit = (e?: React.FormEvent, customQuery?: string) => {
    if (e) e.preventDefault();
    const query = customQuery !== undefined ? customQuery : queryInput;
    if (query.trim()) {
      parseQueryEntities(query.trim());
      executeAnalysis(query.trim());
    } else {
      executeAnalysis();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Fisheries Landings and Environmental Analyst"
      className="fixed inset-0 z-[9999] flex items-center justify-center p-2 sm:p-4 bg-slate-950/80 backdrop-blur-md"
    >
      <div className="relative flex flex-col w-full max-w-7xl max-h-[96vh] rounded-2xl border border-slate-700/80 bg-slate-900 shadow-2xl overflow-hidden">
        {/* Top Floating Close Button */}
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 z-20 flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700 bg-slate-950 text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition shadow-lg"
          aria-label="Close modal"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Modal Header & Controls */}
        <ProductivityHeader
          states={states}
          selectedState={selectedState}
          onSelectState={setSelectedState}
          speciesList={speciesList}
          selectedSpecies={selectedSpecies}
          onSelectSpecies={setSelectedSpecies}
          selectedVariable={selectedVariable}
          onSelectVariable={setSelectedVariable}
          selectedLag={selectedLag}
          onSelectLag={setSelectedLag}
        />

        {/* Scrollable Content Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
          {/* Natural Language Question Bar */}
          <div className="space-y-2">
            <form onSubmit={(e) => handleQuerySubmit(e)} className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
                <input
                  type="text"
                  value={queryInput}
                  onChange={(e) => setQueryInput(e.target.value)}
                  placeholder="Ask an analytical question (e.g., 'Why did sardine landings increase between 2007 and 2012?')..."
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 py-2.5 pl-9 pr-4 text-xs text-slate-100 placeholder-slate-500 shadow-inner focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="flex items-center gap-1.5 rounded-xl bg-cyan-500 px-4 py-2 text-xs font-bold text-slate-950 hover:bg-cyan-400 transition disabled:opacity-50 shadow-md cursor-pointer shrink-0"
              >
                {loading ? (
                  <>
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    <span>Analyzing...</span>
                  </>
                ) : (
                  <span>Analyze</span>
                )}
              </button>
            </form>

            {/* Quick Analytical Suggestions */}
            <div className="flex items-center gap-2 pt-0.5 overflow-hidden">
              <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400 shrink-0 select-none">
                <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
                <span>Try asking:</span>
              </span>
              <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin scrollbar-thumb-slate-800">
                {SUGGESTED_QUERIES.map((q, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => {
                      setQueryInput(q);
                      handleQuerySubmit(undefined, q);
                    }}
                    className="shrink-0 text-xs rounded-lg border border-slate-700/80 bg-slate-950/70 hover:bg-cyan-950/30 hover:border-cyan-500/40 text-slate-300 hover:text-cyan-200 px-3 py-1.5 transition-all shadow-sm flex items-center gap-1.5 cursor-pointer whitespace-nowrap"
                  >
                    <span className="text-cyan-400 text-xs">✦</span>
                    <span>{q}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Active Loading Banner */}
          {loading && (
            <div className="flex items-center gap-2 rounded-xl border border-cyan-500/30 bg-cyan-950/30 px-3.5 py-2.5 text-xs text-cyan-300 animate-pulse">
              <RefreshCw className="h-4 w-4 animate-spin text-cyan-400" />
              <span>Analyzing marine productivity facts, SST/chlorophyll correlation, and observational landings...</span>
            </div>
          )}

          {/* Error Message */}
          {error && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-xs text-red-300 flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0 text-red-400 mt-0.5" />
              <div>
                <strong className="font-semibold">Analysis Failed:</strong> {error}
              </div>
            </div>
          )}

          {/* Loading Indicator */}
          {loading && !analysis && (
            <div className="flex flex-col items-center justify-center p-12 text-slate-400">
              <RefreshCw className="h-6 w-6 animate-spin text-cyan-400 mb-2" />
              <p className="text-xs font-medium">Evaluating non-contaminated empirical baselines & satellite data...</p>
            </div>
          )}

          {/* Main Content Layout */}
          {timeseries && analysis && (
            <div className="space-y-6">
              {/* Row 1: Coordinated Time-Series Visualizer */}
              <EnvironmentalTrendChart
                timeseries={timeseries}
                variable={selectedVariable}
                species={selectedSpecies}
              />

              {/* Row 2: Explainable Analyst Card */}
              <ExplainableAnalystCard analysis={analysis} />

              {/* Row 3: Coordinated Seasonal & Satellite Views */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <SeasonalCatchBarChart
                  seasonalProfile={timeseries.seasonal_profile}
                  species={selectedSpecies}
                  referenceCatch={analysis.observed_evidence.n_valid ? 56000 : 50000}
                />
                <LiveSatelliteViewer initialVariable={selectedVariable} />
              </div>

              {/* Row 4: Calculation Audit Drawer */}
              <CalculationAuditDrawer analysis={analysis} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
