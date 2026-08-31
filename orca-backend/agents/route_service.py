import math
import re
from typing import Dict, Any, List, Tuple, Optional, Literal
from datetime import datetime
from pydantic import BaseModel

from agents.boundary_provider import haversine_km
from agents.pathfinder import (
    pathfinder,
    MaritimeHazard,
    PathfindingError,
    StartOnLandError,
    TargetOnLandError,
    StartOutsideEEZError,
    TargetOutsideEEZError,
    NoSafePathFoundError
)

KM_TO_NM = 0.539957  # 1 km = 0.539957 Nautical Miles


class Waypoint(BaseModel):
    lat: float
    lon: float
    name: str
    leg_distance_nm: float
    cumulative_distance_nm: float


class RouteSegment(BaseModel):
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    distance_nm: float
    bearing_deg: float
    nominal_ete_hours: float
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]


class RouteResponse(BaseModel):
    status: Literal["SUCCESS", "NO_PATH_FOUND", "INVALID_COORDINATES"]
    total_dist_km: float
    total_dist_nm: float
    nominal_ete_hours: float
    minimum_hazard_clearance_nm: float
    minimum_boundary_clearance_nm: float
    max_risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    waypoints: List[Waypoint]
    segments: List[RouteSegment]
    message: Optional[str] = None


def compute_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates initial forward compass bearing in degrees [0, 360)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_lon = math.radians(lon2 - lon1)
    y = math.sin(d_lon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lon)
    bearing = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return round(bearing, 1)


