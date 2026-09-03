"""
Strict Pydantic v2 schemas and canonical enums for the Marine Productivity & Fisheries Analyst module.
All schemas are immutable or validated with strict types to ensure zero data drift.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, model_validator


class MaritimeStateEnum(str, Enum):
    GUJARAT = "Gujarat"
    MAHARASHTRA = "Maharashtra"
    GOA = "Goa"
    KARNATAKA = "Karnataka"
    KERALA = "Kerala"
    TAMIL_NADU = "Tamil Nadu"
    ANDHRA_PRADESH = "Andhra Pradesh"
    ODISHA = "Odisha"
    WEST_BENGAL = "West Bengal"


class CommercialSpeciesEnum(str, Enum):
    OIL_SARDINE = "Oil Sardine"
    INDIAN_MACKEREL = "Indian Mackerel"
    RIBBON_FISH = "Ribbon Fish"
    PENAEID_SHRIMP = "Penaeid Shrimp"
    NON_PENAEID_SHRIMP = "Non-Penaeid Shrimp"
    CEPHALOPODS = "Cephalopods"
    TUNA = "Tuna"
    THREADFIN_BREAMS = "Threadfin Breams"
    SHARKS_AND_RAYS = "Sharks and Rays"
    # Curated aliases from orca-dataset.json
    SARDINE = "Sardine"
    ANCHOVY = "Anchovy"
    CROAKER = "Croaker"
    POMFRET = "Pomfret"
    RIBBONFISH = "Ribbonfish"
    SEER_FISH = "Seer Fish"
    SHARK_AND_RAY = "Shark & Ray"


class EnvironmentalVariableEnum(str, Enum):
    SST = "sst"
    CHLOROPHYLL = "chlorophyll"


class LagYearsEnum(int, Enum):
    LAG_0 = 0
    LAG_1 = 1


class CIStatusEnum(str, Enum):
    VALID = "VALID"
    PERFECT_CORRELATION = "PERFECT_CORRELATION"
    INSUFFICIENT_SAMPLE_FOR_CI = "INSUFFICIENT_SAMPLE_FOR_CI"


class PValueStatusEnum(str, Enum):
    VALID = "VALID"
    PERFECT_CORRELATION = "PERFECT_CORRELATION"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    CONSTANT_SERIES = "CONSTANT_SERIES"


class AutocorrelationStatusEnum(str, Enum):
    VALID = "VALID"
    UNSTABLE = "UNSTABLE"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"


class ReliabilityTierEnum(str, Enum):
    EXPLORATORY_OBSERVATIONAL_BASELINE = "EXPLORATORY_OBSERVATIONAL_BASELINE"
    INSUFFICIENT_PAIRED_DATA = "INSUFFICIENT_PAIRED_DATA"
    UNDEFINED_ZERO_VARIANCE = "UNDEFINED_ZERO_VARIANCE"
    WEAK_OR_UNCERTAIN_ASSOCIATION = "WEAK_OR_UNCERTAIN_ASSOCIATION"


class GroundingStatusEnum(str, Enum):
    GROUNDED = "GROUNDED"
    UNSUPPORTED_VARIABLES_DETECTED = "UNSUPPORTED_VARIABLES_DETECTED"


class ScenarioStatusEnum(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE_MISSING_2012_ANCHOR = "UNAVAILABLE_MISSING_2012_ANCHOR"


class SpatialProxyTypeEnum(str, Enum):
    COASTAL_OFFSHORE_50KM_BUFFER = "COASTAL_OFFSHORE_50KM_BUFFER"


class ExposureConfidenceEnum(str, Enum):
    MODERATE_COASTAL_PROXY = "MODERATE_COASTAL_PROXY"
    HIGH_UNCERTAINTY_OCEANIC_PROXY = "HIGH_UNCERTAINTY_OCEANIC_PROXY"


class ScenarioNameEnum(str, Enum):
    LOW_RATE = "LOW_RATE"
    CENTRAL_RATE = "CENTRAL_RATE"
    HIGH_RATE = "HIGH_RATE"


class HypothesisStatusEnum(str, Enum):
    UNTESTED_HYPOTHESIS = "UNTESTED_HYPOTHESIS"


class HypothesisDirectionEnum(str, Enum):
    POSITIVE_CO_MOVEMENT = "POSITIVE_CO_MOVEMENT"
    NEGATIVE_CO_MOVEMENT = "NEGATIVE_CO_MOVEMENT"
    INCONCLUSIVE = "INCONCLUSIVE"


class DatasetVersionInfo(BaseModel):
    provider: str
    dataset_name: str
    dataset_version: str
    variable_name: str
    retrieval_date: str


class ConfidenceInterval(BaseModel):
    lower: Optional[float] = None
    upper: Optional[float] = None
    confidence_level: float = Field(0.95, gt=0.0, lt=1.0)
    method: str
    status: CIStatusEnum


class StructuredHypothesis(BaseModel):
    variable: EnvironmentalVariableEnum
    mechanism: str
    direction: HypothesisDirectionEnum
    status: HypothesisStatusEnum = HypothesisStatusEnum.UNTESTED_HYPOTHESIS
    caveat: str


class SpatialExposureProxy(BaseModel):
    proxy_type: SpatialProxyTypeEnum = SpatialProxyTypeEnum.COASTAL_OFFSHORE_50KM_BUFFER
    buffer_km: int = 50
    state_coastal_buffer_definition: str = (
        "State coastline reprojected to EPSG:7755, buffered 50 km seaward, intersected with Indian EEZ"
    )
    boundary_sources: str = (
        "Natural Earth 1:10m Physical Coastlines (v5.1.4) / Flanders Marine Institute VLIZ EEZ v12"
    )
    islands_policy: str = (
        "Mainland coastal states only; island territories (Lakshadweep, A&N) are separate spatial domains"
    )
    exposure_confidence: ExposureConfidenceEnum


class ObservedEvidenceSection(BaseModel):
    n_observed_years: int
    n_paired: int
    n_valid: int
    n_difference_pairs: int
    lag_years: int
    lag_direction_label: str
    pearson_r: Optional[float]
    descriptive_first_difference_r: Optional[float]
    level_nominal_p_value_iid_assumed: Optional[float]
    level_p_value_status: PValueStatusEnum
    lag1_autocorrelation_env: Optional[float]
    lag1_autocorrelation_landings: Optional[float]
    autocorrelation_product: Optional[float]
    autocorrelation_status: AutocorrelationStatusEnum
    diagnostic_effective_sample_size_neff: Optional[float]
    level_confidence_interval: ConfidenceInterval
    reliability_tier: ReliabilityTierEnum
    nominal_p_disclaimer: str


class ScenarioTrajectorySection(BaseModel):
    scenario_id: str
    scenario_version: str
    scenario_status: ScenarioStatusEnum
    scenario_start_year: int = 2013
    scenario_end_year: int = 2026
    parameter_source: str
    n_modeled: int
    n_total: int
    modeled_fraction_pct: float
    sst_sensitivity_rates_c_per_year: Dict[str, float]
    chl_sensitivity_rates_pct_per_year: Dict[str, float]
    scenario_disclaimer: str

    @model_validator(mode="after")
    def validate_counts(self):
        if not (0 <= self.n_modeled <= self.n_total):
            raise ValueError("n_modeled must be between 0 and n_total")
        return self


class ScientificFactBundle(BaseModel):
    """Immutable fact container passed from scientific_interpreter to analyst."""
    model_config = {"frozen": True}
    analysis_id: str
    state: MaritimeStateEnum
    species: str
    environmental_variable: EnvironmentalVariableEnum
    lag_years: LagYearsEnum
    n_observed_years: int
    n_paired: int
    n_valid: int
    n_difference_pairs: int
    pearson_r: Optional[float]
    descriptive_first_difference_r: Optional[float]
    level_nominal_p_value_iid_assumed: Optional[float]
    level_p_value_status: PValueStatusEnum
    lag1_autocorrelation_env: Optional[float]
    lag1_autocorrelation_landings: Optional[float]
    autocorrelation_product: Optional[float]
    autocorrelation_status: AutocorrelationStatusEnum
    diagnostic_effective_sample_size_neff: Optional[float]
    reliability_tier: ReliabilityTierEnum
    exposure_confidence: ExposureConfidenceEnum
    scenario_status: ScenarioStatusEnum
    snapshot_id: str
    dataset_sha256_hash: str
    # Context metrics
    base_year: int = 2007
    end_year: int = 2012
    catch_2007: Optional[float] = None
    catch_2012: Optional[float] = None
    catch_2026_scenario: Optional[float] = None
    env_2007: Optional[float] = None
    env_2012: Optional[float] = None
    env_2026_scenario: Optional[float] = None
    peak_month_name: Optional[str] = None
    peak_month_pct: Optional[float] = None
    peak_month_tonnes: Optional[float] = None
    post_monsoon_tonnes: Optional[float] = None
    post_monsoon_pct: Optional[float] = None


class FisheriesAnalysisRequest(BaseModel):
    state: MaritimeStateEnum
    species: str
    environmental_variable: EnvironmentalVariableEnum = EnvironmentalVariableEnum.SST
    lag_years: LagYearsEnum = LagYearsEnum.LAG_1
    query_text: Optional[str] = Field(None, description="Non-authoritative display context metadata")


class FisheriesAnalystResponse(BaseModel):
    analysis_id: str
    analysis_timestamp_utc: datetime
    methodology_version: str
    snapshot_id: str
    dataset_sha256_hash: str
    landings_dataset: DatasetVersionInfo
    sst_dataset: DatasetVersionInfo
    chlorophyll_dataset: DatasetVersionInfo
    state: MaritimeStateEnum
    species: str
    query_text: Optional[str]
    grounding_status: str
    unsupported_variables: List[str]
    observed_evidence: ObservedEvidenceSection
    scenario_trajectory: ScenarioTrajectorySection
    spatial_exposure: SpatialExposureProxy
    compact_notice: str
    full_scientific_disclaimer: str
    structured_hypotheses: List[StructuredHypothesis]
    # Descriptive summaries for UI cards
    direct_answer: str
    what_the_data_shows: List[str]
    possible_contributing_factors: List[str]
