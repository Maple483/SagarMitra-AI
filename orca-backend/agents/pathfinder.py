import heapq
import math
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta
import numpy as np

from agents.boundary_provider import (
    boundary_provider,
    haversine_km,
    NUM_ROWS,
    NUM_COLS,
    GRID_RES,
    MIN_LAT,
    MIN_LON
)

# Custom Exceptions
class PathfindingError(Exception):
    pass

class StartOnLandError(PathfindingError):
    pass

class TargetOnLandError(PathfindingError):
    pass

class StartOutsideEEZError(PathfindingError):
    pass

class TargetOutsideEEZError(PathfindingError):
    pass

class NoSafePathFoundError(PathfindingError):
    pass


class MaritimeHazard:
    """Represents a dynamic spatial/weather hazard with temporal validity."""
    def __init__(
        self,
        center_lat: float,
        center_lon: float,
        radius_km: float,
        swell_height_m: float = 3.0,
        hazard_type: str = "swell_alert",
        valid_from: Optional[datetime] = None,
        valid_until: Optional[datetime] = None
    ):
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.radius_km = radius_km
        self.swell_height_m = swell_height_m
        self.hazard_type = hazard_type
        self.valid_from = valid_from or datetime.utcnow() - timedelta(hours=1)
        self.valid_until = valid_until or datetime.utcnow() + timedelta(hours=48)

    def is_active_at(self, query_time: datetime) -> bool:
        return self.valid_from <= query_time <= self.valid_until

    def get_penalty(self, lat: float, lon: float, query_time: datetime) -> float:
        """
        Evaluates the dynamic penalty at a given coordinate and arrival timestamp.
        Returns np.inf for impassable storm cores, >0 for soft wave penalties, 0.0 otherwise.
        """
        if not self.is_active_at(query_time):
            return 0.0

        d = haversine_km(lat, lon, self.center_lat, self.center_lon)
        if d >= self.radius_km:
            return 0.0

        # Hard core for severe swell (>= 4.0m) within 50% radius
        if self.swell_height_m >= 4.0 and d < (0.5 * self.radius_km):
            return float('inf')

        # Quadratic soft penalty
        normalized_d = d / max(1.0, self.radius_km)
        weight = 10.0 if self.swell_height_m >= 4.0 else 4.0
        return weight * ((1.0 - normalized_d) ** 2)


