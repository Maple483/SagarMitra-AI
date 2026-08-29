import os
import time
import asyncio
from datetime import datetime
from typing import TypedDict, List, Dict, Any, Optional, Annotated, Literal
from pydantic import BaseModel, Field, model_validator
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

def merge_dict(existing: dict, new_updates: dict) -> dict:
    """Merges concurrent dictionary updates safely in LangGraph."""
    merged = existing.copy() if existing else {}
    merged.update(new_updates)
    return merged

class AgentState(TypedDict):
    # Core conversation history with the message reducer to prevent duplications
    messages: Annotated[List[BaseMessage], add_messages]
    user_language: Optional[str]               # e.g., "ta" (Tamil), "te" (Telugu)
    
    # Ingested request metadata
    request_type: Optional[str]                # "query" / "gps_update" / "proactive_alert"
    vessel_id: Optional[str]
    vessel_coords: Optional[Dict[str, float]]  # {"lat": 12.34, "lon": 74.56}
    target_coords: Optional[Dict[str, float]]  # Navigation target coordinate
    target_time_start: Optional[str]
    target_time_end: Optional[str]
    relative_time_expr: Optional[str]
    
    # Intent-Based Routing variables (Compound intents supported)
    query_intents: List[str]                   # ["pfz_search", "border_check", "weather_info"]
    required_agents: List[str]                 # ["weather", "ocean", "geofence"]
    response_status: Optional[str]             # "SUCCESS" / "INSUFFICIENT_LOCATION" / "INSUFFICIENT_INTENT"
    
    # Execution Status Tracker (replaces brittle "is not None" checks)
    # Allowed states: "NOT_REQUIRED", "RUNNING", "SUCCESS", "FAILED"
    agent_status: Annotated[Dict[str, str], merge_dict]
    
    # Structured Agent Outputs (including provenance metadata)
    weather_report: Optional[Dict[str, Any]]
    ocean_report: Optional[Dict[str, Any]]
    geofence_report: Optional[Dict[str, Any]]
    
    # Consensus & Explanatory State (For the UI Consensus Map)
    agent_assessments: Dict[str, Dict[str, Any]] # Recommendation & confidence from each agent
    evidence_log: List[Dict[str, Any]]          # Structured metrics
    conflicts: List[Dict[str, Any]]             # Identified disagreements between agent modules
    decision_trace: List[str]                  # Steps taken by the safety router
    
    # Safety Classification Output
    final_risk_level: Optional[str]            # "SAFE" / "WARNING" / "CRITICAL" / "UNKNOWN"
    override_reasons: List[str]                # Accumulated causes of alerts
    decision_confidence: float                 # Calculated data reliability score (0.0 to 1.0)
    
    # Routing Output
    suggested_route: Optional[List[Dict[str, float]]]
    routing_action: Optional[str]              # "no_routing", "exit_zone", "return_to_safe", etc.
    
    # Final Output
    consensus_advice: Optional[str]            # The finalized English explanation ready for translation


# ==========================================
# 2. State Initialization Policy
# ==========================================

def initialize_request_state(state: AgentState) -> Dict[str, Any]:
    """Wipes transient analytical fields at the start of every turn to prevent memory bleed."""
    return {
        "query_intents": [],
        "required_agents": [],
        "target_time_start": None,
        "target_time_end": None,
        "relative_time_expr": None,
        "response_status": None,
        "agent_status": {
            "weather": "NOT_REQUIRED",
            "ocean": "NOT_REQUIRED",
            "geofence": "NOT_REQUIRED",
            "routing": "NOT_REQUIRED"
        },
        "weather_report": None,
        "ocean_report": None,
        "geofence_report": None,
        "agent_assessments": {},
        "evidence_log": [],
        "conflicts": [],
        "decision_trace": [],
        "final_risk_level": None,
        "override_reasons": [],
        "decision_confidence": 1.0,
        "suggested_route": None,
        "routing_action": None,
        "consensus_advice": None
    }


# ==========================================
# 3. Deterministic Safety Assessment Rules Engine
# ==========================================

