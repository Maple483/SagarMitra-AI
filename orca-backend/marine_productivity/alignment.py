"""
Temporal year-key alignment module.
Performs key-based inner joins on integer calendar years, handles lag shifting
(environment in year y leading catch in year y+k), and computes consecutive-year differencing.
Zero array index slicing is permitted.
"""

from typing import Dict, List, Tuple, Optional
import numpy as np


class TemporalAlignmentResult:
    def __init__(
        self,
        x_values: np.ndarray,
        y_values: np.ndarray,
        matched_years: List[Tuple[int, int]],
        n_paired: int,
        n_valid: int,
    ):
        self.x_values = x_values
        self.y_values = y_values
        self.matched_years = matched_years
        self.n_paired = n_paired
        self.n_valid = n_valid


class DifferencedAlignmentResult:
    def __init__(
        self,
        dx_values: np.ndarray,
        dy_values: np.ndarray,
        matched_diff_years: List[Tuple[int, int]],
        n_difference_pairs: int,
    ):
        self.dx_values = dx_values
        self.dy_values = dy_values
        self.matched_diff_years = matched_diff_years
        self.n_difference_pairs = n_difference_pairs


def align_lagged_series(
    env_dict: Dict[int, float],
    catch_dict: Dict[int, float],
    lag_years: int = 1,
) -> TemporalAlignmentResult:
    """
    Performs an explicit key-based temporal join where environment in year y leads
    catch in year y + lag_years.
    Pairs (env[y], catch[y + lag_years]) are constructed only when both keys exist.
    Finite cleaning removes NaN/Inf values.
    """
    if lag_years < 0:
        raise ValueError(f"Negative lag ({lag_years}) is not supported. Catch cannot precede environment.")

    matched_pairs: List[Tuple[int, int, float, float]] = []
    # Sorted environmental years
    for env_yr in sorted(env_dict.keys()):
        catch_yr = env_yr + lag_years
        if catch_yr in catch_dict:
            matched_pairs.append(
                (env_yr, catch_yr, env_dict[env_yr], catch_dict[catch_yr])
            )

    n_paired = len(matched_pairs)

    valid_x: List[float] = []
    valid_y: List[float] = []
    valid_years: List[Tuple[int, int]] = []

    for env_yr, catch_yr, val_x, val_y in matched_pairs:
        if (
            val_x is not None
            and val_y is not None
            and np.isfinite(val_x)
            and np.isfinite(val_y)
        ):
            valid_x.append(float(val_x))
            valid_y.append(float(val_y))
            valid_years.append((env_yr, catch_yr))

    n_valid = len(valid_x)
    return TemporalAlignmentResult(
        x_values=np.array(valid_x, dtype=np.float64),
        y_values=np.array(valid_y, dtype=np.float64),
        matched_years=valid_years,
        n_paired=n_paired,
        n_valid=n_valid,
    )


def compute_consecutive_differences(
    data_dict: Dict[int, float]
) -> Dict[int, float]:
    """
    Computes delta_X[y] = X[y] - X[y - 1] strictly evaluated if and only if
    the preceding calendar year (y - 1) is present in the series.
    Missing-year transitions (e.g. 2008 -> 2010) are cleanly omitted, preventing
    two-year variance from masquerading as a one-year step.
    """
    diff_dict: Dict[int, float] = {}
    for yr in sorted(data_dict.keys()):
        prev_yr = yr - 1
        if prev_yr in data_dict:
            curr_val = data_dict[yr]
            prev_val = data_dict[prev_yr]
            if (
                curr_val is not None
                and prev_val is not None
                and np.isfinite(curr_val)
                and np.isfinite(prev_val)
            ):
                diff_dict[yr] = float(curr_val - prev_val)
    return diff_dict


def align_differenced_series(
    env_dict: Dict[int, float],
    catch_dict: Dict[int, float],
    lag_years: int = 1,
) -> DifferencedAlignmentResult:
    """
    Computes first-difference series on each variable independently, then performs
    the lagged key join: Delta_E[y] against Delta_C[y + lag_years].
    """
    diff_env = compute_consecutive_differences(env_dict)
    diff_catch = compute_consecutive_differences(catch_dict)

    matched_dx: List[float] = []
    matched_dy: List[float] = []
    matched_years: List[Tuple[int, int]] = []

    for env_yr in sorted(diff_env.keys()):
        catch_yr = env_yr + lag_years
        if catch_yr in diff_catch:
            dx = diff_env[env_yr]
            dy = diff_catch[catch_yr]
            if np.isfinite(dx) and np.isfinite(dy):
                matched_dx.append(dx)
                matched_dy.append(dy)
                matched_years.append((env_yr, catch_yr))

    n_diff = len(matched_dx)
    return DifferencedAlignmentResult(
        dx_values=np.array(matched_dx, dtype=np.float64),
        dy_values=np.array(matched_dy, dtype=np.float64),
        matched_diff_years=matched_years,
        n_difference_pairs=n_diff,
    )
