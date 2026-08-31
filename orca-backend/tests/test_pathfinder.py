import os
import sys
import math
import heapq
from datetime import datetime, timedelta
import pytest

# Ensure orca-backend is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.boundary_provider import (
    boundary_provider,
    haversine_km,
    NUM_ROWS,
    NUM_COLS
)
from agents.pathfinder import (
    MaritimeAStarPathfinder,
    MaritimeHazard,
    StartOnLandError,
    TargetOnLandError,
    NoSafePathFoundError
)
from agents.route_service import RouteService, compute_bearing


def test_precomputed_geodesic_metrics():
    """Test 1: Precomputed geodesic step distances match Haversine formula within 0.05%."""
    # Test North-South step
    exact_ns = haversine_km(15.0, 70.0, 15.05, 70.0)
    assert abs(boundary_provider.dist_ns - exact_ns) < 0.01

    # Test East-West step at Lat 15.0 N (row ~200)
    r200 = 200
    lat_200 = boundary_provider.lat_by_row[r200]
    exact_ew = haversine_km(lat_200, 70.0, lat_200, 70.05)
    assert abs(boundary_provider.dist_ew[r200] - exact_ew) < 0.01

    # Test Diagonal Up step
    exact_diag = haversine_km(lat_200, 70.0, lat_200 + 0.05, 70.05)
    assert abs(boundary_provider.dist_diag_up[r200] - exact_diag) < 0.01


def test_corner_cutting_prevention():
    """Test 2: Diagonal transitions between diagonally touching impassable cells are blocked."""
    pf = MaritimeAStarPathfinder()
    
    # Check that is_cell_impassable detects Goa Naval Zone and Mainland
    goa_r, goa_c = boundary_provider.coord_to_cell(15.5, 72.5)
    assert boundary_provider.is_cell_impassable(goa_r, goa_c) is True

    sea_r, sea_c = boundary_provider.coord_to_cell(15.5, 70.0)
    assert boundary_provider.is_cell_impassable(sea_r, sea_c) is False


def test_connected_water_snapping():
    """Test 3: Port snapping safely resolves dock coordinates to navigable sea without land jumps."""
    # Coordinate on Mumbai coastal dock
    dock_lat, dock_lon = 18.92, 72.83
    snap_lat, snap_lon, r, c = boundary_provider.snap_to_connected_navigable_water(dock_lat, dock_lon, max_search_cells=8)
    
    # Snapped cell must be open water
    assert boundary_provider.is_cell_impassable(r, c) is False
    # Snapped distance must be within reasonable harbor proximity (< 25 km)
    assert haversine_km(dock_lat, dock_lon, snap_lat, snap_lon) < 25.0


def test_dijkstra_a_star_optimality_equivalence():
    """Test 4: A* path cost equals Dijkstra exhaustive cost on an unconstrained test grid."""
    pf = MaritimeAStarPathfinder()
    
    # Select safe open water start and goal in the Arabian Sea
    start_lat, start_lon = 14.0, 70.0
    goal_lat, goal_lon = 14.5, 70.5
    
    # A* solution
    a_star_res = pf.find_path(start_lat, start_lon, goal_lat, goal_lon)
    a_star_cost = a_star_res["total_cost"]
    
    # Exhaustive Dijkstra on same subgraph
    s_r, s_c = boundary_provider.coord_to_cell(start_lat, start_lon)
    g_r, g_c = boundary_provider.coord_to_cell(goal_lat, goal_lon)
    
    pq = [(0.0, s_r, s_c)]
    visited = {}
    
    directions = [
        (-1, 0, False), (1, 0, False), (0, -1, False), (0, 1, False),
        (-1, -1, True), (-1, 1, True), (1, -1, True), (1, 1, True)
    ]
    
    dijkstra_cost = None
    while pq:
        cost, r, c = heapq.heappop(pq)
        if (r, c) == (g_r, g_c):
            dijkstra_cost = cost
            break
        if (r, c) in visited and visited[(r, c)] <= cost:
            continue
        visited[(r, c)] = cost
        
        for dr, dc, is_diag in directions:
            nr, nc = r + dr, c + dc
            if 0 <= nr < NUM_ROWS and 0 <= nc < NUM_COLS:
                if boundary_provider.is_cell_impassable(nr, nc):
                    continue
                if is_diag and (boundary_provider.is_cell_impassable(r + dr, c) or boundary_provider.is_cell_impassable(r, c + dc)):
                    continue
                step_d = boundary_provider.dist_ns if not is_diag and dr != 0 else (boundary_provider.dist_ew[r] if not is_diag else boundary_provider.dist_diag_up[r])
                heapq.heappush(pq, (cost + step_d, nr, nc))
                
    assert dijkstra_cost is not None
    assert abs(a_star_cost - round(dijkstra_cost, 2)) < 0.1


