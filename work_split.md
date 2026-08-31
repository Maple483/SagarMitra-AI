# SagarMitra AI: Team Work Split & Task Allocation

This document outlines the allocation of tasks and milestones across the team to guide the next phases of development for the SagarMitra (ORCA) platform.

---

## 1. Task Allocation Overview

### **Tanmay**
*   **Hierarchical Supervisor Agent (LangGraph):** Upgrading the orchestrator to a supervisor model that dynamically decomposes user queries and coordinates specialized subagents.
*   **A\* Route Optimization:** Building the grid-based pathfinding engine to compute safest maritime routes around high swells, weather warnings, and restricted polygons.
*   **TimescaleDB Analytics Engine:** Designing time-series SQL regressions for historical sea surface temperature, chlorophyll, and fish catch data to analyze productivity declines.

### **Sanskar**
*   **PostGIS Integration & Spatial Queries:** Migrating baseline coordinate checks to a PostgreSQL database with PostGIS, writing `ST_Contains` and `ST_Distance` queries over shapefiles.
*   **Bhashini Multilingual Adapter:** Replacing the mock translation stub in `main.py` with live MeitY Bhashini API endpoints to support regional languages.
*   **Vite React UI Enhancements:** Upgrading the Leaflet map in `App.tsx` to handle dynamic cost-grid routes, chlorophyl heatmaps, and multiple vessel drawers.

### **Pratik**
*   **UI/UX Dashboard Styling:** Polishing React frontend layouts with Tailwind CSS, refining the sidebar chat controls, and creating warning alerts.
*   **Historical Dashboard Charts:** Building telemetry history visualization graphs showing speed, heading, and weather trends over time.

### **Ishita**
*   **Data Ingestion & Cleaning:** Standardizing and cleaning coastal regulatory zone (CRZ) datasets, parsing MoEFCC eco-sensitive zone (ESZ) coordinates, and preparing CSV tables.
*   **Redundant API Integrations:** Configuring secondary weather APIs (Open-Meteo, IMD alerts) to act as fallbacks if primary INCOIS endpoints are unreachable.

### **Shivika**
*   **GIS and Boundary Configurations:** Acquiring, simplifying, and formatting maritime shapefiles (World EEZ, WDPA Marine Protected Areas) for database import.
*   **Visual Map Styling:** Styling Leaflet map overlays for ecological boundaries and navy zones (line weights, warning colors).

### **Arin**
*   **Deep-Sea Communication Gateway:** Integrating cellular GPRS-to-satellite VMS telemetry handlers in the FastAPI gateway for vessels operating beyond 15 km.
*   **NavIC Broadcast Prep:** Structuring binary payload compression formatting to send weather/PFZ updates to ISRO’s NavIC satellite broadcast queue.
*   **QA & System Verification:** Creating integration test suites to verify coordinate extraction, geofence rules, and chatbot performance.

---

## 2. Integrated Timeline

```
Phase 1 (Active)  --> Phase 2 (GIS/PFZ/SST)  --> Phase 3 (Bhashini/UI) --> Phase 4 (Routing/DB) --> Phase 5 (Satellite)
[Core Engine]         [Live Feeds & GIS]         [Local Languages]       [Path & Analytics]     [Deep-Sea Gateway]
(Tanmay/Sanskar)      (Ishita/Shivika)           (Sanskar/Pratik)        (Tanmay/Sanskar)       (Arin/All)
```
