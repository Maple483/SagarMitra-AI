import csv
import math
import os
from typing import Dict, Any, Optional

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c

def find_nearest_pfz(lat: float, lon: float) -> Optional[Dict[str, Any]]:
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
                if d < min_distance:
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

