"""
Scenario trajectory engine for environmental projections (2013-2026).
Generates anchored deterministic sensitivity trajectories for SST warming
and compounded chlorophyll decline, with explicit physical sanity bounds
and missing 2012 anchor guardrails.
"""

from typing import Dict, Optional, Tuple
from .schemas import (
    ScenarioStatusEnum,
    ScenarioNameEnum,
    ScenarioTrajectorySection,
)


class ScenarioTrajectoryEngine:
    SCENARIO_ID = "ORCA-SCENARIO-2026A"
    SCENARIO_VERSION = "v1.0.0"
    START_YEAR = 2013
    END_YEAR = 2026
    PARAMETER_SOURCE = "Configured deterministic sensitivity scenarios (unfitted to 6-year baseline)"

    SST_RATES: Dict[ScenarioNameEnum, float] = {
        ScenarioNameEnum.LOW_RATE: 0.01,
        ScenarioNameEnum.CENTRAL_RATE: 0.02,
        ScenarioNameEnum.HIGH_RATE: 0.03,
    }

    CHL_RATES: Dict[ScenarioNameEnum, float] = {
        ScenarioNameEnum.LOW_RATE: -0.8,
        ScenarioNameEnum.CENTRAL_RATE: -1.5,
        ScenarioNameEnum.HIGH_RATE: -2.5,
    }

    @classmethod
    def generate_scenario_section(
        cls,
        anchor_sst_2012: Optional[float],
        anchor_chl_2012: Optional[float],
        n_observed_years: int = 6,
    ) -> Tuple[ScenarioTrajectorySection, Dict[str, Dict[str, Dict[int, float]]]]:
        """
        Builds the ScenarioTrajectorySection and returns calculated trajectory series:
        {"sst": {rate_name: {year: val}}, "chlorophyll": {rate_name: {year: val}}}
        """
        n_modeled = cls.END_YEAR - cls.START_YEAR + 1  # 14 years
        n_total = n_observed_years + n_modeled
        modeled_pct = round((n_modeled / n_total) * 100.0, 1)

        # Check anchor availability
        if anchor_sst_2012 is None or anchor_chl_2012 is None:
            section = ScenarioTrajectorySection(
                scenario_id=cls.SCENARIO_ID,
                scenario_version=cls.SCENARIO_VERSION,
                scenario_status=ScenarioStatusEnum.UNAVAILABLE_MISSING_2012_ANCHOR,
                scenario_start_year=cls.START_YEAR,
                scenario_end_year=cls.END_YEAR,
                parameter_source=cls.PARAMETER_SOURCE,
                n_modeled=n_modeled,
                n_total=n_total,
                modeled_fraction_pct=modeled_pct,
                sst_sensitivity_rates_c_per_year={
                    k.value: v for k, v in cls.SST_RATES.items()
                },
                chl_sensitivity_rates_pct_per_year={
                    k.value: v for k, v in cls.CHL_RATES.items()
                },
                scenario_disclaimer=(
                    "Environmental scenario trajectories are unavailable because the 2012 "
                    "observed baseline anchor is missing or incomplete."
                ),
            )
            return section, {"sst": {}, "chlorophyll": {}}

        # Generate anchored trajectories
        trajectories: Dict[str, Dict[str, Dict[int, float]]] = {
            "sst": {},
            "chlorophyll": {},
        }

        # SST Warming Scenarios
        for s_name, rate in cls.SST_RATES.items():
            trajectories["sst"][s_name.value] = {}
            for yr in range(cls.START_YEAR, cls.END_YEAR + 1):
                delta_yr = yr - 2012
                val = anchor_sst_2012 + rate * delta_yr
                # Physical ceiling guard
                val = min(val, 36.0)
                trajectories["sst"][s_name.value][yr] = round(val, 3)

        # Chlorophyll Compounded Scenarios
        decay_factors = {
            ScenarioNameEnum.LOW_RATE: 0.992,      # -0.8%
            ScenarioNameEnum.CENTRAL_RATE: 0.985,  # -1.5%
            ScenarioNameEnum.HIGH_RATE: 0.975,     # -2.5%
        }
        for s_name, factor in decay_factors.items():
            trajectories["chlorophyll"][s_name.value] = {}
            for yr in range(cls.START_YEAR, cls.END_YEAR + 1):
                delta_yr = yr - 2012
                val = max(0.001, anchor_chl_2012 * (factor ** delta_yr))
                trajectories["chlorophyll"][s_name.value][yr] = round(val, 4)

        section = ScenarioTrajectorySection(
            scenario_id=cls.SCENARIO_ID,
            scenario_version=cls.SCENARIO_VERSION,
            scenario_status=ScenarioStatusEnum.AVAILABLE,
            scenario_start_year=cls.START_YEAR,
            scenario_end_year=cls.END_YEAR,
            parameter_source=cls.PARAMETER_SOURCE,
            n_modeled=n_modeled,
            n_total=n_total,
            modeled_fraction_pct=modeled_pct,
            sst_sensitivity_rates_c_per_year={
                k.value: v for k, v in cls.SST_RATES.items()
            },
            chl_sensitivity_rates_pct_per_year={
                k.value: v for k, v in cls.CHL_RATES.items()
            },
            scenario_disclaimer=(
                "Scenario trajectories (2013-2026) represent illustrative sensitivity assumptions "
                "anchored at 2012 observed endpoints. They do NOT constitute independent empirical "
                "evidence, validated climate models, or fisheries catch forecasts."
            ),
        )
        return section, trajectories
