from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum


class HazardLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"
    UNKNOWN = "UNKNOWN"


class VesselType(str, Enum):
    FISHING = "fishing"
    CARGO = "cargo"
    PATROL = "patrol"
    PASSENGER = "passenger"


class WeatherWarning(BaseModel):
    warning_id: str
    source: str                 # "IMD" | "INCOIS" | "OPEN-METEO"
    warning_type: str           # "CYCLONE" | "GALE_WIND" | "HIGH_WAVE" | "UNSTRUCTURED_TEXT"
    severity: str               # "RED_WARNING" | "ORANGE_ALERT" | "YELLOW_WATCH"
    issued_at_utc: datetime
    valid_from_utc: datetime
    valid_until_utc: datetime
    geometry: Dict[str, Any]    # GeoJSON Polygon
    description: str
    parse_confidence: float = 1.0


class ProvenanceMetadata(BaseModel):
    atmospheric_source: str
    marine_source: str
    issued_at_utc: Optional[datetime] = None
    observed_at_utc: Optional[datetime] = None
    ingested_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_from_utc: datetime
    valid_until_utc: datetime
    completeness: str = "FULL"         # "FULL" | "PARTIAL"
    freshness: str = "FRESH"           # "FRESH" | "STALE"
    spatial_quality: str = "DIRECT"    # "DIRECT" | "INTERPOLATED" | "NEAREST_MARINE" | "COASTAL_SHELTERED"


class WindMetrics(BaseModel):
    speed_kt: float
    gust_kt: float
    direction_deg: float


class WaveMetrics(BaseModel):
    wave_height_m: Optional[float] = None
    swell_height_m: Optional[float] = None
    wave_direction_deg: Optional[float] = None
    wave_period_s: Optional[float] = None


class CurrentMetrics(BaseModel):
    speed_kt: float
    direction_deg: float
    u_current_kt: float
    v_current_kt: float


class CommonWeatherState(BaseModel):
    lat: float
    lon: float
    timestamp_utc: datetime
    data_type: str = "forecast"         # "forecast" | "observation"
    wind: WindMetrics
    waves: WaveMetrics
    currents: Optional[CurrentMetrics] = None
    is_cross_sea: bool = False
    air_temp_c: Optional[float] = None
    sea_surface_temp_c: Optional[float] = None
    pressure_hpa: Optional[float] = None
    incois_pfz_advisory: Optional[Dict[str, Any]] = None
    provenance: ProvenanceMetadata


class RouteWaypoint(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    eta_utc: Optional[datetime] = None


class VesselProfile(BaseModel):
    vessel_id: str = "ORCA-VESSEL-1"
    vessel_type: VesselType = VesselType.PATROL
    vessel_length_m: float = 24.0
    max_safe_wave_m: float = 3.0
    max_safe_wind_kt: float = 30.0
    max_safe_gust_kt: float = 40.0


class RouteWeatherRequest(BaseModel):
    waypoints: List[RouteWaypoint] = Field(..., min_length=2, max_length=100)
    vessel_profile: VesselProfile = Field(default_factory=VesselProfile)
    speed_through_water_kt: float = Field(15.0, gt=0, le=50)
    departure_time_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TrajectoryPointWeather(BaseModel):
    lat: float
    lon: float
    eta_utc: datetime
    sog_kt: float
    cog_deg: float
    encounter_angle_deg: float
    encounter_type: str                 # "HEAD_SEA" | "BEAM_SEA" | "FOLLOWING_SEA" | "QUARTERING_SEA"
    is_cross_sea: bool = False
    weather: CommonWeatherState
    segment_hazard_level: HazardLevel


class RouteWeatherResponse(BaseModel):
    status: str                         # "SUCCESS" | "DEGRADED"
    overall_hazard_level: HazardLevel
    max_wave_m: Optional[float] = None
    max_risk_adjusted_wave_index: Optional[float] = None
    max_wind_kt: float = 0.0
    duration_wave_exceeded_hours: float = 0.0
    duration_wind_exceeded_hours: float = 0.0
    cumulative_exposure_index: float = 0.0
    cross_sea_warnings_count: int = 0
    trajectory_samples: List[TrajectoryPointWeather] = Field(default_factory=list)
    active_route_warnings: List[WeatherWarning] = Field(default_factory=list)
