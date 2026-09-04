import csv
import math
import os
from typing import Dict, Any, Optional, List, Tuple
from agents.weather_service import weather_service

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

def is_point_eligible_for_pfz(lat: float, lon: float) -> Tuple[bool, Optional[str]]:
    """
    Checks if a coordinate is eligible for Potential Fishing Zone (PFZ) advisory calculations.
    Strictly restricted to oceanic coordinates within the Indian Exclusive Economic Zone (EEZ).
    Inland landmasses and regions outside the Indian EEZ are strictly ineligible (no calculation).
    """
    if weather_service.is_on_landmass(lat, lon):
        return False, "INLAND_LANDMASS"
    if not weather_service.is_inside_indian_eez(lat, lon):
        return False, "OUTSIDE_INDIAN_EEZ"
    return True, None

def get_all_pfz_advisories() -> List[Dict[str, Any]]:
    """Returns all active INCOIS Potential Fishing Zones (PFZs) within the Indian EEZ."""
    csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "pfz_advisories.csv")
    if not os.path.exists(csv_path):
        return []
        
    zones = []
    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                pfz_lat = float(row["Latitude_Decimal"])
                pfz_lon = float(row["Longitude_Decimal"])
                zones.append({
                    "coast_name": row["From the coast of"],
                    "direction": row["Direction"],
                    "bearing_deg": float(row["Bearing (deg)"]),
                    "distance_km_range": row["Distance (km) From-To"],
                    "depth_mtr_range": row["Depth (mtr) From-To"],
                    "state": row["State"],
                    "validity": row["Forecast_Validity"],
                    "lat": pfz_lat,
                    "lon": pfz_lon
                })
            except Exception:
                continue
    return zones

def find_nearest_pfz(lat: float, lon: float, max_radius_km: float = 350.0) -> Optional[Dict[str, Any]]:
    """
    Finds the nearest INCOIS PFZ advisory to the given coordinates.
    Returns None if coordinate is on an inland landmass, outside the Indian EEZ,
    or further than max_radius_km.
    """
    eligible, _ = is_point_eligible_for_pfz(lat, lon)
    if not eligible:
        return None

    csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "pfz_advisories.csv")
    if not os.path.exists(csv_path):
        return None
        
    nearest_zone = None
    min_distance = float("inf")
    
    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                pfz_lat = float(row["Latitude_Decimal"])
                pfz_lon = float(row["Longitude_Decimal"])
                d = haversine_distance(lat, lon, pfz_lat, pfz_lon)
                if d < min_distance and d <= max_radius_km:
                    min_distance = d
                    nearest_zone = {
                        "coast_name": row["From the coast of"],
                        "direction": row["Direction"],
                        "bearing_deg": float(row["Bearing (deg)"]),
                        "distance_km_range": row["Distance (km) From-To"],
                        "depth_mtr_range": row["Depth (mtr) From-To"],
                        "state": row["State"],
                        "validity": row["Forecast_Validity"],
                        "lat": pfz_lat,
                        "lon": pfz_lon,
                        "distance_to_vessel_km": round(d, 2)
                    }
            except Exception:
                continue
                
    return nearest_zone

def find_nearest_pfz_with_status(lat: float, lon: float, max_radius_km: float = 350.0) -> Dict[str, Any]:
    """
    Detailed query method returning status metadata and suppression rationale
    when coordinates fall on an inland landmass or outside the Indian EEZ.
    """
    eligible, reason = is_point_eligible_for_pfz(lat, lon)
    if not eligible:
        message = (
            "Potential Fishing Zone (PFZ) advisory suppressed: Selected coordinates are located on an inland landmass. No calculation performed."
            if reason == "INLAND_LANDMASS" else
            "Potential Fishing Zone (PFZ) advisory suppressed: Selected coordinates are located outside the Indian Exclusive Economic Zone (EEZ). No calculation performed."
        )
        return {
            "status": "SUPPRESSED",
            "reason": reason,
            "message": message,
            "latitude": lat,
            "longitude": lon,
            "nearest_pfz": None
        }

    nearest = find_nearest_pfz(lat, lon, max_radius_km=max_radius_km)
    if not nearest:
        return {
            "status": "NOT_FOUND",
            "reason": "OUT_OF_RANGE",
            "message": f"No active INCOIS PFZ advisory located within {max_radius_km} km of the given position.",
            "latitude": lat,
            "longitude": lon,
            "nearest_pfz": None
        }

    return {
        "status": "SUCCESS",
        "latitude": lat,
        "longitude": lon,
        "nearest_pfz": nearest
    }