def evaluate_safety_rules(state: AgentState) -> Dict[str, Any]:
    """Evaluates spatial, environmental, and weather limits. Updates state variables."""
    risk_level = "SAFE"
    evidence = []
    override_reasons = []
    conflicts = []
    decision_trace = ["Ingested coordinates", "Checked geofences", "Analyzed weather forecast"]
    
    # Check strict location coordinate hierarchy validation
    has_coords = state.get("vessel_coords") is not None
    
    # 1. Evaluate Geofence Report
    near_border = False
    g_rep_success = False
    in_restricted = False
    if state.get("geofence_report") and state["geofence_report"].get("status") == "success" and state["geofence_report"].get("data"):
        geo = state["geofence_report"]["data"]
        dist = geo.get("distance_to_boundary_meters", 99999.0)
        in_restricted = geo.get("in_restricted_zone", False)
        g_rep_success = True
        evidence.append({
            "source": "geofence",
            "metric": "distance_to_boundary",
            "value": dist,
            "unit": "meters",
            "timestamp": state["geofence_report"].get("timestamp", "")
        })
        if in_restricted:
            risk_level = "CRITICAL"
            override_reasons.append("Boundary breach: vessel is inside a restricted zone.")
        elif dist < 2000.0:
            if risk_level != "CRITICAL":
                risk_level = "WARNING"
            near_border = True
            override_reasons.append("Proximity warning: vessel within 2km of restricted border.")

    # 2. Evaluate Weather Report (with API Failsafe check)
    weather_warning_requires_route = False
    if state.get("weather_report"):
        w_rep = state["weather_report"]
        if w_rep.get("status") != "success" or not w_rep.get("data"):
            # API failure / degraded mode: immediately raise warning, do not rely on 0.0 values!
            if risk_level != "CRITICAL":
                risk_level = "WARNING"
            override_reasons.append("API Warning: Marine weather forecasts are currently unavailable.")
        else:
            w = w_rep["data"]
            evidence.append({
                "source": "weather",
                "metric": "swell_height",
                "value": w.get("swell_height", 0.0),
                "unit": "meters",
                "timestamp": w_rep.get("timestamp", "")
            })
            evidence.append({
                "source": "weather",
                "metric": "wind_speed",
                "value": w.get("wind_speed", 0.0),
                "unit": "km/h",
                "timestamp": w_rep.get("timestamp", "")
            })
            
            swell = w.get("swell_height", 0.0)
            wind = w.get("wind_speed", 0.0)
            if swell > 3.0 or wind > 45.0:
                risk_level = "CRITICAL"
                override_reasons.append("Severe weather conditions: high swells/winds exceed safety limits.")
                weather_warning_requires_route = True
            elif swell > 2.2 or wind > 35.0:
                if risk_level != "CRITICAL":
                    risk_level = "WARNING"
                override_reasons.append("Caution: elevated swells/winds detected.")
                weather_warning_requires_route = True

    # 3. Check for Conflicts (e.g. Favorable fish vs Warnings)
    if state.get("ocean_report") and state["ocean_report"].get("status") == "success" and state["ocean_report"].get("data"):
        o = state["ocean_report"]["data"]
        if o.get("sst_gradient_front") and risk_level in ["WARNING", "CRITICAL"]:
            conflicts.append({
                "agent_1": "ocean", "rec_1": "FAVORABLE (PFZ front detected)",
                "agent_2": "safety_rules", "rec_2": f"UNSAFE due to: {'; '.join(override_reasons)}",
                "resolution": "Safety override applied."
            })

    # Intent-specific critical dependency checks for UNKNOWN risk tier
    # If the user asks about borders but geofence search failed, state is UNKNOWN
    if "border_check" in state.get("query_intents", []):
        g_rep = state.get("geofence_report")
        if not g_rep or g_rep.get("status") != "success":
            risk_level = "UNKNOWN"
            override_reasons.append("Geofencing boundary checks are currently offline.")

    # Determine Routing Action (requires coordinates to route)
    routing_action = "no_routing"
    if has_coords:
        if risk_level == "CRITICAL":
            if g_rep_success and in_restricted:
                routing_action = "exit_zone"
            else:
                routing_action = "return_to_safe"
        elif risk_level == "WARNING":
            if near_border:
                routing_action = "preventative_steer_away"
            elif weather_warning_requires_route and state.get("target_coords"):
                routing_action = "preventative_shelter_route"
            else:
                routing_action = "proceed_with_caution"
        elif state.get("target_coords"):
            routing_action = "calculate_route"
            
    # Calculate Decision Confidence
    confidence = 1.0
    failed_critical = False
    for r_name in ["weather_report", "geofence_report"]:
        rep = state.get(r_name)
        if rep:
            if rep.get("status") != "success":
                confidence -= 0.4
                failed_critical = True
            elif rep.get("data_mode") == "synthetic":
                confidence -= 0.15
            elif rep.get("data_mode") == "stale":
                confidence -= 0.25
    if failed_critical and risk_level == "UNKNOWN":
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    # 4. Populate structured assessments for frontend UI rendering
    agent_assessments = {}
    if state.get("weather_report"):
        w_rep = state["weather_report"]
        agent_assessments["weather"] = {
            "recommendation": "UNSAFE" if weather_warning_requires_route else "SAFE",
            "confidence": 0.90 if w_rep.get("status") == "success" and w_rep.get("data") else 0.0,
            "reason": "; ".join(override_reasons) if weather_warning_requires_route else "Weather conditions normal.",
            "source": w_rep.get("source", "Unknown")
        }
    if state.get("geofence_report") and state["geofence_report"].get("status") == "success" and state["geofence_report"].get("data"):
        g_rep = state["geofence_report"]
        g_data = g_rep["data"]
        rec = "SAFE"
        if g_data.get("in_restricted_zone"):
            rec = "CRITICAL"
        elif g_data.get("distance_to_boundary_meters", 99999.0) < 2000.0:
            rec = "WARNING"
        agent_assessments["geofence"] = {
            "recommendation": rec,
            "confidence": 1.0,
            "reason": f"Distance to border: {g_data.get('distance_to_boundary_meters')}m",
            "source": "PostGIS"
        }
    if state.get("ocean_report") and state["ocean_report"].get("status") == "success" and state["ocean_report"].get("data"):
        o_rep = state["ocean_report"]
        o_data = o_rep["data"]
        rec = "FAVORABLE" if o_data.get("sst_gradient_front") else "NEUTRAL"
        agent_assessments["ocean"] = {
            "recommendation": rec,
            "confidence": 0.80,
            "reason": "SST/Chlorophyll fronts active." if rec == "FAVORABLE" else "No active fish fronts.",
            "source": o_rep.get("source", "Unknown")
        }
        
    decision_trace.append(f"Safety rules evaluated. Final Risk: {risk_level}")
    decision_trace.append(f"Routing action decided: {routing_action}")

    return {
        "final_risk_level": risk_level,
        "evidence_log": evidence,
        "conflicts": conflicts,
        "override_reasons": override_reasons,
        "routing_action": routing_action,
        "decision_confidence": confidence,
        "agent_assessments": agent_assessments,
        "decision_trace": decision_trace
    }


