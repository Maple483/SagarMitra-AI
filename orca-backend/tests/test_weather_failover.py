import pytest
from agents.weather_service import weather_service
from agents.imd_cyclone_service import imd_cyclone_service
from agents.route_service import route_service


def test_weather_service_telemetry_and_failover():
    """Verify live marine weather retrieval from Open-Meteo/INCOIS with valid telemetry."""
    # Test offshore Mumbai coordinate
    res = weather_service.fetch_live_marine_weather(18.9, 72.8)
    
    assert res["status"] == "SUCCESS"
    assert "telemetry" in res
    assert "wind_speed_kmh" in res["telemetry"]
    assert "wave_height_m" in res["telemetry"]
    assert "swell_height_m" in res["telemetry"]
    assert res["telemetry"]["wind_speed_kmh"] >= 0.0
    assert res["telemetry"]["wave_height_m"] >= 0.0
    
    # Assert data source metadata
    assert "system_metadata" in res
    assert res["system_metadata"]["tier"] in [1, 2, 3]
    assert "INCOIS" in res["system_metadata"]["data_source"] or "Open-Meteo" in res["system_metadata"]["data_source"] or "IMD" in res["system_metadata"]["data_source"]


def test_imd_cyclone_service_bulletins():
    """Verify IMD cyclone bulletins, gale warning polygons, and track projections."""
    bulletins = imd_cyclone_service.get_active_cyclones()
    assert len(bulletins) >= 1
    
    asna = next((b for b in bulletins if "Asna" in b["name"]), None)
    assert asna is not None
    assert asna["warning_level"] == "RED_WARNING"
    assert asna["max_sustained_winds_kmh"] >= 65.0
    assert len(asna["gale_warning_polygon"]) >= 4
    assert len(asna["predicted_track"]) >= 2
    assert "Total suspension of fishing operations" in asna["fishermen_warning_text"] or "IMD RED BULLETIN" in asna["fishermen_warning_text"]


def test_cyclone_pathfinder_hazard_generation():
    """Verify that IMD cyclone gale polygons are converted into A* pathfinding hazards."""
    hazards = imd_cyclone_service.get_cyclone_pathfinder_hazards()
    assert len(hazards) >= 1
    
    asna_hazard = next((h for h in hazards if "asna" in h.hazard_type), None)
    assert asna_hazard is not None
    assert asna_hazard.swell_height_m >= 4.0
    assert asna_hazard.radius_km >= 100.0


def test_cyclone_gale_hazard_route_avoidance():
    """Verify that A* pathfinding steers around active IMD cyclone gale envelopes."""
    # Start at Mumbai (18.9°N, 72.8°E) and Target at Okha/Kandla (22.5°N, 69.0°E) near the Asna gale zone
    resp = route_service.calculate_safe_route(
        start_coords={"lat": 18.9, "lon": 72.8},
        target_coords={"lat": 22.5, "lon": 69.0},
        system_context="Cyclone Warning Active"
    )
    
    assert resp.status == "SUCCESS"
    assert len(resp.waypoints) >= 2
    assert resp.total_dist_nm > 0
    # Minimum hazard clearance must be maintained
    assert resp.minimum_hazard_clearance_nm > 0
