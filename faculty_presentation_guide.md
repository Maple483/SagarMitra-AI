# ⚓ SagarMitra AI — System Architecture & Workflow Reference

> **Purpose:** Faculty Review & System Engineering Reference Sheet  
> **Format:** High-Contrast, High-Legibility Architecture & Workflow Breakdown.

---

## 1. System Architecture (Layer-by-Layer)

The platform is designed in **5 decoupled layers**, ensuring clear boundaries and preventing AI hallucination in navigational safety.

```
┌────────────────────────────────────────────────────────────────────────┐
│  LAYER 1: ACCESS & PRESENTATION CHANNELS                               │
│  • 🖥️ Web Tactical Map (React 18 + Leaflet GIS for Harbor & Tablets)    │
│  • 📱 Low-Bandwidth GSM Gateway (Compressed SMS / USSD for Keypad Phones)│
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │  REST API Calls & Live WebSockets
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│  LAYER 2: INTEGRATION & API GATEWAY                                    │
│  • ⚡ FastAPI Web Server (Uvicorn ASGI)                                 │
│  • Ingests GPS Telemetry, validates coordinates & orchestrates tasks    │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │  Dispatches Requests to Computation Core
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│  LAYER 3: DETERMINISTIC SAFETY & CALCULATION CORE (No AI Guesswork)    │
│  • 🧭 Dynamic A* Pathfinder: Great-Circle navigation & storm bypass   │
│  • 🛡️ Sovereign Geofence: 200 NM EEZ & Sri Lanka / Maldives IMBL      │
│  • ⚖️ Safety Rules Engine: Deterministic swell & wind risk evaluation  │
└────────────────────────┬───────────────────────────────────┬───────────┘
                         ▲                                   │
      Ingests Live Feeds │                                   │ Verified Facts &
      & Historical Data  │                                   │ Safety Vectors
                         │                                   ▼
┌────────────────────────┴───────────────┐ ┌─────────────────────────────┐
│  LAYER 4: MULTI-SOURCE OCEAN DATA      │ │ LAYER 5: MULTILINGUAL AI    │
│  • 🌊 INCOIS: PFZ Advisories & ERDDAP  │ │ • 🤖 Groq LLaMA-3 Assistant │
│  • 🌪️ IMD: Cyclones & High Wave Alerts │ │ • Translates verified facts │
│  • 🛰️ NASA: SST & Chlorophyll Maps     │ │   into 8+ Indic languages   │
│  • 📊 CMFRI: 20-Year Marine Landings   │ │ • Zero AI Hallucinations    │
└────────────────────────────────────────┘ └─────────────────────────────┘
```

### 🗣️ How to Explain the Architecture to Faculty (Verbatim Speech):
> *"Respected professors, our system architecture is built in five decoupled layers:*
>
> 1. *At the top is our **Presentation Layer**, supporting both a rich Leaflet web map for harbor authorities and a low-bandwidth SMS/USSD channel for rural fishermen with basic keypad phones.*
> 2. *Requests enter through our **FastAPI Gateway**, which routes queries to our **Deterministic Calculation Core**. This core runs our A\* pathfinding, checks UNCLOS international borders, and evaluates storm wave limits. **Crucially, navigation and border safety are 100% mathematical rules — never left to AI guesswork.***
> 3. *This engine is fed by our **Ocean Observation Layer**, integrating live feeds from INCOIS, IMD, NASA Earthdata, and CMFRI fish records.*
> 4. *Finally, our **Multilingual AI Assistant** acts strictly as a communication bridge, taking the verified safety decisions and explaining them in regional Indic languages so any fisherman can understand them."*

---

## 2. Operational Decision Workflow

Here is the step-by-step pipeline executed when a navigator sets a waypoint or asks an ocean safety question:

```
[ Step 1: User Input ]
   │
   ├─► Captain clicks destination on Marine Map
   └─► Crew asks spoken question: "Is it safe to sail southwest today?"
   │
   ▼
[ Step 2: Parallel Data & Safety Validation ]
   │
   ├── Check A (Weather): Wave height, wind speed, and cyclone warnings from INCOIS/IMD
   ├── Check B (Obstacles): Shallow shoals (Adam's Bridge) and islands
   └── Check C (Borders): Sovereign 200 NM EEZ and Sri Lanka / Maldives IMBL lines
   │
   ▼
[ Step 3: Hazard Avoidance & Routing Decision ]
   │
   ├── Case 1 (Path crosses 4.5m Wave Alert):
   │     └── Dynamic A* automatically curves the route safely around the storm perimeter.
   │
   ├── Case 2 (Vessel approaches IMBL within 2 km):
   │     └── Triggers immediate 'Preventative Steer Away' warning siren and blocks border breach.
   │
   └── Case 3 (Safe Open Water):
         └── Generates direct fuel-efficient Great-Circle nautical track.
   │
   ▼
[ Step 4: Grounded Multilingual Advisory Output ]
   │
   └── AI language model takes verified facts and explains them in selected regional Indic language.
   │
   ▼
[ Step 5: Final Delivery to Vessel ]
   │
   └── Navigator receives visual route on map (waypoints, distance in NM, travel time) + plain voice advisory.
```

### 🗣️ How to Explain the Workflow to Faculty (Verbatim Speech):
> *"When a user interacts with the system, the workflow follows five disciplined steps:*
>
> *First, the user sets a destination or asks a spoken safety question. Our backend immediately executes three parallel checks — assessing live wave heights from INCOIS, static shoals, and legal maritime borders.*
>
> *If a 4.5-meter storm wave lies ahead, the system doesn't draw a straight line into danger; our A\* pathfinder automatically calculates a smooth curve around the hazard with safe clearance. If the boat drifts near the Sri Lankan maritime boundary, it triggers an immediate proximity siren.*
>
> *Finally, these mathematical decisions are translated into the crew's native dialect, delivering a safe visual track and trusted spoken advice to the vessel."*

---

## 3. Key Engineering Pillars (Quick Faculty Defense)

1. **Zero AI Hallucination:** The LLM is strictly confined to translation. Coordinates, paths, and safety alerts are 100% computed mathematically by deterministic algorithms.
2. **Offline / Outage Failsafe:** If weather APIs fail in deep waters, the system flags risk as UNKNOWN with 0.0 confidence, advising extreme caution rather than assuming calm seas.
3. **Low-Bandwidth Support:** Works for both high-end harbor tablets via WebSockets, and rural keypad phones via compressed GSM SMS / USSD telemetry.