# ==========================================
# 4. Graph Node Definitions
# ==========================================

import re

class Coordinates(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)

# Pydantic model for structured router outputs
class QueryAnalysis(BaseModel):
    query_intents: List[Literal["weather_info", "pfz_search", "border_check", "informational", "general_safety", "fishing_safety"]] = Field(
        description="The categorized intents of the query."
    )
    extracted_coords: Optional[Coordinates] = Field(
        default=None,
        description="GPS coordinates explicitly mentioned as lat and lon or None"
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
    location_required: bool = Field(
        default=False,
        description="True if coordinates are required to answer this specific query, False if it is a general explanation"
    )

    @model_validator(mode="after")
    def validate_time_range(self) -> 'QueryAnalysis':
        if self.target_time_start and self.target_time_end:
            if self.target_time_end < self.target_time_start:
                raise ValueError("target_time_end must be greater than or equal to target_time_start")
        return self

def robust_coordinate_parser(text: str) -> Optional[Dict[str, float]]:
    """
    Robustly parses coordinates in decimal or cardinal formats (e.g. 13.08 N, 80.27 E)
    from translated Indic natural language inputs. Enforces context check (requires
    explicit geolocation tokens or cardinal labels N/S/E/W or raw comma-separated floats
    or regional terms அட்சரேகை/தீர்க்கரேகை) to prevent mistaking wind or swell speeds for coordinates.
    """
    text_clean = text.upper().replace("°", "").replace("'", "")
    
    # 1. Look for pairs of numbers with cardinal indicators: N/S, E/W
    pattern_cardinal = re.compile(
        r"(-?\d+\.?\d*)\s*([NS])\b.*?(-?\d+\.?\d*)\s*([EW])\b", re.IGNORECASE
    )
    match_cardinal = pattern_cardinal.search(text_clean)
    if match_cardinal:
        lat_val = float(match_cardinal.group(1))
        lat_dir = match_cardinal.group(2)
        lon_val = float(match_cardinal.group(3))
        lon_dir = match_cardinal.group(4)
        lat = -lat_val if lat_dir == 'S' else lat_val
        lon = -lon_val if lon_dir == 'W' else lon_val
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
            return {"lat": lat, "lon": lon}
            
    # 2. Match raw comma-separated floats (e.g. 12.54, 74.32) commonly pasted from Google Maps
    pattern_raw_pair = re.compile(
        r"\b(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\b"
    )
    match_raw = pattern_raw_pair.search(text_clean)
    if match_raw:
        lat = float(match_raw.group(1))
        lon = float(match_raw.group(2))
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
            return {"lat": lat, "lon": lon}

    # 3. Match float pairs with explicit geographic context tags (supporting Tamil translations too)
    geo_tokens = ["LAT", "LON", "GPS", "COORDS", "POSITION", "COORDINATE", "அட்சரேகை", "தீர்க்கரேகை"]
    if any(tok in text_clean for tok in geo_tokens):
        pattern_floats = re.compile(
            r"\b(-?\d+\.\d+)\b[^\d.-]*\b(-?\d+\.\d+)\b"
        )
        match_floats = pattern_floats.search(text_clean)
        if match_floats:
            lat = float(match_floats.group(1))
            lon = float(match_floats.group(2))
            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                return {"lat": lat, "lon": lon}
                
    return None

def initialize_node(state: AgentState):
    return initialize_request_state(state)

def router_node(state: AgentState):
    """Parses user message and routes based on intent, resolving conversational history context."""
    messages = state.get("messages", [])
    if not messages:
        return {
            "query_intents": ["informational"],
            "required_agents": [],
            "response_status": "INSUFFICIENT_INTENT",
            "agent_status": {"weather": "NOT_REQUIRED", "ocean": "NOT_REQUIRED", "geofence": "NOT_REQUIRED", "routing": "NOT_REQUIRED"}
        }

    # Dynamic date injection into the system prompt to prevent date hallucinations
    current_time_str = datetime.utcnow().isoformat()
    pre_parsed_coords = robust_coordinate_parser(messages[-1].content)
    
    # 1. Run LLM Structured Router over conversational memory
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are the Query Router for SagarMitra AI, a decision support assistant for Indian coastal fishermen.\n"
            f"Current Server UTC time is: {current_time_str}Z. Use this datetime as reference to parse relative terms like 'tomorrow' or 'next week'.\n\n"
            "Available Intents (Must select from these exact Literals):\n"
            "- 'weather_info': Weather alerts, wind speeds, cyclones, swell waves.\n"
            "- 'pfz_search': Potential Fishing Zones, SST gradients, chlorophyll maps, catches.\n"
            "- 'border_check': Borders, IMBL, restricted marine areas, protected waters.\n"
            "- 'informational': Greetings, help, standard information requests.\n"
            "- 'general_safety': General safety check combining weather and border checks.\n"
            "- 'fishing_safety': Fishing-specific safety combining weather, ocean state, and border checks.\n\n"
            "If coordinates are explicitly mentioned, parse them as {'lat': float, 'lon': float}.\n"
            "If target times are requested (e.g. tomorrow, next week), extract relative_time_expr or absolute start/end datetimes."
        )),
        *messages
    ])
    
    target_time_start = None
    target_time_end = None
    relative_time_expr = None
    coords = None
    location_required = False
    
    try:
        # Structured output parser enforcing strict validation constraints
        llm = ChatOpenAI(temperature=0.0).with_structured_output(QueryAnalysis)
        chain = prompt | llm
        analysis = chain.invoke({})
        intents = analysis.query_intents
        coords = analysis.extracted_coords or pre_parsed_coords
        target_time_start = analysis.target_time_start
        target_time_end = analysis.target_time_end
        relative_time_expr = analysis.relative_time_expr
        location_required = analysis.location_required
        
        # Temporal resolution conflict check: absolute range overrides relative
        if target_time_start or target_time_end:
            relative_time_expr = None
            
    except Exception:
        # Fallback to local deterministic keyword and context parsing
        query_text = messages[-1].content
        msg = query_text.lower()
        coords = pre_parsed_coords
        
        # Simple local time parsing check
        if "tomorrow" in msg:
            relative_time_expr = "tomorrow"
            
        informational_keywords = ["who are you", "what is", "about sagarmitra", "hello", "hi", "help"]
        if any(kw in msg for kw in informational_keywords):
            intents = ["informational"]
            location_required = False
        else:
            intents = []
            if query_text.strip():
                if any(w in msg for w in ["weather", "cyclone", "wind", "swell", "rain"]):
                    intents.append("weather_info")
                if any(o in msg for o in ["fish", "pfz", "chlorophyll", "temp", "catch"]):
                    intents.append("pfz_search")
                if any(g in msg for g in ["border", "imbl", "restricted", "mpa", "naval"]):
                    intents.append("border_check")
                    
                if not intents:
                    intents = ["general_safety"]
            
            # Fallback check for location dependency
            for intent in intents:
                if intent in ["border_check", "general_safety", "fishing_safety"]:
                    location_required = True
                elif intent in ["weather_info", "pfz_search"]:
                    if any(k in msg for k in ["here", "near", "at", "coords", "gps", "position", "current"]):
                        location_required = True
                        
    # Deterministic mapping: derive agents in code rather than letting LLM decide independently
    agents = derive_required_agents(intents, messages[-1].content)
                
    # Align required status trackers
    status = {a: "RUNNING" for a in agents}
    for default_a in ["weather", "ocean", "geofence"]:
        if default_a not in status:
            status[default_a] = "NOT_REQUIRED"
            
    # Resolve Coordinates object to dict mapping
    coords_dict = None
    if coords:
        if hasattr(coords, "lat") and hasattr(coords, "lon"):
            coords_dict = {"lat": coords.lat, "lon": coords.lon}
        elif isinstance(coords, dict):
            coords_dict = coords
            
    # Set coordinates if resolved
    has_location = coords_dict or state.get("vessel_coords") or state.get("target_coords")
    response_status = "SUCCESS"
    
    if not intents:
        response_status = "INSUFFICIENT_INTENT"
    elif location_required and not has_location:
        response_status = "INSUFFICIENT_LOCATION"
        
    update_data = {
        "query_intents": intents,
        "required_agents": agents,
        "agent_status": {**status, "routing": "NOT_REQUIRED"},
        "target_time_start": target_time_start.isoformat() if target_time_start else None,
        "target_time_end": target_time_end.isoformat() if target_time_end else None,
        "relative_time_expr": relative_time_expr,
        "response_status": response_status
    }
    if coords_dict:
        update_data["vessel_coords"] = coords_dict
        
    return update_data

