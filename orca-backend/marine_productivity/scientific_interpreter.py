"""
Scientific Interpreter module.
Executes the empirical and scenario pipelines and synthesizes the immutable
ScientificFactBundle, completely decoupled from natural-language generation.
"""

import uuid
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from .schemas import (
    MaritimeStateEnum,
    CommercialSpeciesEnum,
    EnvironmentalVariableEnum,
    LagYearsEnum,
    ScientificFactBundle,
    StructuredHypothesis,
    HypothesisStatusEnum,
    HypothesisDirectionEnum,
    ExposureConfidenceEnum,
    ScenarioStatusEnum,
)
from .repository import get_repository
from .alignment import align_lagged_series, align_differenced_series
from .statistics import (
    compute_pearson_correlation,
    compute_diagnostic_neff,
    compute_descriptive_first_difference_r,
)
from .evidence_classifier import classify_evidence_reliability
from .scenario_engine import ScenarioTrajectoryEngine


MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]


class ScientificInterpreter:
    @staticmethod
    def evaluate(
        state: MaritimeStateEnum,
        species: str,
        variable: EnvironmentalVariableEnum = EnvironmentalVariableEnum.SST,
        lag_years: LagYearsEnum = LagYearsEnum.LAG_1,
    ) -> Tuple[ScientificFactBundle, List[StructuredHypothesis], Dict[str, Any]]:
        repo = get_repository()

        # 1. Retrieve historical observed series (2007-2012)
        catch_obs = repo.get_landings_series(state.value, species, observed_only=True)
        env_obs = repo.get_environmental_series(state.value, variable.value, observed_only=True)

        # 2. Retrieve full horizon series (2007-2026) for context
        catch_full = repo.get_landings_series(state.value, species, observed_only=False)
        env_full = repo.get_environmental_series(state.value, variable.value, observed_only=False)

        # 3. Temporal alignment on observed baseline
        lag_val = lag_years.value
        aligned = align_lagged_series(env_obs, catch_obs, lag_years=lag_val)
        diff_aligned = align_differenced_series(env_obs, catch_obs, lag_years=lag_val)

        # 4. Statistical computations on analytical sample
        r_val, p_val, p_status, ci_val = compute_pearson_correlation(
            aligned.x_values, aligned.y_values
        )
        r_diff = compute_descriptive_first_difference_r(
            diff_aligned.dx_values, diff_aligned.dy_values
        )

        rho_x, rho_y, rho_prod, n_eff, auto_status = compute_diagnostic_neff(
            aligned.x_values, aligned.y_values
        )

        # 5. Reliability classification
        rel_tier, reason_code = classify_evidence_reliability(
            aligned.n_valid, r_val, p_val, p_status
        )

        # 6. Habitat exposure confidence
        oceanic_species = [
            "Tuna", "Cephalopods", "Shark & Ray", "Sharks and Rays"
        ]
        is_oceanic = any(o.lower() in species.lower() for o in oceanic_species)
        exposure_conf = (
            ExposureConfidenceEnum.HIGH_UNCERTAINTY_OCEANIC_PROXY
            if is_oceanic
            else ExposureConfidenceEnum.MODERATE_COASTAL_PROXY
        )

        # 7. Scenario anchor check
        anchor_sst = env_obs.get(2012)
        chl_obs = repo.get_environmental_series(state.value, "chlorophyll", observed_only=True)
        anchor_chl = chl_obs.get(2012)

        scenario_section, trajectories = ScenarioTrajectoryEngine.generate_scenario_section(
            anchor_sst_2012=anchor_sst,
            anchor_chl_2012=anchor_chl,
            n_observed_years=6,
        )

        # 8. Contextual metrics
        c_2007 = catch_full.get(2007)
        c_2012 = catch_full.get(2012)
        c_2026 = catch_full.get(2026)
        e_2007 = env_full.get(2007)
        e_2012 = env_full.get(2012)
        e_2026 = env_full.get(2026)

        # Seasonal profile
        profile = repo.get_seasonal_profile(species)
        peak_idx = int(np.argmax(profile))
        peak_month_name = MONTH_NAMES[peak_idx]
        peak_month_pct = round(profile[peak_idx] * 100.0, 1)
        peak_month_tonnes = round(c_2007 * profile[peak_idx], 1) if c_2007 else None

        # Post-monsoon (October: idx 9, November: idx 10)
        post_monsoon_pct = round((profile[9] + profile[10]) * 100.0, 1)
        post_monsoon_tonnes = (
            round(c_2007 * (profile[9] + profile[10]), 1) if c_2007 else None
        )

        analysis_id = f"ORCA-MP-{uuid.uuid4().hex[:8].upper()}"

        # 9. Build Immutable Fact Bundle
        bundle = ScientificFactBundle(
            analysis_id=analysis_id,
            state=state,
            species=species,
            environmental_variable=variable,
            lag_years=lag_years,
            n_observed_years=6,
            n_paired=aligned.n_paired,
            n_valid=aligned.n_valid,
            n_difference_pairs=diff_aligned.n_difference_pairs,
            pearson_r=r_val,
            descriptive_first_difference_r=r_diff,
            level_nominal_p_value_iid_assumed=p_val,
            level_p_value_status=p_status,
            lag1_autocorrelation_env=rho_x,
            lag1_autocorrelation_landings=rho_y,
            autocorrelation_product=rho_prod,
            autocorrelation_status=auto_status,
            diagnostic_effective_sample_size_neff=n_eff,
            reliability_tier=rel_tier,
            exposure_confidence=exposure_conf,
            scenario_status=scenario_section.scenario_status,
            snapshot_id=repo.SNAPSHOT_ID,
            dataset_sha256_hash=repo.sha256_hash,
            base_year=2007,
            end_year=2012,
            catch_2007=c_2007,
            catch_2012=c_2012,
            catch_2026_scenario=c_2026,
            env_2007=e_2007,
            env_2012=e_2012,
            env_2026_scenario=e_2026,
            peak_month_name=peak_month_name,
            peak_month_pct=peak_month_pct,
            peak_month_tonnes=peak_month_tonnes,
            post_monsoon_tonnes=post_monsoon_tonnes,
            post_monsoon_pct=post_monsoon_pct,
        )

        # 10. Structured Hypotheses
        direction = (
            HypothesisDirectionEnum.POSITIVE_CO_MOVEMENT
            if r_val is not None and r_val > 0
            else HypothesisDirectionEnum.NEGATIVE_CO_MOVEMENT
            if r_val is not None and r_val < 0
            else HypothesisDirectionEnum.INCONCLUSIVE
        )

        hypotheses = [
            StructuredHypothesis(
                variable=EnvironmentalVariableEnum.SST,
                mechanism="thermal_suitability_and_coastal_upwelling",
                direction=direction,
                status=HypothesisStatusEnum.UNTESTED_HYPOTHESIS,
                caveat=(
                    "Annual mean SST does not resolve seasonal upwelling cooling, marine heatwaves, "
                    "or thermal front dynamics that govern pelagic schooling behaviour."
                ),
            ),
            StructuredHypothesis(
                variable=EnvironmentalVariableEnum.CHLOROPHYLL,
                mechanism="trophic_food_web_and_larval_food_availability",
                direction=direction,
                status=HypothesisStatusEnum.UNTESTED_HYPOTHESIS,
                caveat=(
                    "Chlorophyll-a is an indirect proxy for phytoplankton biomass and does not track "
                    "zooplankton abundance, species feeding preferences, or trophic timing matches."
                ),
            ),
        ]

        extra_context = {
            "aligned": aligned,
            "ci": ci_val,
            "reason_code": reason_code,
            "scenario_section": scenario_section,
            "trajectories": trajectories,
        }

        return bundle, hypotheses, extra_context
