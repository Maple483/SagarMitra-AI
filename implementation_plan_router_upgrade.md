# Implementation Plan: State Machine Coordinator (Production Grade Concurrency & Validation)

This document specifies the technical design, edge graph configurations, and testing strategies for the upgraded **State Machine Coordinator** in SagarMitra AI, resolving temporal ambiguities, race conditions, validation fallbacks, and coordinate parser formatting blindspots.

---

## 1. Goal Description

Establish a production-grade concurrency router that enforces schema-validated inputs, manages temporal conflicts authoritatively, resolves multilingual coordinate formats, and routes requests safely using explicit response statuses.

---

## 2. Technical Architecture & Component Flow

```
User Query (e.g. Tamil text) 
     ↓
┌─────────────────────────────────────────────────────────────┐
│              Multilingual Coordinate Parsing                 │
│  - Parses raw coordinate pairs (lat, lon) and card directions│
│    in English / Tamil prior to translation/routing          │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
English Translated Query (via Bhashini)
     ↓
Conversational History + New Query
     ↓
┌─────────────────────────────────────────────────────────────┐
│                   Query Router Node                         │
│  - Extracts intents, coordinates, and datetime ranges       │
│  - Enforces Pydantic datetime validation for ISO-8601       │
│  - Maps intents deterministically to data agents            │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ├──────────────────────────┐ (Bypass: Informational / Insufficient data)
                             │ (Data Required)          │ (State: response_status set accordingly)
                             ▼                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  Fetch Agent Data Node                      │
│  - Concurrently queries weather, ocean, and geofence        │
│  - Custom timeouts: 2.0s geofence, 6.0s weather/ocean APIs  │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                 Safety Rules & Consensus                    │
│  - Resolves decisions or prints insufficient data alerts    │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Component Details

### A. Pydantic Structured Output Schema (Strict Validation)
By using `datetime` objects in Pydantic, the model automatically enforces valid ISO-8601 formats, rejecting descriptions like `"tomorrow morningish"` during schema parse steps.

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict, Optional, Literal

class QueryAnalysis(BaseModel):
    query_intents: List[Literal["weather_info", "pfz_search", "border_check", "informational", "general_safety", "fishing_safety"]] = Field(
        description="The categorized intents of the query."
    )
    extracted_coords: Optional[Dict[str, float]] = Field(
        default=None,
        description="GPS coordinates explicitly mentioned as {'lat': float, 'lon': float} or None"
    )
    target_time_start: Optional[datetime] = Field(
        default=None,
        description="ISO 8601 format start time/date or None"
    )
    target_time_end: Optional[datetime] = Field(
        default=None,
        description="ISO 8601 format end time/date or None"
    )
    relative_time_expr: Optional[str] = Field(
        default=None,
        description="Relative time expression e.g. 'tomorrow', 'next week', '2 days later'"
    )
```

### B. Deterministic Mapping & Resolution
Instead of relying on LLM selection for required agents, we map them in code based on validated intents:

*   `weather_info` $\to$ `["weather"]`
*   `pfz_search` $\to$ `["ocean"]`
*   `border_check` $\to$ `["geofence"]`
*   `general_safety` $\to$ `["weather", "geofence"]`
*   `fishing_safety` $\to$ `["weather", "ocean", "geofence"]`

---

## 4. Concurrency & Timeout Specifications

Inside `fetch_data_node`, tasks are executed concurrently in a mapped structure:

```python
async def fetch_data_node(state: AgentState) -> Dict[str, Any]:
    reqs = state.get("required_agents", [])
    task_map = {}
    
    # Custom timeout parameters
    if "weather" in reqs:
        task_map["weather"] = asyncio.wait_for(fetch_weather_report(state), timeout=6.0)
    if "ocean" in reqs:
        task_map["ocean"] = asyncio.wait_for(fetch_ocean_report(state), timeout=6.0)
    if "geofence" in reqs:
        task_map["geofence"] = asyncio.wait_for(fetch_geofence_report(state), timeout=2.0)
        
    if not task_map:
        return {}
        
    keys = list(task_map.keys())
    tasks = list(task_map.values())
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    updates = {}
    for key, res in zip(keys, results):
        if isinstance(res, Exception):
            # Log failure reason explicitly for downstream Safety evaluation
            updates[f"{key}_report"] = {
                "data": {},
                "status": "failed",
                "data_mode": "unavailable",
                "error": str(res)
            }
            updates["agent_status"] = {**updates.get("agent_status", {}), key: "FAILED"}
        else:
            updates.update(res)
    return updates
```

---

## 5. Explicit Graph Response Statuses

To ensure the Consensus Explainer never hallucinates, we define:
`response_status: Optional[Literal["SUCCESS", "INSUFFICIENT_LOCATION", "INSUFFICIENT_INTENT"]]`

*   If spatial agents are required but no coordinates exist in `vessel_coords` or `target_coords`: Set `response_status = "INSUFFICIENT_LOCATION"` and bypass to `consensus`.
*   If no query intents are successfully matched or derived: Set `response_status = "INSUFFICIENT_INTENT"` and bypass to `consensus`.

---

## 6. Multilingual Robust Fallback Coordinates Parser

Supports decimal cardinal patterns and regional translations before the English Bhashini boundary:
*   Matches: `"13.08 N, 80.27 E"`, `"Position: 12.34 84.56"`, `"12.54, 74.32"` (Google maps raw pastes).
*   Matches Tamil cardinal/position markers: `"அட்சரேகை 13.08 தீர்க்கரேகை 80.27"`
*   Restricts numbers to valid global coordinate ranges to filter out wind/swell speed metrics.