def derive_required_agents(intents: List[str], query_text: str) -> List[str]:
    agents = set()
    for intent in intents:
        if intent == "weather_info":
            agents.add("weather")
        elif intent == "pfz_search":
            agents.add("ocean")
        elif intent == "border_check":
            agents.add("geofence")
        elif intent == "general_safety":
            agents.add("weather")
            agents.add("geofence")
        elif intent == "fishing_safety":
            agents.add("weather")
            agents.add("ocean")
            agents.add("geofence")
        elif intent == "safety_check":
            agents.add("weather")
            agents.add("geofence")
            # If query explicitly contains fish/productivity keywords
            if any(k in query_text.lower() for k in ["fish", "pfz", "chlorophyll", "catch", "ocean"]):
                agents.add("ocean")
    return list(agents)

async def fetch_weather_report(state: AgentState) -> Dict[str, Any]:
    # Mock weather retrieval (normally checks IMD / Open-Meteo)
    coords = state.get("vessel_coords") or {"lat": 13.0, "lon": 80.0}
    await asyncio.sleep(0.1)
    return {
        "weather_report": {
            "data": {"wind_speed": 48.0, "swell_height": 3.2}, # Storm conditions mock
            "source": "Open-Meteo Marine",
            "data_mode": "live",
            "timestamp": "2026-08-28T22:30:00Z",
            "status": "success"
        }
    }

