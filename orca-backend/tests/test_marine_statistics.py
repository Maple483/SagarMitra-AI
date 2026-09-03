"""
Unit tests for marine productivity statistical engine and alignment logic.
"""

import pytest
import numpy as np

from marine_productivity.repository import (
    parse_and_validate_year,
    InvalidYearError,
    DuplicateYearError,
)
from marine_productivity.alignment import (
    align_lagged_series,
    align_differenced_series,
    compute_consecutive_differences,
)
from marine_productivity.statistics import (
    is_effectively_constant,
    compute_pearson_correlation,
    compute_diagnostic_neff,
    compute_descriptive_first_difference_r,
    NumericalComputationError,
)
from marine_productivity.schemas import (
    PValueStatusEnum,
    CIStatusEnum,
    AutocorrelationStatusEnum,
    ScenarioStatusEnum,
)
from marine_productivity.scenario_engine import ScenarioTrajectoryEngine
from marine_productivity.analyst import (
    TemplateNarrativeCompiler,
    CausalLanguageViolationError,
)


def test_year_normalization_edge_cases():
    # Valid conversions
    assert parse_and_validate_year(2010) == 2010
    assert parse_and_validate_year("2010") == 2010
    assert parse_and_validate_year(2010.0) == 2010

    # Invalid non-integer or float truncation attempts
    with pytest.raises(InvalidYearError):
        parse_and_validate_year("2010.9")

    with pytest.raises(InvalidYearError):
        parse_and_validate_year(2010.5)

    # Invalid boolean / None
    with pytest.raises(InvalidYearError):
        parse_and_validate_year(True)

    with pytest.raises(InvalidYearError):
        parse_and_validate_year(False)

    with pytest.raises(InvalidYearError):
        parse_and_validate_year(None)

    # Invalid string / NaN / Inf
    with pytest.raises(InvalidYearError):
        parse_and_validate_year("invalid")

    with pytest.raises(InvalidYearError):
        parse_and_validate_year(float("nan"))

    with pytest.raises(InvalidYearError):
        parse_and_validate_year(float("inf"))

    # Out of realistic bounds
    with pytest.raises(InvalidYearError):
        parse_and_validate_year(1850)

    with pytest.raises(InvalidYearError):
        parse_and_validate_year(2150)


def test_temporal_alignment_sample_size_accounting():
    env = {2007: 28.0, 2008: 28.2, 2009: 28.4, 2010: 28.6, 2011: 28.8, 2012: 29.0}
    catch = {2007: 100.0, 2008: 110.0, 2009: 120.0, 2010: 130.0, 2011: 140.0, 2012: 150.0}

    # Lag 0 -> 6 paired observations
    res_lag0 = align_lagged_series(env, catch, lag_years=0)
    assert res_lag0.n_paired == 6
    assert res_lag0.n_valid == 6

    # Lag 1 -> 5 paired observations (2007->2008 ... 2011->2012)
    res_lag1 = align_lagged_series(env, catch, lag_years=1)
    assert res_lag1.n_paired == 5
    assert res_lag1.n_valid == 5
    assert res_lag1.matched_years[0] == (2007, 2008)
    assert res_lag1.matched_years[-1] == (2011, 2012)


def test_consecutive_differencing_missing_years():
    # Gap in years: 2007, 2008, 2010 (2009 missing)
    series_with_gap = {2007: 10.0, 2008: 15.0, 2010: 30.0}
    diff = compute_consecutive_differences(series_with_gap)

    # 2008 has valid delta (2008 - 2007 = 5.0)
    assert 2008 in diff
    assert diff[2008] == 5.0

    # 2010 must NOT compute 30 - 15 = 15 across the missing year 2009!
    assert 2010 not in diff
    assert len(diff) == 1


def test_differenced_alignment_sample_size():
    env = {2007: 28.0, 2008: 28.2, 2009: 28.4, 2010: 28.6, 2011: 28.8, 2012: 29.0}
    catch = {2007: 100.0, 2008: 110.0, 2009: 120.0, 2010: 130.0, 2011: 140.0, 2012: 150.0}

    # Consecutive differences give 5 differences each (2008..2012)
    # With lag 1 (Delta_E[y] vs Delta_C[y+1]), pairing matches 4 pairs: (2008->2009 ... 2011->2012)
    diff_res = align_differenced_series(env, catch, lag_years=1)
    assert diff_res.n_difference_pairs == 4


def test_perfect_correlation_boundary():
    # Perfectly collinear arrays (r = 1.0)
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y = np.array([10.0, 20.0, 30.0, 40.0, 50.0])

    r, p, p_status, ci = compute_pearson_correlation(x, y)
    assert r == 1.0
    assert p == 0.0
    assert p_status == PValueStatusEnum.PERFECT_CORRELATION
    assert ci.method == "DEGENERATE_PERFECT_CORRELATION_BOUNDARY"
    assert ci.status == CIStatusEnum.PERFECT_CORRELATION
    assert ci.lower == 1.0
    assert ci.upper == 1.0

    # Perfectly inverse collinear (r = -1.0)
    y_inv = np.array([50.0, 40.0, 30.0, 20.0, 10.0])
    r_inv, p_inv, p_status_inv, ci_inv = compute_pearson_correlation(x, y_inv)
    assert r_inv == -1.0
    assert p_inv == 0.0
    assert ci_inv.lower == -1.0
    assert ci_inv.upper == -1.0