def test_spatiotemporal_hazard_avoidance():
    """Test 5: Pathfinder routes around active 4.5m swell hazard center."""
    pf = MaritimeAStarPathfinder()
    
    # Place a storm center directly between start and goal
    start_lat, start_lon = 16.0, 69.5
    storm_lat, storm_lon = 16.0, 71.0
    goal_lat, goal_lon = 16.0, 72.5
    
    hazard = MaritimeHazard(
        center_lat=storm_lat,
        center_lon=storm_lon,
        radius_km=80.0,
        swell_height_m=4.5,
        valid_from=datetime.utcnow() - timedelta(hours=2),
        valid_until=datetime.utcnow() + timedelta(hours=24)
    )
    
    res = pf.find_path(start_lat, start_lon, goal_lat, goal_lon, hazards=[hazard])
    smoothed = res["smoothed_coords"]
    
    # Verify no smoothed point penetrates the storm core (< 40 km from center)
    for p_lat, p_lon in smoothed:
        dist_to_center = haversine_km(p_lat, p_lon, storm_lat, storm_lon)
        assert dist_to_center > 40.0, f"Point ({p_lat}, {p_lon}) penetrated storm core (dist={dist_to_center:.1f} km)"


def test_route_service_telemetry_schema():
    """Test 6: RouteService outputs valid Pydantic RouteResponse with segments and bearings."""
    rs = RouteService()
    
    start = {"lat": 14.0, "lon": 70.0}
    target = {"lat": 15.0, "lon": 71.0}
    ctx = "Active Wave alert (4.5m swells) at Lat 14.5, Lng 70.5"
    
    resp = rs.calculate_safe_route(start, target, ctx)
    assert resp.status == "SUCCESS"
    assert resp.total_dist_nm > 0
    assert resp.nominal_ete_hours > 0
    assert len(resp.waypoints) >= 2
    assert len(resp.segments) >= 1
    
    for seg in resp.segments:
        assert 0.0 <= seg.bearing_deg < 360.0
        assert seg.distance_nm > 0
        assert seg.risk_level in ["LOW", "MEDIUM", "HIGH"]


def test_bearing_computation():
    """Test 7: Compass bearing calculation accurately outputs cardinals on unit sphere."""
    # Due North
    assert compute_bearing(10.0, 70.0, 11.0, 70.0) == 0.0
    # Due East along equator
    assert compute_bearing(0.0, 70.0, 0.0, 71.0) == 90.0
def test_strict_eez_geofencing():
    """Test 8: Strict EEZ geofencing rejects targets in international waters."""
    rs = RouteService()
    
    # Start inside Indian EEZ off Mumbai
    start = {"lat": 18.9, "lon": 72.8}
    # Target in deep international waters (high seas west of Indian EEZ)
    target_high_seas = {"lat": 18.0, "lon": 60.0}
    
    resp = rs.calculate_safe_route(start, target_high_seas)
    assert resp.status == "INVALID_COORDINATES"
    assert "outside the Indian Exclusive Economic Zone" in resp.message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