async def fetch_ocean_report(state: AgentState) -> Dict[str, Any]:
    # Mock ocean retrieval (normally checks INCOIS)
    await asyncio.sleep(0.1)
    return {
        "ocean_report": {
            "data": {"sst_gradient_front": True, "chlorophyll_density": 3.8},
            "source": "INCOIS",
            "data_mode": "live",
            "timestamp": "2026-08-28T22:30:00Z",
            "status": "success"
        }
    }

async def fetch_geofence_report(state: AgentState) -> Dict[str, Any]:
    # Mock geofence retrieval (normally checks PostGIS)
    coords = state.get("vessel_coords")
    if not coords:
        coords = {"lat": 13.08, "lon": 80.27} # Port fallback
    await asyncio.sleep(0.1)
    return {
        "geofence_report": {
            "data": {
                "in_restricted_zone": False,
                "nearest_boundary": "India-Sri Lanka IMBL",
                "distance_to_boundary_meters": 1500.0
            },
            "source": "PostGIS",
            "data_mode": "live",
            "timestamp": "2026-08-28T22:30:00Z",
            "status": "success"
        },
        "vessel_coords": coords
    }

async def fetch_data_node(state: AgentState) -> Dict[str, Any]:
    """
    Executes required weather, ocean, and geofence data fetches concurrently in Python.
    Enforces a strict 7.0 second overall deadline, and custom timeouts per tool.
    """
    reqs = state.get("required_agents", [])
    task_map = {}
    
    # Initialize execution status map
    status_map = {a: "RUNNING" for a in reqs}
    for default_a in ["weather", "ocean", "geofence"]:
        if default_a not in status_map:
            status_map[default_a] = "NOT_REQUIRED"
            
    # Custom timeout parameters
    if "weather" in reqs:
        task_map["weather"] = fetch_weather_report(state)
    if "ocean" in reqs:
        task_map["ocean"] = fetch_ocean_report(state)
    if "geofence" in reqs:
        task_map["geofence"] = fetch_geofence_report(state)
        
    if not task_map:
        return {"agent_status": status_map}
        
    # Wrap tasks in asyncio.create_task to make them awaitable futures
    # Enforce custom timeouts per tool using asyncio.wait_for inside the futures
    futures = {}
    if "weather" in task_map:
        futures["weather"] = asyncio.create_task(asyncio.wait_for(task_map["weather"], timeout=6.0))
    if "ocean" in task_map:
        futures["ocean"] = asyncio.create_task(asyncio.wait_for(task_map["ocean"], timeout=6.0))
    if "geofence" in task_map:
        futures["geofence"] = asyncio.create_task(asyncio.wait_for(task_map["geofence"], timeout=2.0))
        
    # Enforce overall 7.0s request deadline using asyncio.wait
    done, pending = await asyncio.wait(
        futures.values(),
        timeout=7.0
    )
    
    # Cancel any pending tasks
    for task in pending:
        task.cancel()
        
    results = []
    keys = []
    for key, fut in futures.items():
        keys.append(key)
        if fut in done:
            try:
                res = fut.result()
                results.append(res)
            except Exception as e:
                results.append(e)
        else:
            results.append(asyncio.TimeoutError("Global Request Timeout (7.0s exceeded)"))
            
    updates = {"agent_status": status_map}
    partial_failure = False
    
    for key, res in zip(keys, results):
        if isinstance(res, Exception):
            print(f"[Fetch Node] Tool {key} failed or timed out: {str(res)}")
            # Degraded failsafe mode: mark status as FAILED to prevent hanging
            updates[f"{key}_report"] = {
                "status": "FAILED",
                "data": None,
                "error_code": "TIMEOUT",
                "data_mode": "unavailable"
            }
            updates["agent_status"][key] = "FAILED"
            partial_failure = True
        else:
            # Merge successfully retrieved report
            updates.update(res)
            updates["agent_status"][key] = "SUCCESS"
            
    if partial_failure:
        updates["response_status"] = "PARTIAL_DATA"
        
    return updates

