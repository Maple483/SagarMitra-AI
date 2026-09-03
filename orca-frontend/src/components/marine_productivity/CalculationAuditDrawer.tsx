import React, { useState } from 'react';
import {
  FileText,
  ChevronDown,
  ChevronUp,
  Hash,
  Activity,
  Layers,
  ShieldCheck,
  Compass,
} from 'lucide-react';
import { FisheriesAnalystResponse } from './types';

interface CalculationAuditDrawerProps {
  analysis: FisheriesAnalystResponse;
}

export const CalculationAuditDrawer: React.FC<CalculationAuditDrawerProps> = ({
  analysis,
}) => {
  const [isOpen, setIsOpen] = useState(false);

  const obs = analysis.observed_evidence;
  const ci = obs.level_confidence_interval;
  const proxy = analysis.spatial_exposure;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 shadow-xl">
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className="w-full flex items-center justify-between text-left"
      >
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-cyan-400" />
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Statistical Calculation & Data Provenance Audit
            </h3>
            <p className="text-[11px] text-slate-400">
              Complete formula parameters, sample size accounting, and cryptographic SHA-256 snapshot hashes
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs font-semibold text-cyan-400">
          <span>{isOpen ? 'Collapse Audit Details' : 'Expand Audit Details'}</span>
          {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </div>
      </button>

      {isOpen && (
        <div className="mt-4 space-y-4 border-t border-slate-800 pt-4 text-xs">
          {/* Section 1: Sample Size Accounting */}
          <div>
            <h4 className="font-bold text-slate-200 mb-2 flex items-center gap-1.5">
              <Activity className="h-4 w-4 text-emerald-400" /> Sample Size Disaggregation
            </h4>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-2.5">
                <span className="text-[10px] text-slate-400 uppercase font-semibold">Observed Years</span>
                <div className="text-sm font-bold text-emerald-400">{obs.n_observed_years} (2007–2012)</div>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-2.5">
                <span className="text-[10px] text-slate-400 uppercase font-semibold">Paired Years</span>
                <div className="text-sm font-bold text-cyan-400">{obs.n_paired} (Lag {obs.lag_years})</div>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-2.5">
                <span className="text-[10px] text-slate-400 uppercase font-semibold">Valid Non-Null Pairs</span>
                <div className="text-sm font-bold text-slate-100">{obs.n_valid}</div>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-2.5">
                <span className="text-[10px] text-slate-400 uppercase font-semibold">Difference Pairs</span>
                <div className="text-sm font-bold text-amber-400">{obs.n_difference_pairs}</div>
              </div>
            </div>
          </div>

          {/* Section 2: Mathematical Statistics */}
          <div>
            <h4 className="font-bold text-slate-200 mb-2 flex items-center gap-1.5">
              <Layers className="h-4 w-4 text-cyan-400" /> Empirical Association Metrics
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-2.5">
                <span className="text-[10px] text-slate-400 uppercase font-semibold">Pearson r (Level)</span>
                <div className="text-sm font-bold text-slate-100">
                  {obs.pearson_r !== null ? obs.pearson_r.toFixed(3) : 'N/A'}
                </div>
                <span className="text-[9px] text-slate-500">
                  Diff r_Δ: {obs.descriptive_first_difference_r !== null ? obs.descriptive_first_difference_r.toFixed(3) : 'N/A'}
                </span>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-2.5">
                <span className="text-[10px] text-slate-400 uppercase font-semibold">Nominal p-Value (i.i.d.)</span>
                <div className="text-sm font-bold text-slate-100">
                  {obs.level_nominal_p_value_iid_assumed !== null
                    ? obs.level_nominal_p_value_iid_assumed.toFixed(4)
                    : 'N/A'}
                </div>
                <span className="text-[9px] text-slate-500">Student's t, df={obs.n_valid - 2}</span>
              </div>
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-2.5">
                <span className="text-[10px] text-slate-400 uppercase font-semibold">Fisher's z 95% CI</span>
                <div className="text-sm font-bold text-slate-100">
                  {ci.lower !== null && ci.upper !== null
                    ? `[${ci.lower.toFixed(2)}, ${ci.upper.toFixed(2)}]`
                    : 'Insufficient Sample (N < 4)'}
                </div>
                <span className="text-[9px] text-slate-500">Method: {ci.method}</span>
              </div>
            </div>
          </div>

          {/* Section 3: Autocorrelation & Effective Sample Size */}
          <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-3">
            <h4 className="font-bold text-slate-200 mb-1.5 flex items-center gap-1.5">
              <Compass className="h-4 w-4 text-amber-400" /> Autocorrelation Decomposition & N_eff
            </h4>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2 text-[11px]">
              <div>
                <span className="text-slate-400">ρ_X (Env lag-1):</span>{' '}
                <strong className="text-slate-200">
                  {obs.lag1_autocorrelation_env !== null ? obs.lag1_autocorrelation_env.toFixed(3) : 'N/A'}
                </strong>
              </div>
              <div>
                <span className="text-slate-400">ρ_Y (Catch lag-1):</span>{' '}
                <strong className="text-slate-200">
                  {obs.lag1_autocorrelation_landings !== null ? obs.lag1_autocorrelation_landings.toFixed(3) : 'N/A'}
                </strong>
              </div>
              <div>
                <span className="text-slate-400">Product ρ_X·ρ_Y:</span>{' '}
                <strong className="text-slate-200">
                  {obs.autocorrelation_product !== null ? obs.autocorrelation_product.toFixed(3) : 'N/A'}
                </strong>
              </div>
              <div>
                <span className="text-slate-400">Diagnostic N_eff:</span>{' '}
                <strong className="text-cyan-400">
                  {obs.diagnostic_effective_sample_size_neff !== null
                    ? obs.diagnostic_effective_sample_size_neff.toFixed(1)
                    : 'N/A'}
                </strong>
              </div>
            </div>
            <p className="text-[10px] text-slate-400">
              {obs.nominal_p_disclaimer}
            </p>
          </div>

          {/* Section 4: Spatial Exposure Definition */}
          <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-3">
            <h4 className="font-bold text-slate-200 mb-1.5 flex items-center gap-1.5">
              <Compass className="h-4 w-4 text-cyan-400" /> State-Specific Spatial Exposure Definition
            </h4>
            <p className="text-[11px] text-slate-300 mb-1">
              <strong>Definition:</strong> {proxy.state_coastal_buffer_definition}
            </p>
            <div className="flex flex-wrap gap-4 text-[10px] text-slate-400">
              <span><strong>Sources:</strong> {proxy.boundary_sources}</span>
              <span><strong>Buffer:</strong> {proxy.buffer_km} km seaward</span>
              <span><strong>Territory Policy:</strong> {proxy.islands_policy}</span>
            </div>
          </div>

          {/* Section 5: Cryptographic Snapshot Checksum */}
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-3">
            <h4 className="font-bold text-emerald-400 mb-1.5 flex items-center gap-1.5">
              <ShieldCheck className="h-4 w-4 text-emerald-400" /> Cryptographic Snapshot Checksum & Version Pinning
            </h4>
            <div className="space-y-1 font-mono text-[10px] text-slate-300">
              <div><strong>Snapshot ID:</strong> {analysis.snapshot_id}</div>
              <div className="truncate"><strong>SHA-256 Checksum:</strong> {analysis.dataset_sha256_hash}</div>
              <div><strong>Methodology Version:</strong> {analysis.methodology_version}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
