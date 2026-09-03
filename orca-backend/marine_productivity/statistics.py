"""
Pure statistical engine for marine environmental and fisheries analysis.
Implements robust Pearson correlation, nominal survival p-values, N >= 4 Fisher CI,
constant series detection, within-series autocorrelation, and diagnostic N_eff.
"""

import math
from typing import Optional, Tuple, Dict, Any
import numpy as np
from scipy import stats

from .schemas import (
    ConfidenceInterval,
    CIStatusEnum,
    PValueStatusEnum,
    AutocorrelationStatusEnum,
)


class NumericalComputationError(ValueError):
    pass


def is_effectively_constant(
    arr: np.ndarray, scale_eps: float = 1e-7, abs_floor: float = 1e-12
) -> bool:
    """
    Detects whether an array has effectively zero variance relative to its scale.
    Uses scale_eps * mean(|x|) + abs_floor to remain scale-invariant across
    variables with different physical units (e.g. tonnes vs mg/m3).
    """
    if len(arr) == 0:
        return True
    mean_abs = float(np.mean(np.abs(arr)))
    std_val = float(np.std(arr, ddof=0))
    return std_val < (scale_eps * mean_abs + abs_floor)


def compute_sample_lag1_autocorrelation(arr: np.ndarray) -> Optional[float]:
    """
    Computes within-series sample lag-1 autocorrelation:
    rho_1 = Corr(X_2 ... X_N, X_1 ... X_N-1).
    Returns None if N < 4 or if either slice has zero variance.
    """
    if len(arr) < 4:
        return None
    x_lead = arr[1:]
    x_lag = arr[:-1]
    if is_effectively_constant(x_lead) or is_effectively_constant(x_lag):
        return None

    x_lead_dev = x_lead - np.mean(x_lead)
    x_lag_dev = x_lag - np.mean(x_lag)
    denom = math.sqrt(float(np.sum(x_lead_dev**2) * np.sum(x_lag_dev**2)))
    if denom < 1e-15:
        return None
    r = float(np.sum(x_lead_dev * x_lag_dev) / denom)
    return max(-1.0, min(1.0, r))


def compute_pearson_correlation(
    x: np.ndarray, y: np.ndarray
) -> Tuple[Optional[float], Optional[float], PValueStatusEnum, ConfidenceInterval]:
    """
    Calculates Pearson's product-moment correlation on paired arrays:
    r = sum((x - x_bar)(y - y_bar)) / sqrt(sum((x - x_bar)^2) * sum((y - y_bar)^2))

    Returns (r, nominal_p_value, p_value_status, confidence_interval).
    """
    n = len(x)
    if n < 3:
        ci_insufficient = ConfidenceInterval(
            lower=None,
            upper=None,
            confidence_level=0.95,
            method="NONE",
            status=CIStatusEnum.INSUFFICIENT_SAMPLE_FOR_CI,
        )
        return None, None, PValueStatusEnum.INSUFFICIENT_SAMPLE, ci_insufficient

    if is_effectively_constant(x) or is_effectively_constant(y):
        ci_const = ConfidenceInterval(
            lower=None,
            upper=None,
            confidence_level=0.95,
            method="NONE",
            status=CIStatusEnum.INSUFFICIENT_SAMPLE_FOR_CI,
        )
        return None, None, PValueStatusEnum.CONSTANT_SERIES, ci_const

    x_dev = x - np.mean(x)
    y_dev = y - np.mean(y)
    ss_xx = float(np.sum(x_dev**2))
    ss_yy = float(np.sum(y_dev**2))
    ss_xy = float(np.sum(x_dev * y_dev))

    denom = math.sqrt(ss_xx * ss_yy)
    if denom < 1e-15:
        ci_const = ConfidenceInterval(
            lower=None,
            upper=None,
            confidence_level=0.95,
            method="NONE",
            status=CIStatusEnum.INSUFFICIENT_SAMPLE_FOR_CI,
        )
        return None, None, PValueStatusEnum.CONSTANT_SERIES, ci_const

    r_raw = ss_xy / denom

    if abs(r_raw) > 1.0 + 1e-5:
        raise NumericalComputationError(
            f"Calculated Pearson r ({r_raw}) exceeds theoretical bounds [-1, 1]"
        )

    r_bounded = max(-1.0, min(1.0, r_raw))

    # Perfect correlation boundary condition
    if abs(r_bounded) >= 1.0 - 1e-7:
        sign_val = 1.0 if r_bounded >= 0 else -1.0
        ci_perfect = ConfidenceInterval(
            lower=sign_val * 1.0,
            upper=sign_val * 1.0,
            confidence_level=0.95,
            method="DEGENERATE_PERFECT_CORRELATION_BOUNDARY",
            status=CIStatusEnum.PERFECT_CORRELATION,
        )
        return r_bounded, 0.0, PValueStatusEnum.PERFECT_CORRELATION, ci_perfect

    # Student's t test statistic
    df = n - 2
    t_stat = r_bounded * math.sqrt(df / (1.0 - r_bounded**2))
    # Two-tailed p-value using survival function for numerical precision
    p_val = float(2.0 * stats.t.sf(abs(t_stat), df=df))

    # Fisher's z Confidence Interval (strictly N >= 4)
    if n < 4:
        ci_result = ConfidenceInterval(
            lower=None,
            upper=None,
            confidence_level=0.95,
            method="FISHER_Z_GUARDED_N_LT_4",
            status=CIStatusEnum.INSUFFICIENT_SAMPLE_FOR_CI,
        )
    else:
        z = math.atanh(r_bounded)
        se_z = 1.0 / math.sqrt(n - 3)
        ci_lower = math.tanh(z - 1.96 * se_z)
        ci_upper = math.tanh(z + 1.96 * se_z)
        ci_result = ConfidenceInterval(
            lower=float(ci_lower),
            upper=float(ci_upper),
            confidence_level=0.95,
            method="FISHER_Z",
            status=CIStatusEnum.VALID,
        )

    return r_bounded, p_val, PValueStatusEnum.VALID, ci_result


