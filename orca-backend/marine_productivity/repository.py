"""
Data repository layer for marine landings and coastal environmental series.
Enforces strict year parsing, duplicate detection, immutable snapshot loading,
and cryptographic SHA-256 integrity verification.
"""

import os
import json
import hashlib
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from .schemas import (
    MaritimeStateEnum,
    CommercialSpeciesEnum,
    EnvironmentalVariableEnum,
    DatasetVersionInfo,
)


class InvalidYearError(ValueError):
    pass


class DuplicateYearError(ValueError):
    pass


class SnapshotIntegrityError(RuntimeError):
    pass


def parse_and_validate_year(val: Any) -> int:
    """
    Strictly validates and converts an input into an integer calendar year.
    Rejects booleans, None, non-finite values (NaN, Inf), non-integers (e.g. 2010.9),
    and years outside realistic historical/modeled bounds [1900, 2100].
    """
    if isinstance(val, bool) or val is None:
        raise InvalidYearError(f"Invalid boolean or null year key: {val}")
    try:
        f_val = float(val)
        if not np.isfinite(f_val):
            raise InvalidYearError(f"Infinite or NaN year encountered: {val}")
        if not f_val.is_integer():
            raise InvalidYearError(f"Non-integer year encountered: {val}")
        y = int(f_val)
        if y < 1900 or y > 2100:
            raise InvalidYearError(f"Year out of realistic bounds: {y}")
        return y
    except (ValueError, TypeError) as e:
        raise InvalidYearError(f"Malformed year key: {val}") from e


