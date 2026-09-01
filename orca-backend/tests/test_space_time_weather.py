import pytest
from datetime import datetime, timezone, timedelta
from agents.weather_service import (
    weather_service, lerp_angle, circular_min_difference,
    compute_2d_vector_sog_and_cog, spherical_rhumb_distance_and_bearing
)
from agents.weather_schema import RouteWeatherRequest, RouteWaypoint, VesselProfile


def test_lerp_angle_shortest_path():
    """Verifies that circular interpolation across 360/0 boundary passes through 0 (North), not 180 (South)."""
    val = lerp_angle(350.0, 10.0, 0.5)
    assert val == 0.0 or val == 360.0


def test_circular_min_difference():
    """Verifies that angular minimum difference diff(350, 10) == 20.0 (Head sea), not 340.0."""
    diff = circular_min_difference(350.0, 10.0)
    assert diff == 20.0


def test_2d_vector_sog_and_cog():
    """Verifies 2D ground vector sum: V_ship (12kt @ 090 East) + V_current (3kt @ 000 North)."""
    sog_kt, cog_deg = compute_2d_vector_sog_and_cog(
        speed_through_water_kt=12.0,
        heading_deg=90.0,
        u_current_kt=0.0,   # Eastward current component = 0
        v_current_kt=3.0    # Northward current component = 3kt
    )
    # SOG = sqrt(12^2 + 3^2) = sqrt(153) ~ 12.37 kt
    assert 12.3 <= sog_kt <= 12.5
    # COG = atan2(12, 3) ~ 75.96 deg
    assert 75.0 <= cog_deg <= 77.0


def test_decoupled_wave_energy_scalar_interpolation():
    """Verifies opposing 2m wave height scalar interpolation does not cancel out to 0m."""
    h1, h2 = 2.0, 2.0
    h_interp = weather_service.interpolate_wave_energy(h1, h2, 0.5)
    assert h_interp == 2.0  # sqrt( (2^2 + 2^2)/2 ) = 2.0


def test_sheltered_harbor_detection():
    """Verifies harbor coordinates inside Mumbai Port return True for shelter check."""
    assert weather_service.is_in_sheltered_harbor(18.95, 72.85) is True
    assert weather_service.is_in_sheltered_harbor(15.00, 70.00) is False


def test_evaluate_route_trajectory():
    """Verifies trajectory space-time hazard evaluation along Mumbai -> Goa route."""
    now = datetime.now(timezone.utc)
    req = RouteWeatherRequest(
        waypoints=[
            RouteWaypoint(lat=18.95, lon=72.85),  # Mumbai
            RouteWaypoint(lat=15.45, lon=73.80)   # Goa
        ],
        vessel_profile=VesselProfile(
            vessel_id="PATROL-101",
            max_safe_wave_m=3.0,
            max_safe_wind_kt=30.0
        ),
        speed_through_water_kt=15.0,
        departure_time_utc=now
    )
    res = weather_service.evaluate_route_trajectory(req)
    assert res.status == "SUCCESS"
    assert len(res.trajectory_samples) > 0
    assert res.max_wind_kt > 0.0
    assert res.overall_hazard_level in ["LOW", "MODERATE", "HIGH", "SEVERE"]