def safety_rules_node(state: AgentState):
    print(">>> SAFETY RULES NODE EXECUTING! <<<")
    results = evaluate_safety_rules(state)
    routing_needed = results["routing_action"] not in ["no_routing", "proceed_with_caution"]
    return {
        **results,
        "agent_status": {
            "routing": "RUNNING" if routing_needed else "NOT_REQUIRED"
        }
    }

def routing_node(state: AgentState):
    # Call A* Router Pathfinder
    try:
        # Check path viability
        path_viable = True  # Mock pathfinding check
        if not path_viable:
            return {
                "routing_action": "NO_SAFE_ROUTE",
                "agent_status": {"routing": "SUCCESS"}
            }
        
        # Returns coordinates steering away or returning to port
        route = [
            {"lat": 13.0827, "lon": 80.2707},
            {"lat": 13.0500, "lon": 80.2500}
        ]
        return {
            "suggested_route": route,
            "agent_status": {"routing": "SUCCESS"}
        }
    except Exception:
        return {
            "agent_status": {"routing": "FAILED"}
        }

def consensus_explainer_node(state: AgentState):
    status = state.get("response_status")
    
    # 1. Deterministic Interventions for Validation Failures (Prevents LLM Hallucinations)
    if status == "INSUFFICIENT_LOCATION":
        advice = "Error: GPS coordinates are required to perform safety and geofence checks. Please provide your location (e.g. 13.08 N, 80.27 E) or ensure your vessel tracker is active."
        return {
            "consensus_advice": advice,
            "messages": [AIMessage(content=advice)]
        }
        
    if status == "INSUFFICIENT_INTENT":
        advice = "I couldn't identify the specific safety query. Please ask a clearer question about weather conditions, borders, or fishing safety."
        return {
            "consensus_advice": advice,
            "messages": [AIMessage(content=advice)]
        }

    # Retrieve safety and routing decisions from the state
    final_risk = state.get("final_risk_level", "SAFE")
    overrides = "; ".join(state.get("override_reasons", [])) or "None"
    evidence = state.get("evidence_log", [])
    action = state.get("routing_action", "no_routing")
    confidence = state.get("decision_confidence", 1.0)
    
    # Calculate data mode summary to prevent KeyError
    modes = []
    for report_name in ["weather_report", "ocean_report", "geofence_report"]:
        report = state.get(report_name)
        if report:
            modes.append(f"{report_name.split('_')[0]}: {report.get('data_mode', 'unknown')}")
    data_mode_summary = ", ".join(modes) if modes else "No external reports fetched."
    
    if status == "PARTIAL_DATA":
        data_mode_summary += " (Warning: Some external datasets failed or timed out)"
        
    # Direct response informational check
    if "informational" in state.get("query_intents", []):
        prompt_template = ChatPromptTemplate.from_template(
            "You are SagarMitra AI, a multi-agent decision support assistant for Indian coastal fishermen. "
            "Helpfully answer the following general question without invoking spatial datasets:\n"
            "Question: {query}"
        )
        user_query = state["messages"][-1].content
        
        # Use try/except in case OPENAI_API_KEY environment variable is not defined yet
        try:
            llm = ChatOpenAI(temperature=0.2)
            chain = prompt_template | llm
            response = chain.invoke({"query": user_query})
            advice = response.content
        except Exception:
            advice = "Hello! I am SagarMitra AI. I can check weather advisories, geofenced borders, and identify fishing coordinates. Please provide your GPS coordinates to begin safety analysis."
    else:
        # Structured Narrative Consensus Explanation
        prompt_template = ChatPromptTemplate.from_template(
            "You are the Consensus Explainer for SagarMitra AI. "
            "Explain the safety decision to the fisherman clearly and concisely in English.\n\n"
            "SYSTEM DECISION:\n"
            "- Final Risk Level: {final_risk_level}\n"
            "- Primary Reason(s): {override_reasons}\n"
            "- Evidence Log: {evidence_log}\n"
            "- Conflicts Resolved: {conflicts}\n"
            "- Routing Action: {routing_action}\n"
            "- Decision Confidence Score: {confidence}\n"
            "- Data Mode: {data_mode_summary}\n\n"
            "Write a short response explaining why the decision was made, details of the warning if any, and instructions on what to do next. "
            "If confidence is 0.0 or risk is UNKNOWN, warn the fisherman that data is offline and caution must be exercised. "
            "If synthetic data was used, state transparently that this is a simulated fallback forecast."
        )
        
        try:
            llm = ChatOpenAI(temperature=0.0)
            chain = prompt_template | llm
            response = chain.invoke({
                "final_risk_level": final_risk,
                "override_reasons": overrides,
                "evidence_log": evidence,
                "conflicts": state.get("conflicts", []),
                "routing_action": action,
                "confidence": confidence,
                "data_mode_summary": data_mode_summary
            })
            advice = response.content
        except Exception:
            # Fallback formatting for local offline testing
            advice = f"[Offline Fallback State] Risk Level: {final_risk}. Action: {action}. Alert reasons: {overrides}. Confidence: {confidence}."
            if status == "PARTIAL_DATA":
                advice += " Warning: Weather or Ocean forecasts are partially offline."
            if action == "exit_zone":
                advice += " Warning: Turn back immediately to exit restricted waters."
            elif action == "return_to_safe":
                advice += " Warning: Storm conditions detected. Seek harbor."
    
    return {
        "consensus_advice": advice,
        "messages": [AIMessage(content=advice)]
    }