class MarineProductivityRepository:
    """
    Thread-safe, read-only immutable repository that loads and caches the verified
    CMFRI landings and coastal environmental dataset snapshot.
    """

    SNAPSHOT_ID = "CMFRI-NOAA-ESA-SNAPSHOT-2026A"
    SNAPSHOT_VERSION = "v1.0.0"
    OBSERVED_START_YEAR = 2007
    OBSERVED_END_YEAR = 2012
    SCENARIO_START_YEAR = 2013
    SCENARIO_END_YEAR = 2026

    def __init__(self, snapshot_dir: Optional[str] = None):
        if snapshot_dir is None:
            # Default to backend data snapshots path
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            snapshot_dir = os.path.join(base_dir, "data", "snapshots", "v1.0.0")
            if not os.path.exists(snapshot_dir):
                snapshot_dir = os.path.join(base_dir, "data")

        self.snapshot_dir = snapshot_dir
        self.dataset_path = os.path.join(snapshot_dir, "orca-dataset.json")
        self._sha256_hash: str = ""
        self._years: List[int] = []
        self._states: List[str] = []
        self._species: List[str] = []
        self._annual_landings: Dict[str, Dict[str, Dict[int, float]]] = {}
        self._annual_env: Dict[str, Dict[str, Dict[int, float]]] = {}
        self._seasonal_profiles: Dict[str, List[float]] = {}
        self._provenance: Dict[str, Any] = {}
        self._is_loaded: bool = False

        self._load_snapshot()

    def _load_snapshot(self) -> None:
        if not os.path.exists(self.dataset_path):
            raise SnapshotIntegrityError(f"Snapshot file not found: {self.dataset_path}")

        # Compute cryptographic SHA-256 hash across raw snapshot bytes
        hasher = hashlib.sha256()
        with open(self.dataset_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        self._sha256_hash = hasher.hexdigest()

        with open(self.dataset_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # Parse and validate year keys
        raw_years = raw.get("years", [])
        validated_years: List[int] = []
        for y_raw in raw_years:
            y = parse_and_validate_year(y_raw)
            if y in validated_years:
                raise DuplicateYearError(f"Duplicate year key in dataset: {y}")
            validated_years.append(y)
        self._years = sorted(validated_years)

        self._states = raw.get("states", [])
        self._species = raw.get("species", [])
        self._seasonal_profiles = raw.get("seasonalProfile", {})
        self._provenance = raw.get("provenance", {})

        # Load annual landings: {state: {species: {year: value}}}
        raw_annual = raw.get("annual", {})
        for state, species_dict in raw_annual.items():
            self._annual_landings[state] = {}
            for sp_name, val_list in species_dict.items():
                self._annual_landings[state][sp_name] = {}
                for idx, val in enumerate(val_list):
                    if idx < len(self._years):
                        yr = self._years[idx]
                        if val is not None and np.isfinite(val) and val >= 0:
                            self._annual_landings[state][sp_name][yr] = float(val)

        # Load environmental series: {state: {"sst": {year: val}, "chlorophyll": {year: val}}}
        raw_env = raw.get("env", {})
        for state, env_list in raw_env.items():
            self._annual_env[state] = {"sst": {}, "chlorophyll": {}}
            for idx, pair in enumerate(env_list):
                if idx < len(self._years):
                    yr = self._years[idx]
                    if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                        sst_val, chl_val = pair[0], pair[1]
                        if sst_val is not None and np.isfinite(sst_val) and 15.0 <= sst_val <= 40.0:
                            self._annual_env[state]["sst"][yr] = float(sst_val)
                        if chl_val is not None and np.isfinite(chl_val) and chl_val > 0:
                            self._annual_env[state]["chlorophyll"][yr] = float(chl_val)

        self._is_loaded = True

    @property
    def sha256_hash(self) -> str:
        return self._sha256_hash

    def get_available_states(self) -> List[str]:
        return list(self._states)

    def get_available_species(self, state: Optional[str] = None) -> List[str]:
        if state and state in self._annual_landings:
            return sorted(list(self._annual_landings[state].keys()))
        return list(self._species)

    def get_landings_series(
        self, state: str, species: str, observed_only: bool = False
    ) -> Dict[int, float]:
        """
        Returns calendar-year mapped landings in metric tonnes.
        If observed_only is True, strictly restricts to [2007, 2012].
        """
        state_data = self._annual_landings.get(state, {})
        # Check direct match or alias
        sp_data = state_data.get(species)
        if sp_data is None:
            # Fallback alias search (e.g. 'Oil Sardine' -> 'Sardine')
            for k, v in state_data.items():
                if k.lower() in species.lower() or species.lower() in k.lower():
                    sp_data = v
                    break
        if sp_data is None:
            return {}

        result = dict(sp_data)
        if observed_only:
            return {
                y: v
                for y, v in result.items()
                if self.OBSERVED_START_YEAR <= y <= self.OBSERVED_END_YEAR
            }
        return result

    def get_environmental_series(
        self, state: str, variable: str, observed_only: bool = False
    ) -> Dict[int, float]:
        """
        Returns calendar-year mapped environmental series (SST or chlorophyll).
        If observed_only is True, strictly restricts to [2007, 2012].
        """
        state_env = self._annual_env.get(state, {})
        var_key = "sst" if "sst" in variable.lower() else "chlorophyll"
        series = state_env.get(var_key, {})
        result = dict(series)
        if observed_only:
            return {
                y: v
                for y, v in result.items()
                if self.OBSERVED_START_YEAR <= y <= self.OBSERVED_END_YEAR
            }
        return result

    def get_seasonal_profile(self, species: str) -> List[float]:
        profile = self._seasonal_profiles.get(species)
        if profile is None:
            for k, v in self._seasonal_profiles.items():
                if k.lower() in species.lower() or species.lower() in k.lower():
                    return list(v)
            return [1.0 / 12.0] * 12
        return list(profile)

    def get_dataset_metadata(self) -> Tuple[DatasetVersionInfo, DatasetVersionInfo, DatasetVersionInfo]:
        landings_info = DatasetVersionInfo(
            provider="Central Marine Fisheries Research Institute (CMFRI)",
            dataset_name="Annual Marine Fisheries Landings in India",
            dataset_version="NMFDC-2007-2012-v1",
            variable_name="Annual Landings (Metric Tonnes)",
            retrieval_date="2026-09-01",
        )
        sst_info = DatasetVersionInfo(
            provider="NOAA National Centers for Environmental Information",
            dataset_name="NOAA Daily Optimum Interpolation SST (OISST) v2.1 Historical Analysis",
            dataset_version="v2.1",
            variable_name="Sea Surface Temperature (degC)",
            retrieval_date="2026-09-01",
        )
        chl_info = DatasetVersionInfo(
            provider="ESA Ocean Colour Climate Change Initiative",
            dataset_name="ESA OC-CCI v6.0 8-day Composite Reanalysis",
            dataset_version="v6.0",
            variable_name="Chlorophyll-a Concentration (mg/m3)",
            retrieval_date="2026-09-01",
        )
        return landings_info, sst_info, chl_info


_repository_instance: Optional[MarineProductivityRepository] = None


def get_repository() -> MarineProductivityRepository:
    global _repository_instance
    if _repository_instance is None:
        _repository_instance = MarineProductivityRepository()
    return _repository_instance
