"""
FastAPI Router for Marine Productivity & Fisheries Analyst endpoints.
Mounted at /api/marine-productivity
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, status

from .schemas import (
    MaritimeStateEnum,
    CommercialSpeciesEnum,
    EnvironmentalVariableEnum,
    LagYearsEnum,
    FisheriesAnalysisRequest,
    FisheriesAnalystResponse,
    ObservedEvidenceSection,
    SpatialExposureProxy,
    SpatialProxyTypeEnum,
    ExposureConfidenceEnum,
)
from .repository import get_repository
from .scientific_interpreter import ScientificInterpreter
from .analyst import TemplateNarrativeCompiler
from .satellite import get_satellite_info

router = APIRouter(prefix="/api/marine-productivity", tags=["Marine Productivity"])


COMPACT_NOTICE = (
    "⚠️ Scientific Notice: Reported landings ≠ fish biomass; correlation ≠ causation; "
    "scenario trajectories are NOT catch forecasts."
)

FULL_DISCLAIMER = (
    "Reported marine landings (tonnes) measure commercial harvest landed at coastal ports, "
    "NOT biological productivity or total fish stock biomass. Catch volume is heavily confounded "
    "by unmeasured operational variables: fishing effort (vessel trips, fleet engine capacity), "
    "gear technology, diesel subsidies, market demand, and seasonal monsoonal fishing bans. "
    "Observed relationships represent observational associations and do not establish ecological "
    "causation. Environmental scenario trajectories (2013-2026) are illustrative sensitivity "
    "assumptions and do NOT project future fisheries catch."
)


@router.get("/regions", response_model=List[str])
def get_regions():
    """Returns the 9 canonical Indian coastal maritime states."""
    repo = get_repository()
    return repo.get_available_states()


@router.get("/species", response_model=List[str])
def get_species(state: Optional[str] = Query(None, description="Filter species by coastal state")):
    """Returns the commercial species/categories available for analysis."""
    repo = get_repository()
    return repo.get_available_species(state)


@router.get("/timeseries")
def get_timeseries(
    state: MaritimeStateEnum = Query(MaritimeStateEnum.KARNATAKA),
    species: str = Query("Sardine"),
    variable: EnvironmentalVariableEnum = Query(EnvironmentalVariableEnum.SST),
):
    """
    Returns full time-series data (2007-2026) formatted for multi-source provenance
    visual encoding (observed solid line vs scenario dashed line).
    """
    repo = get_repository()
    catch_full = repo.get_landings_series(state.value, species, observed_only=False)
    env_full = repo.get_environmental_series(state.value, variable.value, observed_only=False)
    profile = repo.get_seasonal_profile(species)

    # Evaluate scenario trajectories
    bundle, hypotheses, extra = ScientificInterpreter.evaluate(
        state=state, species=species, variable=variable, lag_years=LagYearsEnum.LAG_1
    )

    trajectories = extra.get("trajectories", {})

    return {
        "state": state.value,
        "species": species,
        "variable": variable.value,
        "observed_years": [2007, 2008, 2009, 2010, 2011, 2012],
        "scenario_years": list(range(2013, 2027)),
        "landings": catch_full,
        "environmental": env_full,
        "trajectories": trajectories,
        "seasonal_profile": profile,
        "provenance_encoding": {
            "observed_landings": "Solid emerald line with filled circle markers (2007-2012)",
            "historical_analysis_env": "Solid amber/cyan line with filled diamond markers (2007-2012)",
            "projection_boundary": "Vertical dashed divider at 2012/2013",
            "scenario_trajectories": "Dashed lines with hollow square markers (2013-2026)",
            "endpoint_label": "2026 Synthetic Scenario Value",
        },
    }


@router.post("/explain", response_model=FisheriesAnalystResponse)
def explain_fisheries_relationship(req: FisheriesAnalysisRequest):
    """
    Executes decoupled statistical evaluation and returns grounded template-compiled
    evidence, scenario trajectories, and domain hypotheses with zero causal claims.
    """
    repo = get_repository()
    landings_info, sst_info, chl_info = repo.get_dataset_metadata()

    # 1. Check query grounding
    grounding_status, unsupported = TemplateNarrativeCompiler.check_query_grounding(req.query_text)
    unsupported_notice = None
    if unsupported:
        unsupported_notice = (
            f"The query mentions unobserved operational factor(s): {', '.join(unsupported)}. "
            f"The dataset does not track fishing effort, fleet capacity, fuel subsidies, or ban "
            f"enforcement. These factors cannot be evaluated with the available variables."
        )

    # 2. Evaluate fact bundle
    bundle, hypotheses, extra = ScientificInterpreter.evaluate(
        state=req.state,
        species=req.species,
        variable=req.environmental_variable,
        lag_years=req.lag_years,
    )

    # 3. Compile narrative (with query_text if provided)
    direct_ans, data_shows, contrib_factors = TemplateNarrativeCompiler.compile_narrative(
        bundle=bundle, hypotheses=hypotheses, query_text=req.query_text
    )

    # 4. Assemble observed evidence section
    ci_val = extra["ci"]
    lag_label = f"{req.environmental_variable.value.upper()} leading catch by {req.lag_years.value} year" if req.lag_years.value > 0 else "Same-year exposure"
    evidence_section = ObservedEvidenceSection(
        n_observed_years=bundle.n_observed_years,
        n_paired=bundle.n_paired,
        n_valid=bundle.n_valid,
        n_difference_pairs=bundle.n_difference_pairs,
        lag_years=bundle.lag_years.value,
        lag_direction_label=lag_label,
        pearson_r=bundle.pearson_r,
        descriptive_first_difference_r=bundle.descriptive_first_difference_r,
        level_nominal_p_value_iid_assumed=bundle.level_nominal_p_value_iid_assumed,
        level_p_value_status=bundle.level_p_value_status,
        lag1_autocorrelation_env=bundle.lag1_autocorrelation_env,
        lag1_autocorrelation_landings=bundle.lag1_autocorrelation_landings,
        autocorrelation_product=bundle.autocorrelation_product,
        autocorrelation_status=bundle.autocorrelation_status,
        diagnostic_effective_sample_size_neff=bundle.diagnostic_effective_sample_size_neff,
        level_confidence_interval=ci_val,
        reliability_tier=bundle.reliability_tier,
        nominal_p_disclaimer=(
            "Nominal p-value assumes serially independent observations (i.i.d.). "
            "Diagnostic N_eff is based on within-series lag-1 autocorrelation and "
            "indicates potential loss of degrees of freedom. Inferences are not "
            "adjusted for serial correlation."
        ),
    )

    # 5. Assemble spatial exposure proxy
    spatial_proxy = SpatialExposureProxy(
        proxy_type=SpatialProxyTypeEnum.COASTAL_OFFSHORE_50KM_BUFFER,
        buffer_km=50,
        exposure_confidence=bundle.exposure_confidence,
    )

    scenario_sec = extra["scenario_section"]

    return FisheriesAnalystResponse(
        analysis_id=bundle.analysis_id,
        analysis_timestamp_utc=datetime.now(timezone.utc),
        methodology_version="v1.0.0",
        snapshot_id=bundle.snapshot_id,
        dataset_sha256_hash=bundle.dataset_sha256_hash,
        landings_dataset=landings_info,
        sst_dataset=sst_info,
        chlorophyll_dataset=chl_info,
        state=req.state,
        species=req.species,
        query_text=req.query_text,
        grounding_status=grounding_status,
        unsupported_variables=unsupported,
        observed_evidence=evidence_section,
        scenario_trajectory=scenario_sec,
        spatial_exposure=spatial_proxy,
        compact_notice=COMPACT_NOTICE,
        full_scientific_disclaimer=FULL_DISCLAIMER,
        structured_hypotheses=hypotheses,
        direct_answer=direct_ans,
        what_the_data_shows=data_shows,
        possible_contributing_factors=contrib_factors,
    )


@router.get("/satellite-info")
def get_satellite_context():
    """Returns NASA GIBS Near-Real-Time WMS configuration, layer details, and health check."""
    return get_satellite_info()