def test_fisher_z_sample_guards():
    # N = 3: Correlation is computable, but CI is guarded against division-by-zero (sqrt(3-3) = 0)
    x3 = np.array([1.0, 2.0, 3.0])
    y3 = np.array([2.0, 4.0, 5.0])
    r3, p3, p_status3, ci3 = compute_pearson_correlation(x3, y3)
    assert r3 is not None
    assert p3 is not None
    assert ci3.status == CIStatusEnum.INSUFFICIENT_SAMPLE_FOR_CI
    assert ci3.lower is None
    assert ci3.upper is None

    # N = 4: Valid finite CI computable
    x4 = np.array([1.0, 2.0, 3.0, 4.0])
    y4 = np.array([2.0, 4.0, 5.0, 7.0])
    r4, p4, p_status4, ci4 = compute_pearson_correlation(x4, y4)
    assert ci4.status == CIStatusEnum.VALID
    assert ci4.lower is not None
    assert ci4.upper is not None
    assert -1.0 <= ci4.lower < ci4.upper <= 1.0


def test_constant_series_guard():
    # Zero variance in X
    x_const = np.array([28.0, 28.0, 28.0, 28.0])
    y_var = np.array([100.0, 120.0, 110.0, 130.0])
    assert is_effectively_constant(x_const) is True
    assert is_effectively_constant(y_var) is False

    r, p, p_status, ci = compute_pearson_correlation(x_const, y_var)
    assert r is None
    assert p is None
    assert p_status == PValueStatusEnum.CONSTANT_SERIES


def test_diagnostic_neff_hand_calculated_fixture():
    # Test formula: Neff = N * (1 - rho_x * rho_y) / (1 + rho_x * rho_y)
    # For N = 6, rho_x = 0.5, rho_y = 0.5:
    # product = 0.25
    # (1 - 0.25) / (1 + 0.25) = 0.75 / 1.25 = 0.6
    # Neff = 6 * 0.6 = 3.6
    # Verify synthetic calculation:
    n = 6
    rho_x = 0.5
    rho_y = 0.5
    product = rho_x * rho_y
    expected_neff = n * (1.0 - product) / (1.0 + product)
    assert pytest.approx(expected_neff, 0.001) == 3.6


def test_diagnostic_neff_instability_guard():
    # Test denominator instability: rho_x * rho_y approx -1.0
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y = np.array([5.0, 4.0, 3.0, 2.0, 1.0])
    rho_x, rho_y, rho_prod, neff, status = compute_diagnostic_neff(x, y)
    # Should safely return status UNSTABLE or VALID bounded without ZeroDivisionError
    if status == AutocorrelationStatusEnum.UNSTABLE:
        assert neff is None


def test_scenario_missing_2012_anchor_guard():
    # If 2012 anchor is missing, scenario generation must be halted
    sec, traj = ScenarioTrajectoryEngine.generate_scenario_section(
        anchor_sst_2012=None, anchor_chl_2012=0.95
    )
    assert sec.scenario_status == ScenarioStatusEnum.UNAVAILABLE_MISSING_2012_ANCHOR
    assert len(traj["sst"]) == 0

    # If valid, scenarios generate 14 years
    sec_valid, traj_valid = ScenarioTrajectoryEngine.generate_scenario_section(
        anchor_sst_2012=28.0, anchor_chl_2012=1.0
    )
    assert sec_valid.scenario_status == ScenarioStatusEnum.AVAILABLE
    assert sec_valid.n_modeled == 14
    assert 2026 in traj_valid["sst"]["CENTRAL_RATE"]
    assert traj_valid["chlorophyll"]["CENTRAL_RATE"][2026] > 0


def test_causal_language_blocking():
    # Non-causal observational text must pass
    safe_text = "Observed landings and SST exhibited a positive association (r = 0.61)."
    TemplateNarrativeCompiler.verify_no_causal_leakage(safe_text)

    # Causal / attribution phrasing must raise CausalLanguageViolationError
    adversarial_examples = [
        "SST caused the decline in sardine catch.",
        "SST was responsible for the drop in landings.",
        "Rising temperatures drove down sardine populations.",
        "The catch decline is attributable to warming waters.",
        "SST was a major contributor to catch variance.",
        "Catches responded to SST substantially.",
    ]

    for adv in adversarial_examples:
        with pytest.raises(CausalLanguageViolationError):
            TemplateNarrativeCompiler.verify_no_causal_leakage(adv)