def compute_diagnostic_neff(
    x: np.ndarray, y: np.ndarray
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], AutocorrelationStatusEnum]:
    """
    Computes diagnostic Chelton/Pyper effective sample size based on within-series
    lag-1 autocorrelation:
    N_eff = max(3.0, min(N, N * (1 - rho_X * rho_Y) / (1 + rho_X * rho_Y)))

    Returns (rho_x, rho_y, rho_product, n_eff, autocorrelation_status).
    """
    n = len(x)
    if n < 4:
        return None, None, None, None, AutocorrelationStatusEnum.INSUFFICIENT_SAMPLE

    rho_x = compute_sample_lag1_autocorrelation(x)
    rho_y = compute_sample_lag1_autocorrelation(y)

    if rho_x is None or rho_y is None:
        return None, None, None, None, AutocorrelationStatusEnum.INSUFFICIENT_SAMPLE

    rho_product = float(rho_x * rho_y)

    # Denominator instability guard: if 1 + rho_X * rho_Y approx 0
    if abs(1.0 + rho_product) < 1e-5 or rho_product < -0.999:
        return rho_x, rho_y, rho_product, None, AutocorrelationStatusEnum.UNSTABLE

    raw_neff = n * (1.0 - rho_product) / (1.0 + rho_product)
    neff_bounded = float(max(3.0, min(float(n), raw_neff)))
    return rho_x, rho_y, rho_product, neff_bounded, AutocorrelationStatusEnum.VALID


def compute_descriptive_first_difference_r(
    dx: np.ndarray, dy: np.ndarray
) -> Optional[float]:
    """
    Computes descriptive first-difference correlation r_delta across aligned
    1-year step changes. Requires at least 3 difference pairs and non-constant variance.
    """
    if len(dx) < 3:
        return None
    if is_effectively_constant(dx) or is_effectively_constant(dy):
        return None

    dx_dev = dx - np.mean(dx)
    dy_dev = dy - np.mean(dy)
    denom = math.sqrt(float(np.sum(dx_dev**2) * np.sum(dy_dev**2)))
    if denom < 1e-15:
        return None

    r_diff = float(np.sum(dx_dev * dy_dev) / denom)
    return max(-1.0, min(1.0, r_diff))
