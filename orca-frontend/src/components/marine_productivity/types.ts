export type MaritimeState =
  | 'Gujarat'
  | 'Maharashtra'
  | 'Goa'
  | 'Karnataka'
  | 'Kerala'
  | 'Tamil Nadu'
  | 'Andhra Pradesh'
  | 'Odisha'
  | 'West Bengal';

export type EnvironmentalVariable = 'sst' | 'chlorophyll';

export interface ConfidenceInterval {
  lower: number | null;
  upper: number | null;
  confidence_level: number;
  method: string;
  status: 'VALID' | 'PERFECT_CORRELATION' | 'INSUFFICIENT_SAMPLE_FOR_CI';
}

export interface ObservedEvidence {
  n_observed_years: number;
  n_paired: number;
  n_valid: number;
  n_difference_pairs: number;
  lag_years: number;
  lag_direction_label: string;
  pearson_r: number | null;
  descriptive_first_difference_r: number | null;
  level_nominal_p_value_iid_assumed: number | null;
  level_p_value_status: string;
  lag1_autocorrelation_env: number | null;
  lag1_autocorrelation_landings: number | null;
  autocorrelation_product: number | null;
  autocorrelation_status: string;
  diagnostic_effective_sample_size_neff: number | null;
  level_confidence_interval: ConfidenceInterval;
  reliability_tier: string;
  nominal_p_disclaimer: string;
}

export interface ScenarioTrajectory {
  scenario_id: string;
  scenario_version: string;
  scenario_status: 'AVAILABLE' | 'UNAVAILABLE_MISSING_2012_ANCHOR';
  scenario_start_year: number;
  scenario_end_year: number;
  parameter_source: string;
  n_modeled: number;
  n_total: number;
  modeled_fraction_pct: number;
  sst_sensitivity_rates_c_per_year: Record<string, number>;
  chl_sensitivity_rates_pct_per_year: Record<string, number>;
  scenario_disclaimer: string;
}

export interface DatasetVersionInfo {
  provider: string;
  dataset_name: string;
  dataset_version: string;
  variable_name: string;
  retrieval_date: string;
}

export interface StructuredHypothesis {
  variable: EnvironmentalVariable;
  mechanism: string;
  direction: 'POSITIVE_CO_MOVEMENT' | 'NEGATIVE_CO_MOVEMENT' | 'INCONCLUSIVE';
  status: 'UNTESTED_HYPOTHESIS';
  caveat: string;
}

export interface SpatialExposureProxy {
  proxy_type: string;
  buffer_km: number;
  state_coastal_buffer_definition: string;
  boundary_sources: string;
  islands_policy: string;
  exposure_confidence: 'MODERATE_COASTAL_PROXY' | 'HIGH_UNCERTAINTY_OCEANIC_PROXY';
}

export interface FisheriesAnalystResponse {
  analysis_id: string;
  analysis_timestamp_utc: string;
  methodology_version: string;
  snapshot_id: string;
  dataset_sha256_hash: string;
  landings_dataset: DatasetVersionInfo;
  sst_dataset: DatasetVersionInfo;
  chlorophyll_dataset: DatasetVersionInfo;
  state: MaritimeState;
  species: string;
  query_text: string | null;
  grounding_status: 'GROUNDED' | 'UNSUPPORTED_VARIABLES_DETECTED';
  unsupported_variables: string[];
  observed_evidence: ObservedEvidence;
  scenario_trajectory: ScenarioTrajectory;
  spatial_exposure: SpatialExposureProxy;
  compact_notice: string;
  full_scientific_disclaimer: string;
  structured_hypotheses: StructuredHypothesis[];
  direct_answer: string;
  what_the_data_shows: string[];
  possible_contributing_factors: string[];
}

export interface TimeseriesData {
  state: string;
  species: string;
  variable: string;
  observed_years: number[];
  scenario_years: number[];
  landings: Record<number, number>;
  environmental: Record<number, number>;
  trajectories: {
    sst?: Record<string, Record<number, number>>;
    chlorophyll?: Record<string, Record<number, number>>;
  };
  seasonal_profile: number[];
  provenance_encoding: Record<string, string>;
}
