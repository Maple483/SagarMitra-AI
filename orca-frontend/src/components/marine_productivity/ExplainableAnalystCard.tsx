import React, { useState } from 'react';
import {
  Brain,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  HelpCircle,
  ShieldAlert,
  Sparkles,
  Layers,
} from 'lucide-react';
import { FisheriesAnalystResponse } from './types';

interface ExplainableAnalystCardProps {
  analysis: FisheriesAnalystResponse;
}

export const ExplainableAnalystCard: React.FC<ExplainableAnalystCardProps> = ({
  analysis,
}) => {
  const [drawerOpen, setDrawerOpen] = useState(false);

  const obs = analysis.observed_evidence;
  const isWeak = obs.reliability_tier === 'WEAK_OR_UNCERTAIN_ASSOCIATION';

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 shadow-xl backdrop-blur-md">
      {/* Permanent Notice Badge */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
          <span className="font-semibold">{analysis.compact_notice}</span>
        </div>
        <button
          type="button"
          onClick={() => setDrawerOpen((v) => !v)}
          className="flex items-center gap-1 rounded bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-200 hover:bg-amber-500/30 transition"
        >
          {drawerOpen ? 'Hide Scientific Caveats' : 'Read Full Scientific Notice'}
          {drawerOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </button>
      </div>

      {/* Expandable Scientific Drawer */}
      {drawerOpen && (
        <div className="mb-4 rounded-lg border border-slate-700 bg-slate-950 p-3 text-xs leading-relaxed text-slate-300 shadow-inner">
          <h4 className="font-bold text-cyan-400 mb-1 flex items-center gap-1.5">
            <ShieldAlert className="h-4 w-4 text-cyan-400" /> Methodological & Ecological Constraints
          </h4>
          <p className="text-slate-300 mb-2">{analysis.full_scientific_disclaimer}</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] text-slate-400 pt-2 border-t border-slate-800">
            <div>
              <strong className="text-slate-200">Analytical Sample:</strong> {obs.n_observed_years} observed years (2007–2012); {obs.n_valid} paired observations for lag {obs.lag_years}.
            </div>
            <div>
              <strong className="text-slate-200">Autocorrelation Disclosure:</strong> Serial correlation may reduce effective degrees of freedom. Inferences are nominal i.i.d. statistics.
            </div>
          </div>
        </div>
      )}

      {/* Warning for ungrounded user questions */}
      {analysis.grounding_status === 'UNSUPPORTED_VARIABLES_DETECTED' && (
        <div className="mb-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
          <div className="font-bold flex items-center gap-1.5 mb-1">
            <AlertTriangle className="h-4 w-4 text-red-400" /> Unobserved Operational Variables in Query
          </div>
          <div>
            Your question references factors not tracked in observational marine datasets ({analysis.unsupported_variables.join(', ')}). Commercial landings are heavily influenced by fuel prices, subsidies, fleet vessel capacity, and trawler ban enforcement, none of which can be quantified from environmental series alone.
          </div>
        </div>
      )}

      {/* Section 1: Direct Answer Box */}
      <div className="mb-4 rounded-xl border border-cyan-500/30 bg-gradient-to-r from-cyan-950/40 via-slate-900 to-slate-950 p-3.5 shadow-md">
        <div className="flex items-center gap-2 text-xs font-bold text-cyan-300 uppercase tracking-wider mb-1.5">
          <Sparkles className="h-4 w-4 text-cyan-400" />
          Direct Empirical Synthesis
        </div>
        <p className="text-sm font-medium leading-relaxed text-slate-100">
          {analysis.direct_answer}
        </p>
      </div>

      {/* Grid of Two Columns: What Data Shows vs Possible Factors */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Column A: What the Data Shows */}
        <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-2 flex items-center gap-1.5">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" /> What the Data Shows
          </h4>
          <ul className="space-y-2 text-xs text-slate-300">
            {analysis.what_the_data_shows.map((bullet, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 mt-1.5 shrink-0" />
                <span>{bullet}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Column B: Possible Contributing Factors (Hypotheses) */}
        <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 mb-2 flex items-center gap-1.5">
            <HelpCircle className="h-4 w-4 text-cyan-400" /> Possible Contributing Factors
          </h4>
          <ul className="space-y-2.5 text-xs text-slate-300">
            {analysis.possible_contributing_factors.map((factor, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 mt-1.5 shrink-0" />
                <span>{factor}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
};
