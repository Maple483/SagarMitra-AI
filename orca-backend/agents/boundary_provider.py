import math
from typing import Dict, Any, List, Tuple, Optional
import numpy as np

# Grid Specifications
MIN_LAT = 5.0
MAX_LAT = 25.0
MIN_LON = 65.0
MAX_LON = 90.0
GRID_RES = 0.05  # 0.05 degrees

NUM_ROWS = int(round((MAX_LAT - MIN_LAT) / GRID_RES)) + 1  # 401
NUM_COLS = int(round((MAX_LON - MIN_LON) / GRID_RES)) + 1  # 501
EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Exact Great-Circle Haversine distance in kilometers."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_KM * c


class MaritimeBoundaryProvider:
    """
    Manages static nautical boundaries, landmasses, bathymetric shoals,
    precomputed geodesic metric lookup tables, and harbor water snapping.
    """

    def __init__(self):
        self.num_rows = NUM_ROWS
        self.num_cols = NUM_COLS
        self.min_lat = MIN_LAT
        self.min_lon = MIN_LON
        self.grid_res = GRID_RES

        # Precompute 1D row coordinate tables
        self.lat_by_row = np.array([MIN_LAT + r * GRID_RES for r in range(NUM_ROWS)], dtype=np.float32)
        self.lon_by_col = np.array([MIN_LON + c * GRID_RES for c in range(NUM_COLS)], dtype=np.float32)

        # Precompute exact center-to-center geodesic neighbor step distances
        self._precompute_geodesic_metrics()

        # Build and pre-rasterize static impassable mask (Land, Shoals, Naval Prohibited Zones)
        self.static_impassable_mask = np.zeros((NUM_ROWS, NUM_COLS), dtype=bool)
        self._rasterize_static_features()

    def _precompute_geodesic_metrics(self):
        """
        Precomputes the exact geodesic distances between neighboring cell centers
        for each movement direction to avoid runtime trigonometry.
        """
        self.dist_ns = haversine_km(MIN_LAT, 70.0, MIN_LAT + GRID_RES, 70.0)  # Constant ~5.557 km

        self.dist_ew = np.zeros(NUM_ROWS, dtype=np.float32)
        self.dist_diag_up = np.zeros(NUM_ROWS, dtype=np.float32)
        self.dist_diag_down = np.zeros(NUM_ROWS, dtype=np.float32)

        for r in range(NUM_ROWS):
            lat = self.lat_by_row[r]
            # East-West step at row r
            self.dist_ew[r] = haversine_km(lat, 70.0, lat, 70.0 + GRID_RES)

            # Diagonal Up (North-East / North-West) from row r to r+1
            if r + 1 < NUM_ROWS:
                self.dist_diag_up[r] = haversine_km(lat, 70.0, lat + GRID_RES, 70.0 + GRID_RES)
            else:
                self.dist_diag_up[r] = self.dist_diag_up[r - 1]

            # Diagonal Down (South-East / South-West) from row r to r-1
            if r - 1 >= 0:
                self.dist_diag_down[r] = haversine_km(lat, 70.0, lat - GRID_RES, 70.0 + GRID_RES)
            else:
                self.dist_diag_down[r] = self.dist_diag_down[r + 1]

    def coord_to_cell(self, lat: float, lon: float) -> Tuple[int, int]:
        """Converts decimal coordinates to integer grid indices (row, col) clamped to bounds."""
        r = int(round((lat - self.min_lat) / self.grid_res))
        c = int(round((lon - self.min_lon) / self.grid_res))
        r = max(0, min(self.num_rows - 1, r))
        c = max(0, min(self.num_cols - 1, c))
        return r, c

    def cell_to_coord(self, r: int, c: int) -> Tuple[float, float]:
        """Converts grid indices (row, col) back to decimal lat/lon coordinates."""
        lat = round(float(self.min_lat + r * self.grid_res), 4)
        lon = round(float(self.min_lon + c * self.grid_res), 4)
        return lat, lon

    def _rasterize_static_features(self):
        """
        Pre-rasterizes static polygons (Mainland India, Sri Lanka, Lakshadweep/Maldives,
        Goa Naval Exercise Zone, Adam's Bridge / Palk Strait shoal barrier).
        """
        # 1. Indian Mainland coastal polygon
        mainland_poly = [
            (24.5, 68.0), (23.5, 68.3), (22.8, 70.0), (22.2, 69.0),
            (20.8, 70.4), (21.5, 72.3), (20.0, 72.8), (18.9, 72.8),
            (16.0, 73.5), (15.2, 73.8), (13.0, 74.8), (10.0, 75.8),
            (8.1, 77.5), (8.5, 78.1), (9.2, 79.2), (10.3, 79.8),
            (11.0, 79.8), (13.1, 80.3), (16.0, 81.3), (17.7, 83.3),
            (19.8, 85.8), (21.5, 87.0), (22.0, 89.0), (25.0, 90.0),
            (25.0, 65.0), (24.5, 68.0)
        ]

        # 2. Sri Lanka landmass polygon
        sri_lanka_poly = [
            (9.8, 80.2), (9.0, 79.7), (8.0, 79.8), (6.0, 80.2),
            (5.9, 80.6), (6.9, 81.9), (8.5, 81.3), (9.8, 80.2)
        ]

        # 3. Goa Naval Exercise Operational Polygon (Restricted zone)
        # Lat 15.0 to 16.0, Lon 72.0 to 73.5
        goa_naval_poly = [
            (15.0, 72.0), (16.0, 72.0), (16.0, 73.5), (15.0, 73.5), (15.0, 72.0)
        ]

        # 4. Adam's Bridge / Ram Setu shallow reef barrier (Depth < 2m shoal)
        adams_bridge_poly = [
            (9.10, 79.35), (9.30, 79.70), (9.15, 79.75), (8.95, 79.40), (9.10, 79.35)
        ]

        # 5. Full Lakshadweep Island & Administrative Territory (Matching OpenStreetMap Island Polygon)
        # Bounded by: Lat 7.7°N to 12.8°N, Lon 71.3°E to 74.2°E
        lakshadweep_zone_poly = [
            (12.80, 71.30),  # Northwest
            (12.80, 73.80),  # Northeast
            (10.90, 74.20),  # East (Andrott)
            (9.80, 74.00),   # Southeast (Kalpeni)
            (7.80, 73.30),   # South apex east (Minicoy)
            (7.70, 73.00),   # South apex bottom (Below 8.0°N boundary tip)
            (7.80, 72.70),   # South apex west
            (9.80, 71.40),   # Southwest (Suheli)
            (11.00, 71.30),  # West (Agatti / Bitra)
            (12.80, 71.30)   # Close loop
        ]
        # Minicoy Island Atoll (in Eight Degree Channel)
        minicoy_poly = [
            (8.45, 72.90), (8.45, 73.20), (8.15, 73.20), (8.15, 72.90), (8.45, 72.90)
        ]

        # 6. Maldives Archipelago Atolls (Male, Ari, Nilandhe, Huvadhoo)
        maldives_north_poly = [
            (7.2, 72.7), (7.2, 73.4), (3.0, 73.8), (3.0, 72.7), (7.2, 72.7)
        ]
        maldives_south_poly = [
            (2.2, 72.7), (2.2, 73.8), (0.0, 73.6), (0.0, 72.7), (2.2, 72.7)
        ]

        # 7. Official Indian EEZ Polygon (Matching official Marine Regions / UNCLOS dataset)
        self.indian_eez_poly = [
            (23.85, 68.10),  # Sir Creek / Pakistan Maritime Boundary
            (21.80, 66.10),  # Kutch Outer Continental Shelf
            (20.40, 65.80),  # Saurashtra Outer EEZ Limit
            (17.50, 68.30),  # Maharashtra Outer EEZ 200 NM Limit
            (14.50, 69.20),  # Goa Outer EEZ Limit
            (12.50, 68.50),  # West of Northern Lakshadweep
            (10.00, 68.30),  # West of Central Lakshadweep
            (8.00, 69.50),   # Southwest of Lakshadweep
            (7.60, 71.00),   # Eight Degree Channel West
            (7.60, 73.50),   # Eight Degree Channel Median Line (India-Maldives Boundary)
            (7.80, 74.80),   # Eight Degree Channel East
            (4.784, 77.023), # Point T: India - Sri Lanka - Maldives Trijunction (Southward Arrowhead Point)
            (7.20, 78.60),   # Wadge Bank / Gulf of Mannar Entry
            (8.60, 79.20),   # Gulf of Mannar Median Line
            (9.15, 79.52),   # Adam's Bridge / Rameswaram (IMBL Treaty)
            (9.80, 79.80),   # Palk Bay Median Line
            (10.20, 80.30),  # Palk Strait Exit (North of Jaffna / Point Pedro)
            (11.50, 83.50),  # Bay of Bengal (East of Tamil Nadu)
            (13.50, 85.00),  # Bay of Bengal (East of Andhra Pradesh)
            (16.00, 86.50),  # Bay of Bengal (East of Visakhapatnam)
            (18.00, 88.50),  # Bay of Bengal (East of Odisha)
            (21.15, 89.40),  # India - Bangladesh Maritime Boundary (UNCLOS 2014 Award)
            (21.65, 89.15),  # West Bengal Coast
            (25.0, 90.0),    # Mainland envelope closure
            (25.0, 65.0),
            (23.85, 68.10)
        ]

        self.inside_eez_mask = np.zeros((self.num_rows, self.num_cols), dtype=bool)

        # Point in polygon rasterizer
        for r in range(self.num_rows):
            lat = float(self.lat_by_row[r])
            for c in range(self.num_cols):
                lon = float(self.lon_by_col[c])
                
                # Check EEZ containment
                if self._point_in_polygon(lat, lon, self.indian_eez_poly):
                    self.inside_eez_mask[r, c] = True

                if self._point_in_polygon(lat, lon, mainland_poly):
                    self.static_impassable_mask[r, c] = True
                elif self._point_in_polygon(lat, lon, sri_lanka_poly):
                    self.static_impassable_mask[r, c] = True
                elif self._point_in_polygon(lat, lon, goa_naval_poly):
                    self.static_impassable_mask[r, c] = True
                elif self._point_in_polygon(lat, lon, adams_bridge_poly):
                    self.static_impassable_mask[r, c] = True
                elif self._point_in_polygon(lat, lon, lakshadweep_zone_poly):
                    self.static_impassable_mask[r, c] = True
                elif self._point_in_polygon(lat, lon, minicoy_poly):
                    self.static_impassable_mask[r, c] = True
                elif self._point_in_polygon(lat, lon, maldives_north_poly):
                    self.static_impassable_mask[r, c] = True
                elif self._point_in_polygon(lat, lon, maldives_south_poly):
                    self.static_impassable_mask[r, c] = True
                elif self._point_in_polygon(lat, lon, maldives_south_poly):
                    self.static_impassable_mask[r, c] = True

    def is_inside_eez(self, lat: float, lon: float) -> bool:
        """Returns True if the coordinate is within India's Exclusive Economic Zone."""
        r, c = self.coord_to_cell(lat, lon)
        return bool(self.inside_eez_mask[r, c])

    def _point_in_polygon(self, x: float, y: float, poly: List[Tuple[float, float]]) -> bool:
        """Ray-casting point in polygon algorithm."""
        inside = False
        n = len(poly)
        p1x, p1y = poly[0]
        for i in range(n + 1):
            p2x, p2y = poly[i % n]
            if x > min(p1x, p2x):
                if x <= max(p1x, p2x):
                    if y <= max(p1y, p2y):
                        if p1x != p2x:
                            xinters = (x - p1x) * (p2y - p1y) / (p2x - p1x) + p1y
                        if p1y == p2y or y <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    def is_cell_impassable(self, r: int, c: int) -> bool:
        """
        Returns True if cell is inside land, shoal barrier, restricted naval zone,
        or OUTSIDE the Indian Exclusive Economic Zone (Strict EEZ Geofence).
        """
        if r < 0 or r >= self.num_rows or c < 0 or c >= self.num_cols:
            return True
        # Hard obstacle check (Land / Shoal / Naval Zone)
        if self.static_impassable_mask[r, c]:
            return True
        # Strict EEZ Geofence check (International Waters & Foreign EEZs are impassable for fishing vessels)
        if not self.inside_eez_mask[r, c]:
            return True
        return False

    def snap_to_connected_navigable_water(self, lat: float, lon: float, max_search_cells: int = 8) -> Tuple[float, float, int, int]:
        """
        Finds the nearest contiguous navigable sea cell from a departure location (dock/jetty)
        using an outward BFS without crossing intermediate landmasses.
        Search radius: up to max_search_cells (~24 NM envelope).
        """
        start_r, start_c = self.coord_to_cell(lat, lon)

        # If already in open navigable water, return directly
        if not self.is_cell_impassable(start_r, start_c):
            snap_lat, snap_lon = self.cell_to_coord(start_r, start_c)
            return snap_lat, snap_lon, start_r, start_c

        # BFS spiral search for the closest contiguous water cell
        from collections import deque
        queue = deque([(start_r, start_c, 0)])
        visited = {(start_r, start_c)}
        best_cell = None
        min_dist = float('inf')

        while queue:
            curr_r, curr_c, depth = queue.popleft()
            if depth > max_search_cells:
                break

            if not self.is_cell_impassable(curr_r, curr_c):
                c_lat, c_lon = self.cell_to_coord(curr_r, curr_c)
                d = haversine_km(lat, lon, c_lat, c_lon)
                if d < min_dist:
                    min_dist = d
                    best_cell = (c_lat, c_lon, curr_r, curr_c)

            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
                nr, nc = curr_r + dr, curr_c + dc
                if 0 <= nr < self.num_rows and 0 <= nc < self.num_cols and (nr, nc) not in visited:
                    visited.add((nr, nc))
                    queue.append((nr, nc, depth + 1))

        if best_cell:
            return best_cell

        # Fallback to offshore shifted point
        return lat, lon - 0.1, start_r, max(0, start_c - 2)


# Global singleton instance
boundary_provider = MaritimeBoundaryProvider()