# ==========================================
# 5. Graph Assembly & Routing
# ==========================================

workflow = StateGraph(AgentState)

workflow.add_node("initialize", initialize_node)
workflow.add_node("router", router_node)
workflow.add_node("fetch_data", fetch_data_node)
workflow.add_node("safety_rules", safety_rules_node)
workflow.add_node("routing", routing_node)
workflow.add_node("consensus", consensus_explainer_node)

# Set entry point
workflow.set_entry_point("initialize")
workflow.add_edge("initialize", "router")

# Router conditional fan-out
def route_from_router(state: AgentState) -> Literal["fetch_data", "consensus"]:
    status = state.get("response_status", "SUCCESS")
    if status in ["INSUFFICIENT_INTENT", "INSUFFICIENT_LOCATION"]:
        return "consensus"
        
    reqs = state.get("required_agents", [])
    if not reqs:
        return "consensus"
        
    return "fetch_data"

workflow.add_conditional_edges(
    "router",
    route_from_router,
    {
        "fetch_data": "fetch_data",
        "consensus": "consensus"
    }
)

# Core pipeline transitions
workflow.add_edge("fetch_data", "safety_rules")

# Conditional edge based on routing action
def routing_router_condition(state: AgentState) -> Literal["routing", "consensus"]:
    if state.get("routing_action") in [
        "exit_zone", "return_to_safe", "calculate_route", 
        "preventative_steer_away", "preventative_shelter_route"
    ]:
        return "routing"
    return "consensus"

workflow.add_conditional_edges(
    "safety_rules",
    routing_router_condition,
    {
        "routing": "routing",
        "consensus": "consensus"
    }
)

workflow.add_edge("routing", "consensus")
workflow.add_edge("consensus", END)

# Compile Graph with persistent MemorySaver
memory = MemorySaver()
app = workflow.compile(checkpointer=memory)
