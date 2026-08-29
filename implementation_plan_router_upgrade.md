# Implementation Plan: State Machine Coordinator (Concurrency & Router Schema)

This document specifies the technical design, edge graph configurations, and testing strategies for the upgraded **State Machine Coordinator** in SagarMitra AI, resolving concurrency race conditions, temporal ambiguities, and fallback parsing vulnerabilities.

---

## 1. Goal Description

Establish a robust, high-performance State Machine Coordinator that executes API fetches concurrently in Python (avoiding graph race conditions), parses complex temporal ranges, maps intents deterministically, and validates coordinate token contexts.

---

## 2. Technical Architecture & Component Flow

To prevent LangGraph double-trigger race conditions and state-merging overwrite conflicts, we replace parallel graph fan-out branches with a single **`Fetch Agent Data`** node that runs the data tools concurrently using `asyncio.gather`.

```
User Query (e.g. Tamil text) 
     ↓ [Bhashini translation]
English Query 
     ↓
Conversational History + New Query (with temporal range)
     ↓
┌─────────────────────────────────────────────────────────────┐
│                   Query Router Node                         │
│  - Extracts intents, target coordinates, and time ranges     │
│  - Evaluates Location Availability & Intent Constraints     │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ├──────────────────────────┐
                             │ (Data Required)          │ (Bypass: Informational / No Coords)
                             ▼                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  Fetch Agent Data Node                      │
│  - Runs weather, ocean, geofence concurrently in Python    │
│  - Enforces a 5.0s execution timeout per tool               │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│             Safety rules & Pathfinder Routing               │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Component Details

### A. Pydantic Structured Output Schema
The LLM router is bound to a strict validation schema with Literal Enums and structured time ranges:

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal

class QueryAnalysis(BaseModel):
    query_intents: List[Literal["weather_info", "pfz_search", "border_check", "informational", "safety_check"]] = Field(
        description="The categorized intents of the query."
    )
    extracted_coords: Optional[Dict[str, float]] = Field(
        default=None,
        description="GPS coordinates explicitly mentioned as {'lat': float, 'lon': float} or None"
    )
    target_time_start: Optional[str] = Field(
        default=None,
        description="ISO 8601 format start time/date or None"
    )
    target_time_end: Optional[str] = Field(
        default=None,
        description="ISO 8601 format end time/date or None"
    )
    relative_time_expr: Optional[str] = Field(
        default=None,
        description="Relative time expression e.g. 'tomorrow', 'next week', '2 days later'"
    )
```

### B. Deterministic Intent-to-Agent Mapping
Instead of trusting the LLM to output dependent representations, the router deterministically maps intents to execution agents in code:

```python
def derive_required_agents(intents: List[str], query_text: str) -> List[str]:
    agents = set()
    for intent in intents:
        if intent == "weather_info":
            agents.add("weather")
        elif intent == "pfz_search":
            agents.add("ocean")
        elif intent == "border_check":
            agents.add("geofence")
        elif intent == "safety_check":
            agents.add("weather")
            agents.add("geofence")
            # If query explicitly contains fish/productivity keywords
            if any(k in query_text.lower() for k in ["fish", "pfz", "chlorophyll", "catch"]):
                agents.add("ocean")
    return list(agents)
```

### C. Concurrency without Race Conditions (`asyncio.gather`)
The graph runs linearly, preventing LangGraph multi-trigger bugs:

```python
# Sequential Graph Layout
workflow.set_entry_point("initialize")
workflow.add_edge("initialize", "router")

def route_from_router(state: AgentState) -> Literal["fetch_data", "consensus"]:
    # 1. Informational bypass checks (only bypass if no data agents are required)
    if not state.get("required_agents") and "informational" in state.get("query_intents", []):
        return "consensus"
        
    # 2. Location availability check (bypass if location is required but completely unavailable)
    location_required = "safety_check" in state["query_intents"] or "border_check" in state["query_intents"]
    if location_required and not state.get("vessel_coords"):
        return "consensus" # Bypasses to consensus to return "Coordinates required"
        
    return "fetch_data"

workflow.add_conditional_edges("router", route_from_router, {
    "fetch_data": "fetch_data",
    "consensus": "consensus"
})

workflow.add_edge("fetch_data", "safety_rules")
```

Inside the `fetch_data_node`, we run fetches concurrently with a **5-second timeout** per API call:
```python
async def fetch_data_node(state: AgentState) -> Dict[str, Any]:
    reqs = state.get("required_agents", [])
    tasks = []
    
    if "weather" in reqs:
        tasks.append(asyncio.wait_for(fetch_weather_report(state), timeout=5.0))
    if "ocean" in reqs:
        tasks.append(asyncio.wait_for(fetch_ocean_report(state), timeout=5.0))
    if "geofence" in reqs:
        tasks.append(asyncio.wait_for(fetch_geofence_report(state), timeout=5.0))
        
    # Gather tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # Merge results and handle timeout errors gracefully
```

---

## 4. Robust Parser & Fallbacks

To resolve coordinate extraction ambiguities, the fallback text parser enforces:
1.  **Coordinate Context Checks:** Discards pairs of numbers unless preceded by geographical tokens like `LAT`, `LON`, `GPS`, `COORDS`, `POSITION`, or followed by cardinal orientation tags (`N`, `S`, `E`, `W`). This prevents mistaking wind speeds and wave swells for GPS coords.
2.  **Range Validation:** Latitude must lie in $[-90.0, 90.0]$ and Longitude in $[-180.0, 180.0]$.

---

## 5. Verification & Testing

Our updated test suite (`scratch/test_orchestrator.py`) includes 7 cases covering:
*   Safety vectors (weather storms, geofence breaches, safe fishing).
*   API failures and timeouts.
*   **Informational bypass** query routes.
*   **Vague time constraint** resolution.
*   **Text token parsing fallback robustness** under malformed inputs.
