# SagarMitra AI (ORCA)
### **Intelligent Multilingual Maritime Safety & Dynamic A\* Navigation Platform for Indian Coastal Waters**

---

## Overview
**SagarMitra AI** is a real-time maritime intelligence platform designed to safeguard Indian fishermen, navigators, and coastal vessels. It integrates:
- **Groq-Powered Multilingual AI Assistant:** Real-time conversational safety reasoning across 8+ Indic languages (Tamil, Telugu, Hindi, Malayalam, Kannada, Gujarati, Bengali, Odia) and English.
- **Dynamic Time-Dependent A\* Pathfinder:** Safe nautical pathfinding avoiding active storm swell alerts, shallow shoals (e.g. Adam's Bridge), restricted naval operational zones, and island landmasses.
- **Strict EEZ & Geofence Intelligence:** Real-time compliance with UNCLOS 200 NM Indian Exclusive Economic Zone, 1974/1976 India-Sri Lanka IMBL, and 1976 India-Maldives Eight Degree Channel treaties.
- **Oceanographic Data Integration:** Direct ingestion of INCOIS Potential Fishing Zones (PFZ) and active wave hazard advisories.
- **Interactive Marine Leaflet Dashboard:** Risk-colored route segments (Low/Medium/High), compass bearings, nominal ETE, and waypoint telemetry.

---

## Quick Start & Run Guide

### 1. Prerequisites
- **Python:** `3.10` or higher
- **Node.js:** `18.0.0` or higher & `npm`
- **Groq API Key:** (Free tier available at [console.groq.com](https://console.groq.com))

---

### 2. Backend Setup (`orca-backend`)

1. Navigate to the backend directory:
   ```bash
   cd orca-backend
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure Environment Variables:
   Set your `GROQ_API_KEY` (either in an `.env` file or in your environment):
   ```powershell
   $env:GROQ_API_KEY="your_groq_api_key_here"
   ```

4. Start the FastAPI Backend Server:
   ```bash
   python main.py
   ```
   *The backend will run on `http://localhost:8000` (API Docs: `http://localhost:8000/docs`).*

---

### 3. Frontend Setup (`orca-frontend`)

1. Navigate to the frontend directory:
   ```bash
   cd orca-frontend
   ```

2. Install Node dependencies:
   ```bash
   npm install
   ```

3. Start the Vite Development Server:
   ```bash
   npm run dev
   ```
   *The UI will run on `http://localhost:3000`.*

---

##  Automated Test Suite

Run the full pathfinding and spatial geometry verification suite:
```bash
pytest orca-backend/tests/test_pathfinder.py -v
```

### Verified Test Cases:
- `test_precomputed_geodesic_metrics`: Step distances match Haversine formula (< 0.05% error).
- `test_corner_cutting_prevention`: Prevents diagonal transitions across touching land cells.
- `test_connected_water_snapping`: Port snapping connects dock positions without jumping isthmuses.
- `test_dijkstra_a_star_optimality_equivalence`: Verifies heuristic admissibility and shortest-path optimality.
- `test_spatiotemporal_hazard_avoidance`: Confirms clearance around active 4.5m swell hazard cores.
- `test_route_service_telemetry_schema`: Validates Pydantic response models, bearings, and ETE.
- `test_bearing_computation`: Verifies Great-Circle azimuth calculations.
- `test_strict_eez_geofencing`: Confirms automatic rejection of routes into international waters.

---

##  System Architecture & File Structure

```
sih/
├── orca-backend/
│   ├── agents/
│   │   ├── boundary_provider.py   # EEZ / IMBL treaties, static island masks, geodesic lookup tables
│   │   ├── pathfinder.py          # Time-dependent A* engine, Great-Circle SLERP smoothing
│   │   ├── route_service.py       # Pydantic schemas, compass bearings, telemetry calculation
│   │   ├── pfz_loader.py          # INCOIS Potential Fishing Zone CSV dataset reader
│   │   └── orchestrator.py        # LangGraph consensus engine & multi-agent pipeline
│   ├── data/
│   │   └── pfz_advisories.csv     # Official INCOIS PFZ advisory coordinate catalog
│   ├── tests/
│   │   └── test_pathfinder.py     # 8 comprehensive automated unit tests
│   ├── main.py                    # FastAPI gateway, Groq translation, /api/chat, /api/route
│   └── requirements.txt           # Python dependency specifications
│
└── orca-frontend/
    ├── src/
    │   ├── App.tsx                # Leaflet marine chart, multilingual chat, custom marker routing
    │   ├── main.tsx               # React application entry point
    │   └── index.css              # Tailwind CSS styles
    ├── package.json               # Node.js dependencies and scripts
    └── vite.config.ts             # Vite bundler configuration
```

---

##  API Endpoints Reference

### 1. `POST /api/chat`
Conversational marine safety queries with automatic Indic language translation and route synthesis.
- **Request Body:** `{"prompt": "Calculate safe route to my fishing zone"}`
- **Response:** `{"reply": "...", "route": {...}}`

### 2. `POST /api/route`
Direct A* nautical pathfinding endpoint.
- **Request Body:**
  ```json
  {
    "start_lat": 9.93,
    "start_lon": 76.26,
    "target_lat": 10.50,
    "target_lon": 70.00,
    "speed_knots": 12.0,
    "system_context": "Active Wave alert (4.5m swells) at Lat 16.0, Lng 71.0"
  }
  ```
- **Response:** Returns `RouteResponse` with waypoints, bearings, distance (NM), ETE (hours), and risk levels.

### 3. `GET /api/pfz`
Returns all active INCOIS Potential Fishing Zone coordinates and advisories.

### 4. `GET /health`
Backend health check and operational status.
