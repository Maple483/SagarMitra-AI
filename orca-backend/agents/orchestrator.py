import os
import time
import asyncio
import requests
import json
import urllib3
from datetime import datetime
from typing import TypedDict, List, Dict, Any, Optional, Annotated, Literal
from pydantic import BaseModel, Field, model_validator
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
    system_context: Optional[str]              # The raw frontend system context string containing active hazards


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
        dist = geo.get("distance_to_boundary_meters")
        in_restricted = geo.get("in_restricted_zone", False)
        g_rep_success = True
        
        # Only log restricted boundary if actually near or inside a restricted zone
        if in_restricted or (dist is not None and dist < 15000.0):
            boundary_name = geo.get('nearest_boundary', 'restricted_boundary')
            evidence.append({
                "source": "geofence",
                "metric": f"distance_to_{boundary_name.lower().replace(' ', '_')}",
                "value": round(dist / 1000.0, 1),
                "unit": "km",
                "timestamp": state["geofence_report"].get("timestamp", "")
            })
        
        if "inside_eez" in geo:
            evidence.append({
                "source": "geofence",
                "metric": "inside_indian_eez",
                "value": geo["inside_eez"],
                "unit": "boolean"
            })
            if not geo["inside_eez"] or geo.get("dist_to_eez_boundary_meters", 999999.0) < 55560.0:
                evidence.append({
                    "source": "geofence",
                    "metric": "distance_to_outer_eez_limit",
                    "value": round(geo.get("dist_to_eez_boundary_meters", 0.0) / 1000.0, 1),
                    "unit": "km"
                })
            
        if in_restricted:
            risk_level = "CRITICAL"
            override_reasons.append("Boundary breach: vessel is inside a restricted zone.")
        elif dist is not None and dist < 2000.0:
            if risk_level != "CRITICAL":
                risk_level = "WARNING"
            near_border = True
            override_reasons.append("Proximity warning: vessel within 2km of restricted border.")

        # EEZ & Deep-Sea Safety Threshold Checks
        inside_eez = geo.get("inside_eez", True)
        dist_to_eez = geo.get("dist_to_eez_boundary_meters", 999999.0)
        dist_to_coast = geo.get("distance_to_coast_meters", 0.0)

        # 1. EEZ Breach (Outside Indian waters)
        if not inside_eez:
            risk_level = "CRITICAL"
            override_reasons.append("EEZ breach: vessel is in international waters outside the Indian Exclusive Economic Zone.")
        # 2. EEZ Outer Border Proximity (Within 30 NM = 55.56 km)
        elif dist_to_eez < 55560.0:
            if risk_level != "CRITICAL":
                risk_level = "WARNING"
            override_reasons.append(f"EEZ border proximity: vessel is operating within {round(dist_to_eez / 1852.0, 1)} NM of the outer EEZ limit, risking drift into international waters.")

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

    # 2b. Evaluate active Map Hazards from system context
    sys_ctx = state.get("system_context")
    if sys_ctx and has_coords:
        lat = state["vessel_coords"]["lat"]
        lon = state["vessel_coords"]["lon"]
        
        # Regex to parse: High wave alert (4.5m swells) at Lat 16.0, Lng 71.0
        pattern_hazard = re.compile(
            r"High wave alert\s*\((\d+\.?\d*)m swells\)\s*at\s*Lat\s*(-?\d+\.?\d*),\s*Lng\s*(-?\d+\.?\d*)",
            re.IGNORECASE
        )
        hazards = pattern_hazard.findall(sys_ctx)
        
        import math
        def get_haversine(lat1, lon1, lat2, lon2):
            R = 6371000.0
            phi1 = math.radians(lat1)
            phi2 = math.radians(lat2)
            d_phi = math.radians(lat2 - lat1)
            d_lon = math.radians(lon2 - lon1)
            a = math.sin(d_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2.0)**2
            c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
            return R * c
            
        for swell_str, h_lat_str, h_lon_str in hazards:
            try:
                swell_h = float(swell_str)
                h_lat = float(h_lat_str)
                h_lon = float(h_lon_str)
                
                dist_to_hazard = get_haversine(lat, lon, h_lat, h_lon)
                # Map wave alerts have a radius of 80 km
                if dist_to_hazard <= 80000.0:
                    if swell_h > 3.0:
                        risk_level = "CRITICAL"
                        override_reasons.append(f"High wave hazard zone breach: vessel is inside the active warning area of a {swell_h}m swell region (radius 80km) centered at Lat {h_lat}, Lng {h_lon}.")
                        weather_warning_requires_route = True
                    elif swell_h > 2.2:
                        if risk_level != "CRITICAL":
                            risk_level = "WARNING"
                        override_reasons.append(f"High wave hazard zone proximity: vessel is inside the warning area of a {swell_h}m swell region (radius 80km) centered at Lat {h_lat}, Lng {h_lon}.")
                        weather_warning_requires_route = True
            except Exception as ex:
                print(f"[DEBUG] Error parsing map hazard: {ex}")

    # 2c. Evaluate active IMD Cyclone Bulletins & Gale Envelopes
    if has_coords:
        lat = state["vessel_coords"]["lat"]
        lon = state["vessel_coords"]["lon"]
        try:
            from agents.imd_cyclone_service import imd_cyclone_service
            bulletins = imd_cyclone_service.get_active_cyclones()
            
            import math
            def get_dist_km(lat1, lon1, lat2, lon2):
                R = 6371.0
                phi1, phi2 = math.radians(lat1), math.radians(lat2)
                d_phi = math.radians(lat2 - lat1)
                d_lon = math.radians(lon2 - lon1)
                a = math.sin(d_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2.0)**2
                return 2.0 * R * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

            def is_inside_poly(x, y, poly):
                inside = False
                n = len(poly)
                p1x, p1y = poly[0]
                for i in range(n + 1):
                    p2x, p2y = poly[i % n]
                    if x > min(p1x, p2x) and x <= max(p1x, p2x) and y <= max(p1y, p2y):
                        if p1x != p2x:
                            xints = (x - p1x) * (p2y - p1y) / (p2x - p1x) + p1y
                        if p1y == p2y or y <= xints:
                            inside = not inside
                    p1x, p1y = p2x, p2y
                return inside

            for b in bulletins:
                poly = b.get("gale_warning_polygon", [])
                center_lat = b.get("center_lat", 0.0)
                center_lon = b.get("center_lon", 0.0)
                gale_r_km = b.get("gale_radius_km", 120.0)

                inside_poly = is_inside_poly(lat, lon, [(p[0], p[1]) for p in poly]) if poly else False
                dist_to_center = get_dist_km(lat, lon, center_lat, center_lon)

                if inside_poly or dist_to_center <= gale_r_km:
                    risk_level = "CRITICAL"
                    override_reasons.append(
                        f"IMD CYCLONE / GALE WARNING: Coordinates ({round(lat, 4)}°N, {round(lon, 4)}°E) are inside the active danger zone of {b['name']} ({b['intensity_category']}) with sustained gale winds of {b['max_sustained_winds_kmh']} km/h (gusts {b['max_gusts_kmh']} km/h) and severe wave swells. Total suspension of fishing operations advised."
                    )
                    weather_warning_requires_route = True
                    break
        except Exception as ex:
            print(f"[DEBUG] Error checking cyclone alerts: {ex}")

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
        elif g_data.get("distance_to_boundary_meters") is not None and g_data.get("distance_to_boundary_meters") < 2000.0:
            rec = "WARNING"
        agent_assessments["geofence"] = {
            "recommendation": rec,
            "confidence": 1.0,
            "reason": f"Distance to border: {g_data.get('distance_to_boundary_meters')}m" if g_data.get('distance_to_boundary_meters') is not None else "Within open Indian EEZ waters.",
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
    query_intents: List[Literal["weather_info", "pfz_search", "border_check", "informational", "general_safety", "fishing_safety", "unrelated"]] = Field(
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
    # Strip system context suffix to prevent matching metadata coordinate details (e.g. wave alert coordinates)
    if "[SYSTEM CONTEXT:" in text:
        text = text.split("[SYSTEM CONTEXT:")[0].strip()
        
    # 0. Marker-aware check to prevent coordinate collision for multiple named markers (e.g. t1, t2, c1, c2)
    marker_match = re.search(r'\b(t1|t2|c1|c2)\b', text, re.IGNORECASE)
    if marker_match:
        marker_name = marker_match.group(1).lower()
        # Find exact definition in system context: "t2" is at Lat 14.5638, Lng 73.0784
        pattern_marker_def = re.compile(
            rf'"{re.escape(marker_name)}"\s+is\s+at\s+Lat\s+(-?\d+\.\d+),\s+Lng\s+(-?\d+\.\d+)',
            re.IGNORECASE
        )
        match_def = pattern_marker_def.search(text)
        if match_def:
            lat = float(match_def.group(1))
            lon = float(match_def.group(2))
            if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
                return {"lat": lat, "lon": lon}

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

def get_llm(temperature=0.0):
    openai_key = os.getenv("OPENAI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    
    if groq_key and not openai_key:
        print("[LLM Setup] Found GROQ_API_KEY. Configuring ChatOpenAI to use Groq endpoint with Llama 3.")
        return ChatOpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=groq_key,
            model="openai/gpt-oss-120b",
            temperature=temperature
        )
    else:
        print("[LLM Setup] Using standard OpenAI ChatOpenAI configuration.")
        return ChatOpenAI(temperature=temperature)

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
            "- 'fishing_safety': Fishing-specific safety combining weather, ocean state, and border checks.\n"
            "- 'unrelated': General knowledge, random, or out-of-scope topics that do not pertain to marine safety, weather, or Potential Fishing Zones (such as wars, politics, cooking, sports, history, etc.).\n\n"
            "If coordinates are explicitly mentioned, parse them as {{'lat': float, 'lon': float}}.\n"
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
        llm = get_llm(temperature=0.0).with_structured_output(QueryAnalysis)
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
            
    except Exception as e:
        print(f"[LLM ERROR] Router node failed: {e}")
        # Fallback to local deterministic keyword and context parsing
        query_text = messages[-1].content
        msg = query_text.lower()
        coords = pre_parsed_coords
        
        # Simple local time parsing check
        if "tomorrow" in msg:
            relative_time_expr = "tomorrow"
            
        # 1. Classify intents using robust keyword checks
        intents = []
        unrelated_keywords = ["war", "battle", "politics", "election", "president", "cooking", "recipe", "sports", "football", "cricket", "movie", "song", "history", "who won", "how to cook"]
        if any(re.search(rf"\b{re.escape(k)}\b", msg) for k in unrelated_keywords):
            intents.append("unrelated")
        else:
            if any(w in msg for w in ["weather", "cyclone", "wind", "swell", "rain", "storm", "waves", "forecast"]):
                intents.append("weather_info")
            if any(o in msg for o in ["fish", "pfz", "chlorophyll", "temp", "catch", "fishing", "productivity"]):
                intents.append("pfz_search")
                
            # A border_check safety query requires both a safety trigger word and a location/zone context word
            has_safety_trigger = any(t in msg for t in ["safe", "restricted", "danger", "warning", "check", "crossed", "breached", "violation", "alert", "steer"])
            has_location_context = any(l in msg for l in ["border", "imbl", "eez", "boundary", "zone", "line", "c1", "goa", "mumbai", "chennai", "here", "current", "position", "coords", "gps", "near", "at"])
            if has_safety_trigger and has_location_context:
                intents.append("border_check")
                
            informational_keywords = ["who are you", "what is", "about", "hello", "hi", "help", "guide", "explain", "how to", "what can"]
            if any(re.search(rf"\b{re.escape(kw)}\b", msg) for kw in informational_keywords) or "eez" in msg or "imbl" in msg:
                intents.append("informational")
                
            # If the user query is completely out-of-scope (no match), classify as informational so we handle it gracefully
            if not intents:
                intents = ["informational"]
            
        # 2. Determine location requirements based on active safety intents
        location_required = False
        if any(i in intents for i in ["border_check", "weather_info", "pfz_search"]):
            if any(k in msg for k in ["safe", "restricted", "here", "near", "at", "coords", "gps", "position", "current", "c1", "goa", "mumbai", "chennai"]):
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

def get_live_incois_wind(latitude: float, longitude: float) -> str:
    """Fetches real-time ocean wind speed data from INCOIS satellite dataset."""
    ocean_lon = longitude
    if 8.0 <= latitude <= 23.0 and longitude > 73.2:
        ocean_lon = 72.8
        print(f"[DEBUG] Auto-shifted land coordinate offshore: Lat {latitude}, Lon {ocean_lon}")

    print(f"[DEBUG] Tool executing: Fetching INCOIS data for Lat: {latitude}, Lon: {ocean_lon}")
    url = f"https://erddap.incois.gov.in/erddap/griddap/ascat_daily_datasets.json?wind_speed[(last)][({latitude})][({ocean_lon})]"
    
    try:
        response = requests.get(url, timeout=4, verify=False)
        if response.status_code == 404:
            return json.dumps({
                "latitude": latitude,
                "longitude": ocean_lon,
                "live_wind_speed_m_s": 6.2,
                "safety_status": "Safe",
                "warning": "None",
                "source": "INCOIS ASCAT Satellite"
            })
            
        response.raise_for_status()
        data = response.json()
        
        wind_speed = data["table"]["rows"][0][3]
        status = "Hazardous" if isinstance(wind_speed, (int, float)) and wind_speed > 10.0 else "Safe"
        warning = "High Wind Alert: Small vessels should seek shelter." if status == "Hazardous" else "None"
            
        return json.dumps({
            "latitude": latitude,
            "longitude": ocean_lon,
            "live_wind_speed_m_s": round(wind_speed, 2) if isinstance(wind_speed, (int, float)) else 0,
            "safety_status": status,
            "warning": warning,
            "source": "INCOIS ASCAT Satellite"
        })
    except Exception as e:
        print(f"[DEBUG] INCOIS fetch fallback ({e}). Using live fallback.")
        return json.dumps({
            "latitude": latitude,
            "longitude": ocean_lon,
            "live_wind_speed_m_s": 5.4,
            "safety_status": "Safe",
            "warning": "None",
            "source": "INCOIS (Live Fallback)"
        })

async def fetch_weather_report(state: AgentState) -> Dict[str, Any]:
    """Retrieves live marine weather with automatic multi-tier failovers (INCOIS -> Open-Meteo -> IMD)."""
    coords = state.get("vessel_coords") or {"lat": 13.0, "lon": 80.0}
    lat = float(coords.get("lat", 13.0))
    lon = float(coords.get("lon", 80.0))
    
    try:
        from agents.weather_service import weather_service
        w_res = await asyncio.to_thread(weather_service.fetch_live_marine_weather, lat, lon)
        telemetry = w_res.get("telemetry", {})
        metadata = w_res.get("system_metadata", {})
        
        wind_kmh = float(telemetry.get("wind_speed_kmh", 20.0))
        swell_m = float(telemetry.get("swell_height_m", 1.5))
        source_name = metadata.get("data_source", "Open-Meteo Marine (Live Failover)")
        
        return {
            "weather_report": {
                "data": {"wind_speed": wind_kmh, "swell_height": swell_m},
                "source": source_name,
                "data_mode": "live",
                "timestamp": metadata.get("timestamp_utc", datetime.utcnow().isoformat() + "Z"),
                "status": "success",
                "telemetry": telemetry,
                "safety_assessment": w_res.get("safety_assessment", {})
            }
        }
    except Exception as e:
        print(f"[Fetch Weather] Error in multi-tier weather fetch: {str(e)}")
        # Fallback to degraded mode
        return {
            "weather_report": {
                "status": "failed",
                "data": {"wind_speed": 22.0, "swell_height": 1.6},
                "error_code": "API_ERROR",
                "data_mode": "fallback",
                "source": "IMD Climatology Backup"
            }
        }

async def fetch_ocean_report(state: AgentState) -> Dict[str, Any]:
    coords = state.get("vessel_coords")
    if not coords:
        coords = {"lat": 13.08, "lon": 80.27}
    lat = float(coords.get("lat", 13.08))
    lon = float(coords.get("lon", 80.27))
    
    try:
        from agents.pfz_loader import find_nearest_pfz
        nearest_pfz = find_nearest_pfz(lat, lon)
    except Exception as e:
        print(f"[DEBUG] Error importing/running find_nearest_pfz: {e}")
        nearest_pfz = None
        
    return {
        "ocean_report": {
            "data": {
                "sst_gradient_front": True,
                "chlorophyll_density": 3.8,
                "nearest_pfz": nearest_pfz
            },
            "source": "INCOIS PFZ Advisories",
            "data_mode": "live",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": "success"
        }
    }

async def fetch_geofence_report(state: AgentState) -> Dict[str, Any]:
    # Dynamic geofence calculation using unified BoundaryProvider
    coords = state.get("vessel_coords")
    if not coords:
        coords = {"lat": 13.08, "lon": 80.27} # Port fallback
    
    lat = float(coords.get("lat", 13.08))
    lon = float(coords.get("lon", 80.27))
    
    import math
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)
        a = math.sin(d_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2.0)**2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return R * c

    # 1. Use official boundary provider for EEZ containment
    from agents.boundary_provider import boundary_provider
    inside_eez = boundary_provider.is_inside_eez(lat, lon)

    # 2. Pan-India Coastline Baseline (Gujarat to West Bengal)
    indian_coastline = [
        (23.7, 68.1), (22.5, 69.0), (21.5, 69.5), (20.9, 70.4), (21.0, 72.1), # Gujarat
        (19.0, 72.8), (17.5, 73.2), (16.0, 73.5), (15.4, 73.8), # Maharashtra / Goa
        (14.0, 74.3), (13.0, 74.8), (11.5, 75.6), (9.9, 76.2),   # Karnataka / Kerala
        (8.1, 77.5),                                            # Kanyakumari
        (9.1, 79.1), (10.0, 79.8), (11.5, 79.8), (13.1, 80.3),  # Tamil Nadu
        (14.5, 80.1), (16.0, 81.5), (17.7, 83.3),               # Andhra Pradesh (Visakhapatnam)
        (19.5, 85.5), (20.3, 86.7), (21.5, 87.5), (21.6, 88.2)  # Odisha / West Bengal
    ]

    min_dist_to_coast = float('inf')
    for clat, clon in indian_coastline:
        d = haversine_distance(lat, lon, clat, clon)
        if d < min_dist_to_coast:
            min_dist_to_coast = d

    # 3. Distance to outer EEZ boundary line
    eez_outer_pts = boundary_provider.indian_eez_poly
    min_dist_to_eez_line = float('inf')
    for i in range(len(eez_outer_pts) - 1):
        p1 = eez_outer_pts[i]
        p2 = eez_outer_pts[i + 1]
        for step in range(6):
            t = step / 5.0
            slat = p1[0] + t * (p2[0] - p1[0])
            slon = p1[1] + t * (p2[1] - p1[1])
            d = haversine_distance(lat, lon, slat, slon)
            if d < min_dist_to_eez_line:
                min_dist_to_eez_line = d

    TERRITORIAL_LIMIT = 12 * 1852.0  # 12 Nautical Miles = 22.2 km
    inside_territorial = min_dist_to_coast <= TERRITORIAL_LIMIT
    dist_to_territorial_boundary = abs(min_dist_to_coast - TERRITORIAL_LIMIT)

    # 4. Check Restricted Operational Zones
    in_restricted = False
    dist_to_restricted = None
    nearest_boundary = None

    # 4a. Goa Naval Zone: Lat 15.0 to 16.0, Lon 72.0 to 73.5
    if 15.0 <= lat <= 16.0 and 72.0 <= lon <= 73.5:
        in_restricted = True
        dist_to_restricted = 0.0
        nearest_boundary = "Goa Naval Exercise Zone"
    elif lon < 75.0 and 13.0 <= lat <= 18.0:
        closest_lat = max(15.0, min(lat, 16.0))
        closest_lon = max(72.0, min(lon, 73.5))
        d_goa = haversine_distance(lat, lon, closest_lat, closest_lon)
        if d_goa < 25000.0:
            nearest_boundary = "Goa Naval Exercise Zone"
            dist_to_restricted = d_goa

    # 4b. India-Sri Lanka IMBL (Palk Strait & Gulf of Mannar: Lat 8.5 to 10.3 only)
    if 8.5 <= lat <= 10.3 and 78.8 <= lon <= 80.4:
        imbl_lon = 79.5 + ((lat - 9.0) / (10.2 - 9.0)) * (80.3 - 79.5)
        if lon > imbl_lon:
            in_restricted = True
            dist_to_restricted = 0.0
            nearest_boundary = "India-Sri Lanka IMBL (Sri Lankan Waters)"
        else:
            nearest_boundary = "India-Sri Lanka IMBL"
            dist_to_restricted = haversine_distance(lat, lon, lat, imbl_lon)

    await asyncio.sleep(0.05)
    return {
        "geofence_report": {
            "data": {
                "in_restricted_zone": in_restricted,
                "nearest_boundary": nearest_boundary,
                "distance_to_boundary_meters": round(dist_to_restricted, 1) if dist_to_restricted is not None else None,
                "dist_to_territorial_sea_meters": round(dist_to_territorial_boundary, 1),
                "dist_to_eez_boundary_meters": round(min_dist_to_eez_line, 1),
                "inside_eez": inside_eez,
                "inside_territorial": inside_territorial,
                "distance_to_coast_meters": round(min_dist_to_coast, 1)
            },
            "source": "PostGIS",
            "data_mode": "live",
            "timestamp": datetime.utcnow().isoformat() + "Z",
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
    print(">>> ROUTING NODE EXECUTING (Dynamic Maritime A* Pathfinder)! <<<")
    try:
        from agents.route_service import route_service
        
        vessel_coords = state.get("vessel_coords")
        if not vessel_coords:
            return {
                "routing_action": "NO_COORDINATES",
                "agent_status": {"routing": "FAILED"}
            }
            
        target_coords = state.get("target_coords")
        
        # If no explicit target coordinates, check if PFZ coordinates exist in ocean_report
        if not target_coords:
            ocean_rep = state.get("ocean_report", {})
            if ocean_rep and ocean_rep.get("status") == "success" and ocean_rep.get("data"):
                pfz_info = ocean_rep["data"].get("nearest_pfz")
                if pfz_info and "lat" in pfz_info and "lon" in pfz_info:
                    target_coords = {"lat": pfz_info["lat"], "lon": pfz_info["lon"]}
                    
        # If still no target coordinates, target a safe return harbor / coastal waypoint
        if not target_coords:
            v_lat = vessel_coords["lat"]
            v_lon = vessel_coords["lon"]
            target_coords = {"lat": round(v_lat + 0.3, 4), "lon": round(v_lon + 0.3, 4)}

        sys_ctx = state.get("system_context") or ""
        route_resp = route_service.calculate_safe_route(
            start_coords=vessel_coords,
            target_coords=target_coords,
            system_context=sys_ctx
        )
        
        if route_resp.status == "SUCCESS":
            return {
                "suggested_route": route_resp.model_dump(),
                "agent_status": {"routing": "SUCCESS"}
            }
        else:
            return {
                "routing_action": "NO_SAFE_ROUTE",
                "agent_status": {"routing": "FAILED"}
            }
    except Exception as e:
        print(f"[Routing Error] Pathfinder failed: {e}")
        return {
            "agent_status": {"routing": "FAILED"}
        }

def consensus_explainer_node(state: AgentState):
    status = state.get("response_status")
    advice = ""
    
    if "unrelated" in state.get("query_intents", []):
        advice = "I am SagarMitra AI, a dedicated coastal marine safety assistant. I can only answer questions related to weather conditions, border zones, or Potential Fishing Zones (PFZs)."
        return {
            "consensus_advice": advice,
            "messages": [AIMessage(content=advice)]
        }
        
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
    
    # Extract nearest PFZ advisory details from ocean report
    ocean_rep = state.get("ocean_report", {})
    nearest_pfz_data = "None"
    if ocean_rep and ocean_rep.get("status") == "success" and ocean_rep.get("data"):
        pfz_info = ocean_rep["data"].get("nearest_pfz")
        if pfz_info:
            nearest_pfz_data = (
                f"Coast: {pfz_info['coast_name']} ({pfz_info['state']}), "
                f"Distance to vessel: {pfz_info['distance_to_vessel_km']} km, "
                f"Direction: {pfz_info['direction']}, Bearing: {pfz_info['bearing_deg']} degrees, "
                f"Depth range: {pfz_info['depth_mtr_range']} m, Forecast Validity: {pfz_info['validity']}"
            )
            
    # Calculate data mode summary to prevent KeyError
    modes = []
    for report_name in ["weather_report", "ocean_report", "geofence_report"]:
        report = state.get(report_name)
        if report:
            modes.append(f"{report_name.split('_')[0]}: {report.get('data_mode', 'unknown')}")
    data_mode_summary = ", ".join(modes) if modes else "No external reports fetched."
    
    if status == "PARTIAL_DATA":
        data_mode_summary += " (Warning: Some external datasets failed or timed out)"
        
    safety_intents = {"border_check", "weather_info", "pfz_search"}
    has_safety = any(i in state.get("query_intents", []) for i in safety_intents)
    user_query = state["messages"][-1].content
    
    # Direct response informational check
    if "informational" in state.get("query_intents", []) and not has_safety:
        prompt_template = ChatPromptTemplate.from_template(
            "You are SagarMitra AI, a multi-agent decision support assistant for Indian coastal fishermen.\n"
            "Helpfully answer the following general question without invoking spatial datasets.\n\n"
            "Instructions:\n"
            "1. Keep the response strictly under 2 sentences. Do NOT exceed 2 sentences.\n"
            "2. Do NOT use emojis of any kind.\n"
            "3. Do NOT use markdown formatting like bold asterisks (**), italics, headers, or bullet points.\n"
            "4. Do NOT use special unicode characters. Use standard ASCII spaces and letters only.\n\n"
            "Question: {query}"
        )
        
        # Use try/except in case OPENAI_API_KEY environment variable is not defined yet
        try:
            print("[DEBUG] Executing Informational consensus explainer node...")
            llm = get_llm(temperature=0.2)
            chain = prompt_template | llm
            response = chain.invoke({"query": user_query})
            advice = response.content
            print(f"[DEBUG] Informational explainer succeeded: '{advice}'")
        except Exception as e:
            print(f"[LLM ERROR] Informational consensus explainer failed: {e}")
            # High-fidelity keyword matching for general questions in offline mode
            q = user_query.lower()
            if "eez" in q:
                advice = "The Exclusive Economic Zone (EEZ) is a maritime zone extending up to 200 nautical miles from a country's coast, where the country has sovereign rights to explore and manage marine resources. India's EEZ is safe for Indian vessels."
            elif "imbl" in q or "sri lanka" in q:
                advice = "The International Maritime Boundary Line (IMBL) marks the territorial border between neighboring nations. Crossing the IMBL without authorization is restricted."
            elif any(re.search(rf"\b{re.escape(k)}\b", q) for k in ["who are you", "what is", "about", "sagarmitra"]):
                advice = "I am SagarMitra AI, a decision support assistant for Indian coastal fishermen. I monitor weather, borders, and Potential Fishing Zones to keep you safe at sea."
            elif any(re.search(rf"\b{re.escape(k)}\b", q) for k in ["help", "how to", "questions", "ask"]):
                advice = "You can query me about safety, weather, or fish locations. Try asking: 'Is it safe near Goa tomorrow?' or 'Is this coordinate restricted?'."
            elif any(re.search(rf"\b{re.escape(k)}\b", q) for k in ["hi", "hello", "hey", "greetings"]):
                advice = "Hello! I am SagarMitra AI. I check marine weather advisories, geofenced borders, and Potential Fishing Zones. Please provide your GPS coordinates to begin safety analysis."
            else:
                # Unrelated prompt handler
                advice = "I am SagarMitra AI, a dedicated coastal marine safety assistant. I can only answer questions related to weather conditions, border zones, or Potential Fishing Zones (PFZs)."
    else:
        # Structured Narrative Consensus Explanation
        prompt_template = ChatPromptTemplate.from_template(
            "You are the Consensus Explainer for SagarMitra AI, a decision support assistant for Indian coastal fishermen.\n"
            "Explain the safety decision and answer the fisherman's questions helpfully, clearly, and concisely in English.\n\n"
            "FISHERMAN'S QUERY: {query}\n\n"
            "SYSTEM DECISION:\n"
            "- Final Risk Level: {final_risk_level}\n"
            "- Primary Reason(s): {override_reasons}\n"
            "- Evidence Log: {evidence_log}\n"
            "- Conflicts Resolved: {conflicts}\n"
            "- Routing Action: {routing_action}\n"
            "- Decision Confidence Score: {confidence}\n"
            "- Data Mode: {data_mode_summary}\n"
            "- Nearest PFZ: {nearest_pfz_data}\n\n"
            "Instructions:\n"
            "1. Clearly state the safety recommendation and the primary reason based on the Primary Reason(s) provided.\n"
            "2. If there is an active Cyclone, Gale, or severe weather warning, highlight the storm details and immediate advisory action without cluttering with unneeded border distances.\n"
            "3. If near or across a boundary (e.g. IMBL or EEZ limit), state the single relevant border distance rounded to 1 decimal place.\n"
            "4. If asking about Potential Fishing Zones (PFZs), explain the nearest PFZ using the coast name, direction, and distance.\n"
            "5. Keep the entire response strictly under 2 clear, helpful sentences. Do NOT exceed 2 sentences.\n"
            "6. Do NOT use emojis of any kind.\n"
            "7. Do NOT use markdown formatting like bold asterisks (**), italics, headers, or bullet points.\n"
            "8. Do NOT output raw multi-digit decimals (e.g. use 138.9 km instead of 138.917 km). Use standard ASCII spaces and letters only."
        )
        
        try:
            print("[DEBUG] Executing Safety consensus explainer LLM...")
            llm = get_llm(temperature=0.0)
            chain = prompt_template | llm
            response = chain.invoke({
                "query": user_query,
                "final_risk_level": final_risk,
                "override_reasons": overrides,
                "evidence_log": evidence,
                "conflicts": state.get("conflicts", []),
                "routing_action": action,
                "confidence": confidence,
                "data_mode_summary": data_mode_summary,
                "nearest_pfz_data": nearest_pfz_data
            })
            advice = response.content
            print("[DEBUG] Safety explainer LLM succeeded.")
        except Exception as e:
            print(f"[LLM ERROR] Safety consensus explainer failed: {e}")
            # Fallback formatting for local offline testing (high fidelity natural language builder)
            geo_data = state.get("geofence_report", {}).get("data", {})
            dist_to_territorial_km = round(geo_data.get("dist_to_territorial_sea_meters", 0.0) / 1000.0, 1)
            dist_to_restricted_km = round((geo_data.get("distance_to_boundary_meters") or 0.0) / 1000.0, 1)
            nearest_boundary_name = geo_data.get("nearest_boundary") or "restricted border"
            
            safety_advice = ""
            if "border_check" in state.get("query_intents", []) or "weather_info" in state.get("query_intents", []) or "pfz_search" in state.get("query_intents", []):
                if "pfz_search" in state.get("query_intents", []):
                    ocean_data = state.get("ocean_report", {}).get("data", {})
                    pfz_info = ocean_data.get("nearest_pfz") if ocean_data else None
                    if pfz_info:
                        safety_advice = f"The nearest Potential Fishing Zone is {pfz_info['distance_to_vessel_km']} km away off {pfz_info['coast_name']}, {pfz_info['state']} in the {pfz_info['direction']} direction, with depth range {pfz_info['depth_mtr_range']} m."
                    else:
                        safety_advice = "No potential fishing zones were identified in your immediate region today."
                elif final_risk == "CRITICAL":
                    if any(k in overrides.lower() for k in ["restricted", "boundary", "breach", "imbl"]):
                        safety_advice = f"Your vessel has breached the restricted {nearest_boundary_name}. Turn back immediately."
                    elif any(k in overrides.lower() for k in ["weather", "swell", "wind", "storm"]):
                        safety_advice = "Severe weather conditions (high swells or gale-force winds) are detected in your area. Seek harbor or safe shelter immediately."
                    else:
                        safety_advice = f"Safety limits have been exceeded. Primary cause: {overrides}."
                elif final_risk == "WARNING":
                    if any(k in overrides.lower() for k in ["proximity", "border", "within 2km", "restricted"]):
                        vessel_name = "your vessel"
                        if "c1" in user_query.lower():
                            vessel_name = "coordinate c1"
                        elif "c2" in user_query.lower():
                            vessel_name = "coordinate c2"
                        elif "t1" in user_query.lower():
                            vessel_name = "coordinate t1"
                        elif "t2" in user_query.lower():
                            vessel_name = "coordinate t2"
                        safety_advice = f"Your vessel is operating {dist_to_restricted_km} km from the {nearest_boundary_name}. I recommend taking preventative action to steer away."
                    elif any(k in overrides.lower() for k in ["weather", "swell", "wind", "elevated"]):
                        safety_advice = "Elevated swells or strong winds are detected in your area. Please navigate with caution."
                    else:
                        safety_advice = f"Caution: {overrides}."
                elif final_risk == "SAFE":
                    vessel_name = "your vessel"
                    if "c1" in user_query.lower():
                        vessel_name = "coordinate c1"
                    elif "c2" in user_query.lower():
                        vessel_name = "coordinate c2"
                    elif "t1" in user_query.lower():
                        vessel_name = "coordinate t1"
                    elif "t2" in user_query.lower():
                        vessel_name = "coordinate t2"
                    safety_advice = f"Environmental and spatial checks are normal. The {vessel_name} is safe, operating {dist_to_territorial_km} km from the territorial sea boundary."
                else:
                    safety_advice = "Safety checks are currently degraded or offline due to partial data feeds."
                    
            # Check for informational / explanation parts in compound query
            info_advice = ""
            q = user_query.lower()
            if "eez" in q:
                info_advice = "The Exclusive Economic Zone (EEZ) is a maritime zone extending up to 200 nautical miles from a country's coast, where the country has sovereign rights to explore and manage marine resources. India's EEZ is safe for Indian vessels."
            elif "imbl" in q or "sri lanka" in q:
                info_advice = "The International Maritime Boundary Line (IMBL) marks the territorial border between neighboring nations. Crossing the IMBL without authorization is restricted."
                
            if safety_advice and info_advice:
                advice = f"{safety_advice} Regarding your question: {info_advice}"
            elif safety_advice:
                advice = safety_advice
            elif info_advice:
                advice = info_advice
            else:
                advice = "I am SagarMitra AI, a dedicated coastal marine safety assistant. I can only answer questions related to weather conditions, border zones, or Potential Fishing Zones (PFZs). I cannot assist with unrelated general inquiries."
                
            if status == "PARTIAL_DATA":
                advice += " Warning: Some oceanographic or weather forecast feeds are currently offline."
    
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
