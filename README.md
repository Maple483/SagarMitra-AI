# SagarMitra AI (ORCA)
### **Intelligent Multilingual Maritime Safety, Dynamic A\* Navigation & Fisheries Productivity Platform**

---

## Overview
**SagarMitra AI (ORCA)** is a production-grade maritime intelligence and tactical decision-support system built for Indian coastal waters, navigators, port authorities, and fishing communities. It unites:

1. **Dynamic Time-Dependent A\* Pathfinder:**
   - Great-Circle geodesic navigation with spherical SLERP post-smoothing.
   - Strict non-penetration hazard avoidance: routes gracefully curve around active high-wave alert zones (e.g. 4.5m swells).
   - **Terminal Zone Tactical Handling:** If destination or departure lies inside a hazard zone (search & rescue, distress, or port approach), the pathfinder navigates via safe waters to the closest perimeter waypoint before executing the shortest direct tactical leg with high-risk telemetry.
   - **Multi-Pointer Path Persistence:** Supports dropping multiple custom markers with simultaneous route rendering, individual route focusing, and "All Routes" vs "Single Route" toggling.
   - Shallow shoal avoidance (Adam's Bridge / Palk Strait) and corner-cutting prevention across island chains.

2. **International Maritime Boundary (EEZ / IMBL) Geofencing:**
   - Enforces legal navigation boundaries: 200 NM Indian Exclusive Economic Zone (UNCLOS), 1974/1976 India-Sri Lanka IMBL, and 1976 India-Maldives Eight Degree Channel.
   - Automatically detects and prevents route generation into non-jurisdictional international high seas.

3. **Marine Fisheries Productivity & Historical Catch Analytics:**
   - Causal and statistical analysis across 2007–2026 historical marine landings from CMFRI / ICAR datasets.
   - Multi-state coverage (Gujarat, Maharashtra, Goa, Karnataka, Kerala, Tamil Nadu, Andhra Pradesh, Odisha, West Bengal) across 9 commercial pelagic and demersal species.
   - Environmental covariate regression integrating Sea Surface Temperature (SST) and Chlorophyll-a anomalies.

4. **Live Oceanographic & Satellite Earth Observation:**
   - Real-time INCOIS Potential Fishing Zones (PFZ) advisory ingestion.
   - NASA GIBS Earthdata integration: Near-real-time Sea Surface Temperature (MUR L4 1km analysis) and Chlorophyll-a (VIIRS SNPP True Color & Chlorophyll concentrations).
   - INCOIS ERDDAP ocean state forecast failover with automated telemetry failover.

5. **Multilingual Generative Safety Agent (Groq / LLaMA-3):**
   - Natural language maritime assistant supporting 8+ Indic languages (Hindi, Tamil, Telugu, Malayalam, Kannada, Gujarati, Bengali, Odia) and English.

---

## System Requirements & Prerequisites

| Component | Minimum Requirement | Recommended |
|---|---|---|
| **Python** | `3.10` or higher | `3.10` / `3.11` |
| **Node.js** | `18.0.0` or higher | `20.x` LTS (`npm 9+`) |
| **Operating System** | Windows 10/11, macOS, or Linux | Windows / Ubuntu 22.04 |
| **API Keys** | `GROQ_API_KEY` (Free tier from [console.groq.com](https://console.groq.com)) | Optional: `OPENAI_API_KEY` |

---

## Quick Start & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/ROYALKINGSJ/SIH_CS6.git
cd SIH_CS6
```

---

### 2. Backend Setup (`orca-backend`)

1. **Navigate to the backend folder:**
   ```bash
   cd orca-backend
   ```

2. **Create and activate a virtual environment (optional but recommended):**
   ```bash
   # Windows (PowerShell)
   python -m venv venv
   .\venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set Environment Variables:**
   Create an `.env` file in `orca-backend/` (or set in shell):
   ```ini
   GROQ_API_KEY=your_groq_api_key_here
   ```
   *(PowerShell alternative: `$env:GROQ_API_KEY="your_groq_api_key_here"`)*

5. **Start the FastAPI Backend:**
   ```bash
   python main.py
   ```
   * The API server starts on **`http://localhost:8000`**
   * Interactive Swagger documentation: **`http://localhost:8000/docs`**
   * OpenAPI Specification: **`http://localhost:8000/openapi.json`**

---

### 3. Frontend Setup (`orca-frontend`)

1. **Open a new terminal and navigate to the frontend folder:**
   ```bash
   cd orca-frontend
   ```

2. **Install Node modules:**
   ```bash
   npm install
   ```

3. **Start the Vite development server:**
   ```bash
   npm run dev
   ```
   * The client application launches at **`http://localhost:3000`**

---

## Running the Automated Test Suite

The platform includes a comprehensive automated test suite covering A* pathfinding, temporal hazard avoidance, space-time weather failover, marine statistics, and API endpoints:

```bash
cd orca-backend
pytest -v
```

### Test Coverage Highlights (42 Passing Tests):
- **`tests/test_pathfinder.py` (10 tests):**
  - Metric step distance accuracy (< 0.05% vs Haversine equation)
  - Diagonal corner-cutting leak prevention across land boundaries
  - Port snapping to connected navigable water
  - Dijkstra vs. A* optimality equivalence
  - Spatiotemporal storm hazard avoidance
  - Route telemetry schema and compass bearing validation
  - Strict EEZ / IMBL boundary geofencing
  - Strict non-penetration of external hazard perimeters
  - Destination inside terminal hazard zone navigation with tactical advisory
- **`tests/test_marine_statistics.py` (11 tests):**
  - CMFRI historical landings data validation & alignment
  - Pearson & Spearman correlation coefficients and p-values
  - Robust Z-score anomaly detection and scenario projections
- **`tests/test_marine_api.py` (6 tests):**
  - Endpoints `/api/marine-productivity/metadata`, `/timeseries`, `/align`, `/interpret`
- **`tests/test_weather_failover.py` (4 tests):**
  - ERDDAP live connection and graceful offline telemetry failover
- **`tests/test_space_time_weather.py` (6 tests):**
  - Time-stepped environmental field interpolation along vessel trajectories
- **`tests/test_sms_gateway.py` (5 tests):**
  - Compact marine emergency SMS dispatch and encoding

---

## System Architecture & Directory Layout

```
SIH_CS6/
├── orca-backend/
│   ├── agents/
│   │   ├── boundary_provider.py       # EEZ / IMBL treaties, static shoals, geodesic lookup tables
│   │   ├── pathfinder.py              # Time-dependent A* engine, geodesic smoothing, terminal zones
│   │   ├── route_service.py           # Pydantic schemas, compass bearings, telemetry calculation
│   │   ├── weather_service.py         # INCOIS ERDDAP telemetry & failover cache
│   │   ├── imd_cyclone_service.py     # IMD severe weather bulletin parser
│   │   ├── pfz_loader.py              # INCOIS Potential Fishing Zone reader
│   │   └── orchestrator.py            # LangGraph multi-agent safety pipeline
│   ├── marine_productivity/
│   │   ├── router.py                  # FastAPI router for /api/marine-productivity/*
│   │   ├── repository.py              # CMFRI landings & SST/Chlorophyll cache loader
│   │   ├── statistics.py              # SciPy/NumPy correlation & regression engine
│   │   ├── scientific_interpreter.py  # Evidence-based fisheries interpretation
│   │   ├── scenario_engine.py         # SST warming anomaly trajectory simulator
│   │   └── satellite.py               # NASA GIBS satellite layer metadata provider
│   ├── data/
│   │   ├── orca-dataset.json          # Historical state-wise fish landings (2007-2026)
│   │   ├── Combined_Marine_Landings.csv
│   │   └── pfz_advisories.csv         # Official INCOIS PFZ coordinates
│   ├── tests/                         # Full automated pytest suite (42 tests)
│   ├── conftest.py                    # Pytest environment & path configuration
│   ├── main.py                        # FastAPI application entry point
│   └── requirements.txt               # Backend Python dependencies
│
└── orca-frontend/
    ├── src/
    │   ├── components/
    │   │   ├── marine_productivity/   # Marine Productivity Modal, Live Satellite Viewer
    │   │   ├── WeatherQuickWidget.tsx # Coastal weather telemetry HUD
    │   │   └── WeatherMapDrawer.tsx   # Detailed weather drawer
    │   ├── App.tsx                    # Main interactive Leaflet marine chart & navigation HUD
    │   ├── main.tsx                   # React root mount
    │   └── index.css                  # Tailwind styles
    ├── package.json                   # Frontend dependencies
    └── vite.config.ts                 # Vite configuration
```

---

## API Documentation

### 1. Direct A* Nautical Pathfinding (`POST /api/route`)
Computes obstacle-free, hazard-avoiding Great-Circle routes within the Indian EEZ.

**Request:**
```json
POST http://localhost:8000/api/route
Content-Type: application/json

{
  "start_lat": 15.40,
  "start_lon": 73.80,
  "target_lat": 14.30,
  "target_lon": 69.80,
  "vessel_name": "ORCA-1",
  "speed_knots": 12.0,
  "system_context": "Active Wave alert (4.5m swells, radius 180km) at Lat 15.5, Lng 71.0"
}
```

**Response (Sample):**
```json
{
  "status": "SUCCESS",
  "total_dist_nm": 234.8,
  "nominal_ete_hours": 19.6,
  "minimum_hazard_clearance_nm": 2.2,
  "max_risk_level": "LOW",
  "message": "Safe nautical route resolved avoiding active high wave alert zones with 2.2 NM minimum clearance.",
  "waypoints": [
    { "name": "Start Departure", "lat": 15.40, "lon": 73.80, "cumulative_distance_nm": 0.0 },
    { "name": "Waypoint 1", "lat": 15.00, "lon": 73.55, "cumulative_distance_nm": 27.8 },
    { "name": "Waypoint 2", "lat": 13.95, "lon": 71.60, "cumulative_distance_nm": 135.2 },
    { "name": "Destination", "lat": 14.30, "lon": 69.80, "cumulative_distance_nm": 234.8 }
  ],
  "segments": [
    {
      "start_lat": 15.40, "start_lon": 73.80,
      "end_lat": 15.00, "end_lon": 73.55,
      "distance_nm": 27.8, "bearing_deg": 208.5,
      "risk_level": "LOW"
    }
  ]
}
```

### 2. Multilingual Maritime Safety Chat (`POST /api/chat`)
Processes conversational queries with Groq LLaMA-3 in English or Indic languages.

**Request:**
```json
POST http://localhost:8000/api/chat
Content-Type: application/json

{
  "prompt": "Is it safe to sail from Panaji towards southwest offshore given current high wave alerts?"
}
```

### 3. Marine Fisheries Productivity (`GET /api/marine-productivity/interpret`)
Computes correlation coefficients and scenario analysis for coastal marine species.

**Request:**
```bash
curl "http://localhost:8000/api/marine-productivity/interpret?state=Kerala&species=Sardine"
```

---

## License & Acknowledgments
* **License:** Apache-2.0
* **Data Providers:** Indian National Centre for Ocean Information Services (INCOIS), India Meteorological Department (IMD), Central Marine Fisheries Research Institute (CMFRI), and NASA Earthdata (GIBS).
