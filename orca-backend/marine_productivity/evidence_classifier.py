"""
Heuristic analysis reliability tier classifier.
Applies product-defined rules to classify empirical evidence strictly on observed
analytical sample size (N_valid), effect magnitude (|r|), and nominal p-value.
"""

from typing import Optional, Tuple
from .schemas import (
    ReliabilityTierEnum,
    PValueStatusEnum,
)

SMALL_SAMPLE_MAX_N = 6


def classify_evidence_reliability(
    n_valid: int,
    pearson_r: Optional[float],
    nominal_p_value: Optional[float],
    p_value_status: PValueStatusEnum,
) -> Tuple[ReliabilityTierEnum, str]:
    """
    Classifies the observational association into a heuristic reliability tier.
    Returns (reliability_tier, tier_reason_code).
    """
    if n_valid < 3 or pearson_r is None:
        return (
            ReliabilityTierEnum.INSUFFICIENT_PAIRED_DATA,
            "INSUFFICIENT_VALID_PAIRS",
        )

    if p_value_status == PValueStatusEnum.CONSTANT_SERIES:
        return (
            ReliabilityTierEnum.UNDEFINED_ZERO_VARIANCE,
            "CONSTANT_SERIES",
        )

    # Inconclusive/weak if magnitude is below threshold or nominal p-value is high
    if abs(pearson_r) < 0.30 or (nominal_p_value is not None and nominal_p_value > 0.10):
        return (
            ReliabilityTierEnum.WEAK_OR_UNCERTAIN_ASSOCIATION,
            "WEAK_MAGNITUDE_OR_HIGH_P",
        )

    # Small-sample baseline (N <= 6)
    if n_valid <= SMALL_SAMPLE_MAX_N and abs(pearson_r) >= 0.30:
        return (
            ReliabilityTierEnum.EXPLORATORY_OBSERVATIONAL_BASELINE,
            "OBSERVATIONAL_SMALL_SAMPLE_BASELINE",
        )

    return (
        ReliabilityTierEnum.EXPLORATORY_OBSERVATIONAL_BASELINE,
        "OBSERVATIONAL_SMALL_SAMPLE_BASELINE",
    )