class RouteService:
    """
    Decouples LangGraph orchestration from pathfinding mechanics,
    parsing contextual map hazards and computing multi-segment risk telemetry.
    """

    def __init__(self):
        self.pathfinder = pathfinder

    def parse_hazards_from_context(self, context_text: Optional[str]) -> List[MaritimeHazard]:
        """Parses active wave alerts and coordinates from the system context string."""
        hazards = []
        if not context_text:
            return hazards

        # Match e.g. "Active Wave alert (4.5m swells) at Lat 16.0, Lng 71.0"
        wave_match = re.search(
            r'Wave alert.*?([\d\.]+)\s*m.*?Lat\s*([\d\.-]+).*?Lng\s*([\d\.-]+)',
            context_text,
            re.IGNORECASE
        )
        if wave_match:
            try:
                swell_m = float(wave_match.group(1))
                h_lat = float(wave_match.group(2))
                h_lon = float(wave_match.group(3))
                hazards.append(MaritimeHazard(
                    center_lat=h_lat,
                    center_lon=h_lon,
                    radius_km=80.0,
                    swell_height_m=swell_m,
                    hazard_type="wave_alert"
                ))
            except Exception:
                pass

        # Ingest active IMD cyclone and gale warning hazard zones
        try:
            from agents.imd_cyclone_service import imd_cyclone_service
            hazards.extend(imd_cyclone_service.get_cyclone_pathfinder_hazards())
        except Exception:
            pass

        return hazards

    def calculate_safe_route(
        self,
        start_coords: Dict[str, float],
        target_coords: Dict[str, float],
        system_context: Optional[str] = None
    ) -> RouteResponse:
        """
        Calculates the lowest-cost safe nautical path avoiding active hazards and boundaries.
        """
        start_lat = float(start_coords.get("lat", 0.0))
        start_lon = float(start_coords.get("lon", start_coords.get("lng", 0.0)))
        target_lat = float(target_coords.get("lat", 0.0))
        target_lon = float(target_coords.get("lon", target_coords.get("lng", 0.0)))

        hazards = self.parse_hazards_from_context(system_context)

        try:
            result = self.pathfinder.find_path(
                start_lat=start_lat,
                start_lon=start_lon,
                goal_lat=target_lat,
                goal_lon=target_lon,
                hazards=hazards
            )
        except (StartOnLandError, TargetOnLandError, StartOutsideEEZError, TargetOutsideEEZError) as e:
            return RouteResponse(
                status="INVALID_COORDINATES",
                total_dist_km=0.0,
                total_dist_nm=0.0,
                nominal_ete_hours=0.0,
                minimum_hazard_clearance_nm=0.0,
                minimum_boundary_clearance_nm=0.0,
                max_risk_level="HIGH",
                waypoints=[],
                segments=[],
                message=str(e)
            )
        except NoSafePathFoundError as e:
            return RouteResponse(
                status="NO_PATH_FOUND",
                total_dist_km=0.0,
                total_dist_nm=0.0,
                nominal_ete_hours=0.0,
                minimum_hazard_clearance_nm=0.0,
                minimum_boundary_clearance_nm=0.0,
                max_risk_level="HIGH",
                waypoints=[],
                segments=[],
                message=str(e)
            )

        coords = result["smoothed_coords"]
        total_km = result["total_dist_km"]
        total_nm = round(total_km * KM_TO_NM, 2)
        nominal_ete = round(total_nm / 10.0, 2)  # 10 knots nominal speed

        # Build Waypoints & Segments
        waypoints: List[Waypoint] = []
        segments: List[RouteSegment] = []
        cum_dist_nm = 0.0

        for i, (lat, lon) in enumerate(coords):
            leg_nm = 0.0
            if i > 0:
                p_prev = coords[i - 1]
                leg_km = haversine_km(p_prev[0], p_prev[1], lat, lon)
                leg_nm = round(leg_km * KM_TO_NM, 2)
                cum_dist_nm += leg_nm

                bearing = compute_bearing(p_prev[0], p_prev[1], lat, lon)
                seg_ete = round(leg_nm / 10.0, 2)

                # Segment risk evaluation based on proximity to hazards
                seg_risk: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
                for h in hazards:
                    mid_lat = (p_prev[0] + lat) / 2.0
                    mid_lon = (p_prev[1] + lon) / 2.0
                    dist_to_h = haversine_km(mid_lat, mid_lon, h.center_lat, h.center_lon)
                    if dist_to_h < (h.radius_km + 15.0):
                        seg_risk = "HIGH" if dist_to_h < h.radius_km else "MEDIUM"

                segments.append(RouteSegment(
                    start_lat=round(p_prev[0], 4),
                    start_lon=round(p_prev[1], 4),
                    end_lat=round(lat, 4),
                    end_lon=round(lon, 4),
                    distance_nm=leg_nm,
                    bearing_deg=bearing,
                    nominal_ete_hours=seg_ete,
                    risk_level=seg_risk
                ))

            w_name = "Start Departure" if i == 0 else ("Destination" if i == len(coords) - 1 else f"Waypoint {i}")
            waypoints.append(Waypoint(
                lat=round(lat, 4),
                lon=round(lon, 4),
                name=w_name,
                leg_distance_nm=leg_nm,
                cumulative_distance_nm=round(cum_dist_nm, 2)
            ))

        # Overall Minimum Hazard Clearance calculation
        min_hazard_clearance_km = float('inf')
        for lat, lon in coords:
            for h in hazards:
                d = haversine_km(lat, lon, h.center_lat, h.center_lon) - h.radius_km
                if d < min_hazard_clearance_km:
                    min_hazard_clearance_km = d

        if math.isinf(min_hazard_clearance_km):
            min_clearance_nm = 50.0
        else:
            min_clearance_nm = round(max(0.0, min_hazard_clearance_km * KM_TO_NM), 1)

        # Max risk level determination
        max_risk: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"
        for seg in segments:
            if seg.risk_level == "HIGH":
                max_risk = "HIGH"
                break
            elif seg.risk_level == "MEDIUM":
                max_risk = "MEDIUM"

        return RouteResponse(
            status="SUCCESS",
            total_dist_km=total_km,
            total_dist_nm=total_nm,
            nominal_ete_hours=nominal_ete,
            minimum_hazard_clearance_nm=min_clearance_nm,
            minimum_boundary_clearance_nm=12.0,
            max_risk_level=max_risk,
            waypoints=waypoints,
            segments=segments
        )


# Global singleton instance
route_service = RouteService()