class MaritimeAStarPathfinder:
    """
    Time-dependent A* Maritime Pathfinder with lazy temporal hazard evaluation,
    corner-cutting leak prevention, Great-Circle geodesic smoothing, and admissible heuristics.
    """

    def __init__(self, nominal_speed_knots: float = 10.0):
        self.provider = boundary_provider
        self.nominal_speed_kmh = nominal_speed_knots * 1.852  # 1 knot = 1.852 km/h
        self.speed_kmh = max(1.0, self.nominal_speed_kmh)

    def _get_dynamic_cost(
        self,
        r: int,
        c: int,
        arrival_time: datetime,
        hazards: List[MaritimeHazard]
    ) -> float:
        """
        Calculates C(n', t_arrival) on the fly without materializing 3D arrays.
        Semantic hierarchy: Hard obstacle (land/shoal/naval) = inf, Normal water = 1.0 + sum(penalties).
        """
        if self.provider.is_cell_impassable(r, c):
            return float('inf')

        lat, lon = self.provider.cell_to_coord(r, c)
        cost = 1.0

        for h in hazards:
            p = h.get_penalty(lat, lon, arrival_time)
            if math.isinf(p):
                return float('inf')
            cost += p

        return cost

    def _spherical_geodesic_interpolate(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        num_samples: int
    ) -> List[Tuple[float, float]]:
        """
        Generates num_samples intermediate points along the Great-Circle geodesic arc.
        Uses 3D spherical interpolation (SLERP) on unit vectors.
        """
        phi1 = math.radians(lat1)
        lam1 = math.radians(lon1)
        phi2 = math.radians(lat2)
        lam2 = math.radians(lon2)

        v1 = np.array([math.cos(phi1) * math.cos(lam1), math.cos(phi1) * math.sin(lam1), math.sin(phi1)])
        v2 = np.array([math.cos(phi2) * math.cos(lam2), math.cos(phi2) * math.sin(lam2), math.sin(phi2)])

        dot = np.clip(np.dot(v1, v2), -1.0, 1.0)
        omega = math.acos(dot)

        if omega < 1e-6:
            return [(lat1, lon1), (lat2, lon2)]

        sin_omega = math.sin(omega)
        points = []

        for i in range(num_samples):
            t = i / float(num_samples - 1)
            vt = (math.sin((1.0 - t) * omega) / sin_omega) * v1 + (math.sin(t * omega) / sin_omega) * v2
            norm = np.linalg.norm(vt)
            if norm > 0:
                vt /= norm

            lat_t = math.degrees(math.asin(np.clip(vt[2], -1.0, 1.0)))
            lon_t = math.degrees(math.atan2(vt[1], vt[0]))
            points.append((lat_t, lon_t))

        return points

    def find_path(
        self,
        start_lat: float,
        start_lon: float,
        goal_lat: float,
        goal_lon: float,
        hazards: Optional[List[MaritimeHazard]] = None,
        start_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Executes time-dependent A* search with Great Circle cost-integral smoothing.
        """
        hazards = hazards or []
        t0 = start_time or datetime.utcnow()

        # 1. Snap start and goal to connected navigable water
        s_lat, s_lon, start_r, start_c = self.provider.snap_to_connected_navigable_water(start_lat, start_lon)
        g_lat, g_lon, goal_r, goal_c = self.provider.snap_to_connected_navigable_water(goal_lat, goal_lon)

        if not self.provider.is_inside_eez(start_lat, start_lon):
            raise StartOutsideEEZError("Departure location lies outside the Indian Exclusive Economic Zone in International Waters.")

        if not self.provider.is_inside_eez(goal_lat, goal_lon):
            raise TargetOutsideEEZError("Target destination lies outside the Indian Exclusive Economic Zone in International Waters. Fishing vessels are legally restricted from crossing the outer EEZ boundary.")

        if self.provider.is_cell_impassable(start_r, start_c):
            raise StartOnLandError("Departure coordinates cannot be connected to navigable water inside the EEZ.")

        if self.provider.is_cell_impassable(goal_r, goal_c):
            raise TargetOnLandError("Target destination lies inside an impassable land, shoal, or restricted zone.")

        if (start_r, start_c) == (goal_r, goal_c):
            return {
                "grid_path": [(start_r, start_c)],
                "smoothed_coords": [(s_lat, s_lon)],
                "total_dist_km": 0.0,
                "total_cost": 0.0
            }

        # 2. Priority queue A* search
        # Heap tuple: (f_score, g_cost, r, c, elapsed_hours)
        h_start = haversine_km(s_lat, s_lon, g_lat, g_lon)
        open_set = [(h_start, 0.0, start_r, start_c, 0.0)]
        came_from = {}
        cost_so_far = {(start_r, start_c): 0.0}
        time_so_far = {(start_r, start_c): 0.0}

        goal_reached = False

        # 8-connected transitions: (dr, dc, is_diagonal)
        directions = [
            (-1, 0, False), (1, 0, False), (0, -1, False), (0, 1, False),
            (-1, -1, True), (-1, 1, True), (1, -1, True), (1, 1, True)
        ]

        while open_set:
            f, g, r, c, elapsed_h = heapq.heappop(open_set)

            if (r, c) == (goal_r, goal_c):
                goal_reached = True
                break

            if g > cost_so_far.get((r, c), float('inf')):
                continue

            for dr, dc, is_diag in directions:
                nr, nc = r + dr, c + dc

                if nr < 0 or nr >= self.provider.num_rows or nc < 0 or nc >= self.provider.num_cols:
                    continue

                # Diagonal Corner-Cutting Check: both orthogonal neighbors must be unblocked
                if is_diag:
                    if self.provider.is_cell_impassable(r + dr, c) or self.provider.is_cell_impassable(r, c + dc):
                        continue

                # Step Distance Calculation from Precomputed Metric Tables
                if not is_diag:
                    step_dist = self.provider.dist_ns if dr != 0 else self.provider.dist_ew[r]
                else:
                    step_dist = self.provider.dist_diag_up[r] if dr > 0 else self.provider.dist_diag_down[r]

                # Lazy Temporal Arrival Time Calculation
                step_time_h = step_dist / self.speed_kmh
                n_arrival_time = t0 + timedelta(hours=elapsed_h + step_time_h)

                # Cost Coefficient C(n', t_arrival)
                cost_coeff = self._get_dynamic_cost(nr, nc, n_arrival_time, hazards)
                if math.isinf(cost_coeff):
                    continue

                edge_cost = step_dist * cost_coeff
                new_g = g + edge_cost
                new_time = elapsed_h + step_time_h

                if new_g < cost_so_far.get((nr, nc), float('inf')):
                    cost_so_far[(nr, nc)] = new_g
                    time_so_far[(nr, nc)] = new_time
                    came_from[(nr, nc)] = (r, c)

                    n_lat, n_lon = self.provider.cell_to_coord(nr, nc)
                    h = haversine_km(n_lat, n_lon, g_lat, g_lon)
                    heapq.heappush(open_set, (new_g + h, new_g, nr, nc, new_time))

        if not goal_reached:
            raise NoSafePathFoundError("No navigable route could be resolved avoiding active storm cores and land boundaries.")

        # 3. Reconstruct Grid Path
        curr = (goal_r, goal_c)
        path = [curr]
        while curr in came_from:
            curr = came_from[curr]
            path.append(curr)
        path.reverse()

        # 4. Geodesic Line-of-Sight Cost-Integral Smoothing
        smoothed_coords, total_km = self._smooth_path_cost_integral(path, hazards, t0)

        # Pinpoint Accuracy: Anchor to exact continuous user coordinates
        if len(smoothed_coords) >= 2:
            smoothed_coords[0] = (start_lat, start_lon)
            smoothed_coords[-1] = (goal_lat, goal_lon)
            total_km = sum(
                haversine_km(smoothed_coords[k][0], smoothed_coords[k][1], smoothed_coords[k+1][0], smoothed_coords[k+1][1])
                for k in range(len(smoothed_coords) - 1)
            )

        return {
            "grid_path": path,
            "smoothed_coords": smoothed_coords,
            "total_dist_km": round(total_km, 2),
            "total_cost": round(cost_so_far[(goal_r, goal_c)], 2)
        }

    def _smooth_path_cost_integral(
        self,
        grid_path: List[Tuple[int, int]],
        hazards: List[MaritimeHazard],
        start_time: datetime
    ) -> Tuple[List[Tuple[float, float]], float]:
        """
        Smoothes the discrete 8-connected grid path using Great-Circle geodesic line integration.
        Allows up to 5% cost increase during smoothing to eliminate grid staircase artifacts
        without soft-hazard inversion.
        """
        if len(grid_path) <= 2:
            coords = [self.provider.cell_to_coord(r, c) for r, c in grid_path]
            d = haversine_km(coords[0][0], coords[0][1], coords[-1][0], coords[-1][1]) if len(coords) == 2 else 0.0
            return coords, d

        # Convert full grid path to raw coordinates
        raw_coords = [self.provider.cell_to_coord(r, c) for r, c in grid_path]

        # Greedy raycast smoothing
        smoothed = [raw_coords[0]]
        i = 0

        while i < len(raw_coords) - 1:
            best_next = i + 1

            # Look ahead as far as possible
            for j in range(len(raw_coords) - 1, i + 1, -1):
                if self._is_geodesic_shortcut_valid(raw_coords, i, j, hazards, start_time):
                    best_next = j
                    break

            smoothed.append(raw_coords[best_next])
            i = best_next

        # Secondary pass: Direct raycast between non-adjacent smoothed waypoints
        for _ in range(2):
            if len(smoothed) <= 2:
                break
            refined = [smoothed[0]]
            m = 0
            while m < len(smoothed) - 1:
                next_m = m + 1
                for n in range(len(smoothed) - 1, m + 1, -1):
                    p1 = smoothed[m]
                    p2 = smoothed[n]
                    dist = haversine_km(p1[0], p1[1], p2[0], p2[1])
                    samples = max(4, int(math.ceil(dist / 2.5)))
                    pts = self._spherical_geodesic_interpolate(p1[0], p1[1], p2[0], p2[1], samples)
                    if all(not self.provider.is_cell_impassable(*self.provider.coord_to_cell(lat, lon)) for lat, lon in pts):
                        next_m = n
                        break
                refined.append(smoothed[next_m])
                m = next_m
            smoothed = refined

        # Calculate total smoothed geodesic distance
        total_dist = 0.0
        for k in range(len(smoothed) - 1):
            total_dist += haversine_km(smoothed[k][0], smoothed[k][1], smoothed[k + 1][0], smoothed[k + 1][1])

        return smoothed, total_dist

    def _is_geodesic_shortcut_valid(
        self,
        raw_coords: List[Tuple[float, float]],
        start_idx: int,
        end_idx: int,
        hazards: List[MaritimeHazard],
        start_time: datetime
    ) -> bool:
        """
        Evaluates whether a direct Great-Circle segment from raw_coords[start_idx] to raw_coords[end_idx]
        is obstacle-free (C < inf) and does not exceed the A* path cost by more than 5%.
        """
        p1 = raw_coords[start_idx]
        p2 = raw_coords[end_idx]
        direct_dist = haversine_km(p1[0], p1[1], p2[0], p2[1])

        # Sub-sample every ~3 km along the Great-Circle arc
        num_samples = max(4, int(math.ceil(direct_dist / 3.0)))
        sample_pts = self._spherical_geodesic_interpolate(p1[0], p1[1], p2[0], p2[1], num_samples)

        # 1. Hard Obstacle & Dynamic Cost Integral Integration
        direct_cost = 0.0
        step_km = direct_dist / float(num_samples - 1)
        step_time_h = step_km / self.speed_kmh

        for k, (s_lat, s_lon) in enumerate(sample_pts):
            sr, sc = self.provider.coord_to_cell(s_lat, s_lon)
            if self.provider.is_cell_impassable(sr, sc):
                return False

            sample_time = start_time + timedelta(hours=k * step_time_h)
            cost_c = self._get_dynamic_cost(sr, sc, sample_time, hazards)
            if math.isinf(cost_c):
                return False

            direct_cost += step_km * cost_c

        # 2. Compute Original Sub-path Cost
        original_cost = 0.0
        for idx in range(start_idx, end_idx):
            sub_p1 = raw_coords[idx]
            sub_p2 = raw_coords[idx + 1]
            sub_d = haversine_km(sub_p1[0], sub_p1[1], sub_p2[0], sub_p2[1])
            sub_r, sub_c = self.provider.coord_to_cell(sub_p2[0], sub_p2[1])
            orig_c = self._get_dynamic_cost(sub_r, sub_c, start_time, hazards)
            original_cost += sub_d * (orig_c if not math.isinf(orig_c) else 1.0)

        # Allow up to 5% cost increase during smoothing to remove grid artifacts
        return direct_cost <= (original_cost * 1.05)


# Global singleton instance
pathfinder = MaritimeAStarPathfinder()
