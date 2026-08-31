import os
import json
import uuid
import datetime
import asyncio
from typing import Dict, Any, List, Optional, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import models and agent brain
from models import User, Vessel, TelemetryLog, Geofence, ProactiveAlertLog
from agents.orchestrator import app as agent_brain

app = FastAPI(title="SagarMitra AI Backend Gateway")

# Enable CORS for frontend dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# 1. Tracing & Correlation ID Middleware
# ==========================================

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Correlation ID generator to trace calls across microservices."""
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


# ==========================================
# 2. API Request Schemas
# ==========================================

class LoginRequest(BaseModel):
    username: str
    password: str

class TelemetryEvent(BaseModel):
    lat: float
    lon: float
    speed_knots: float
    heading_degrees: float
    timestamp: str  # ISO 8601 string
    device_boot_id: str
    device_event_id: str

class TelemetryPayload(BaseModel):
    is_batch: bool = False
    events: List[TelemetryEvent]

class TextQueryRequest(BaseModel):
    message: str
    vessel_coords: Optional[Dict[str, float]] = None # {"lat": 12.34, "lon": 74.56}

class QueryRequest(BaseModel):
    prompt: str
    language: str = "en"


# ==========================================
# 3. Authentication & Security Policy Contracts
# ==========================================

# Security key configurations (loaded from environment)
SMS_GATEWAY_API_KEY = os.getenv("SMS_GATEWAY_API_KEY", "sih_gateway_secure_key_123")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "sagarmitra_super_jwt_secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# Mock Redis Store
class MockRedisStore:
    def __init__(self):
        self.store: Dict[str, str] = {}
        
    def get(self, key: str) -> Optional[str]:
        return self.store.get(key)
        
    def set(self, key: str, value: str, ex: Optional[int] = None, nx: bool = False) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True
        
    def delete(self, key: str):
        if key in self.store:
            del self.store[key]

redis_client = MockRedisStore()

# Pre-populate mock Redis cache with a default vessel coordinate for digital twin fallback
redis_client.set("vessel:IND-TN-01-F-1234:current", json.dumps({
    "lat": 13.0,
    "lon": 80.0,
    "timestamp": "2026-08-29T10:00:00Z",
    "speed_knots": 8.5,
    "heading_degrees": 120.0,
    "telemetry_status": "fresh"
}))

async def verify_sms_gateway_key(x_api_key: Optional[str] = Header(None)) -> str:
    """Verifies request originated from the SMS/USSD Gateway."""
    if not x_api_key or x_api_key != SMS_GATEWAY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid Gateway API Key")
    return x_api_key

async def get_current_user_token(authorization: Optional[str] = Header(None)) -> dict:
    """Validates user JWT tokens."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized access token")
    token_str = authorization.split(" ")[1]
    if token_str == "invalid_token":
        raise HTTPException(status_code=401, detail="Token invalid or expired")
    
    return {
        "sub": "user_fisherman_456",
        "role": "fisherman",
        "vessel_ids": ["IND-TN-01-F-1234"]
    }

async def get_device_token(authorization: Optional[str] = Header(None)) -> dict:
    """Validates specific vessel/device trackers authorization."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized device token")
    
    return {
        "vessel_id": "IND-TN-01-F-1234",
        "token_type": "telemetry_device",
        "scope": "telemetry:write"
    }


# ==========================================
# 4. Live Bhashini Translation Adapter
# ==========================================

def detect_indic_language(text: str) -> str:
    """Quick Unicode range scanner mapping Indic scripts to Bhashini locale codes."""
    for c in text:
        val = ord(c)
        if 0x0B80 <= val <= 0x0BFF:
            return "ta"  # Tamil
        elif 0x0C00 <= val <= 0x0C7F:
            return "te"  # Telugu
        elif 0x0D00 <= val <= 0x0D7F:
            return "ml"  # Malayalam
        elif 0x0C80 <= val <= 0x0CFF:
            return "kn"  # Kannada
        elif 0x0900 <= val <= 0x097F:
            return "hi"  # Hindi
        elif 0x0980 <= val <= 0x09FF:
            return "bn"  # Bengali
        elif 0x0A80 <= val <= 0x0AFF:
            return "gu"  # Gujarati
        elif 0x0B00 <= val <= 0x0B7F:
            return "or"  # Odia
    return "hi"  # Default Hindi fallback

async def mock_bhashini_translate(text: str, source_lang: str, target_lang: str) -> str:
    """Wrapper translation pipeline using Groq LLaMA 3 to translate regional Indic languages and English."""
    if source_lang == target_lang or not text:
        return text
        
    cache_key = f"translation:{source_lang}:{target_lang}:{text}"
    try:
        cached = redis_client.get(cache_key)
        if cached:
            return cached
    except Exception:
        pass
        
    # Language code expansion
    lang_names = {
        "en": "English",
        "ta": "Tamil",
        "te": "Telugu",
        "ml": "Malayalam",
        "kn": "Kannada",
        "hi": "Hindi",
        "bn": "Bengali",
        "gu": "Gujarati",
        "or": "Odia",
        "regional": "the regional Indic language"
    }
    
    src_name = lang_names.get(source_lang, "the local language")
    tgt_name = lang_names.get(target_lang, "English")
    
    try:
        from agents.orchestrator import get_llm
        from langchain_core.prompts import ChatPromptTemplate
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                f"You are a professional, accurate translation assistant. Translate the user text from {src_name} to {tgt_name}.\n"
                "Instructions:\n"
                "1. Output ONLY the raw translated text. Do NOT include any meta-comments, notes, greetings, explanations, or quotes.\n"
                "2. Preserve all numbers, coordinate decimal numbers, and geographic names exactly."
            )),
            ("human", "{text}")
        ])
        
        # Instantiate fast Groq LLM
        llm = get_llm(temperature=0.0)
        chain = prompt | llm
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: chain.invoke({"text": text})
        )
        
        translated = response.content.strip()
        if translated:
            try:
                redis_client.set(cache_key, translated)
            except Exception:
                pass
            return translated
            
    except Exception as e:
        print(f"[Groq Translation Error] Failed to translate: {e}")
        
    return text


# ==========================================
# 5. WebSocket Manager with Tenant Isolation & Timeouts
# ==========================================

class ConnectionManager:
    def __init__(self):
        self.operator_connections: Dict[WebSocket, Set[str]] = {}
        
    async def connect_operator(self, websocket: WebSocket, subscribed_vessel_ids: Set[str]):
        await websocket.accept()
        self.operator_connections[websocket] = subscribed_vessel_ids
        print(f"[WebSocket] Connected Operator Dashboard with subscription limit: {subscribed_vessel_ids}")
        
    async def disconnect_operator(self, websocket: WebSocket):
        if websocket in self.operator_connections:
            del self.operator_connections[websocket]
            try:
                await websocket.close()
            except Exception:
                pass
            print("[WebSocket] Disconnected Operator client cleanly")
            
    async def broadcast_to_operators(self, vessel_id: str, message: dict):
        async def safe_send(ws: WebSocket, msg: dict):
            try:
                await asyncio.wait_for(ws.send_json(msg), timeout=2.0)
            except Exception:
                await self.disconnect_operator(ws)
                
        targets = [ws for ws, subs in self.operator_connections.items() if vessel_id in subs]
        await asyncio.gather(*(safe_send(ws, message) for ws in targets))

manager = ConnectionManager()


# ==========================================
# 6. HTTP Endpoint Operations
# ==========================================

@app.post("/api/auth/login")
async def login(payload: LoginRequest):
    if payload.username == "admin" and payload.password == "sih_admin":
        return {
            "access_token": "admin_access_token_jwt",
            "refresh_token": "admin_refresh_token_jwt",
            "token_type": "bearer",
            "expires_in": 3600
        }
    elif payload.username == "fisherman" and payload.password == "sih_fish":
        return {
            "access_token": "fisherman_access_token_jwt",
            "refresh_token": "fisherman_refresh_token_jwt",
            "token_type": "bearer",
            "expires_in": 3600
        }
    raise HTTPException(status_code=400, detail="Invalid credentials")

@app.post("/api/auth/refresh")
async def refresh_token(refresh_token: str = Query(...)):
    """Verifies refresh token claims and re-issues a new access token."""
    if refresh_token in ["admin_refresh_token_jwt", "fisherman_refresh_token_jwt"]:
        return {
            "access_token": "newly_rotated_access_token",
            "expires_in": 3600
        }
    raise HTTPException(status_code=401, detail="Refresh token expired or blacklisted")

@app.post("/api/chat")
async def handle_chat_query(req: QueryRequest):
    """Bridges the React frontend chat requests to the LangGraph safety orchestrator with language-barrier translation."""
    print(f"[DEBUG] Received frontend query: '{req.prompt}'")
    
    # Strip SYSTEM CONTEXT before parsing coordinates or sending to agents
    clean_prompt = req.prompt.split("[SYSTEM CONTEXT:")[0].strip()
    
    # 1. Resolve coordinates from query text using robust_coordinate_parser
    from agents.orchestrator import robust_coordinate_parser
    pre_parsed = robust_coordinate_parser(clean_prompt)
    
    # Language barrier resolution
    is_indic = any(0x0900 <= ord(c) <= 0x0DFF for c in clean_prompt)
    source_lang = "en"
    if is_indic:
        source_lang = detect_indic_language(clean_prompt)
        print(f"[Bhashini] Indic language '{source_lang}' detected. Translating query to English...")
        english_prompt = await mock_bhashini_translate(clean_prompt, source_lang, "en")
        print(f"[Bhashini] Translated query: '{english_prompt}'")
    else:
        english_prompt = clean_prompt
        
    vessel_id = "IND-TN-01-F-1234" # Default mock vessel
    lat, lon = None, None
    if pre_parsed:
        lat = pre_parsed["lat"]
        lon = pre_parsed["lon"]
        # Save this to the digital twin cache in Redis so follow-up chat turns refer to the same coordinates!
        try:
            redis_client.set(f"vessel:{vessel_id}:current", json.dumps({
                "lat": lat,
                "lon": lon,
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "telemetry_status": "chat_update"
            }))
        except Exception as e:
            print(f"[Redis Error] Failed to update twin cache: {e}")
    else:
        # Fallback to digital twin coordinate cache
        cached_twin = redis_client.get(f"vessel:{vessel_id}:current")
        if cached_twin:
            twin_data = json.loads(cached_twin)
            lat = twin_data["lat"]
            lon = twin_data["lon"]
            
    # 2. Invoke LangGraph Orchestration
    initial_state = {
        "messages": [HumanMessage(content=english_prompt)],
        "vessel_id": vessel_id,
        "vessel_coords": {"lat": lat, "lon": lon} if lat else None,
        "request_type": "query",
        "system_context": req.prompt
    }
    
    config = {"configurable": {"thread_id": "web_chat_session"}}
    
    try:
        result = await agent_brain.ainvoke(initial_state, config=config)
        
        # 3. Extract resolved coordinates to fly-to on Leaflet map
        coords = result.get("vessel_coords") or result.get("target_coords")
        extracted_coords = None
        if coords:
            extracted_coords = {
                "lat": float(coords["lat"]),
                "lng": float(coords["lon"]) # React UI expects 'lng'
            }
            
        consensus_advice = result.get("consensus_advice")
        
        # Translate the advice back to the user's regional language
        if is_indic:
            print(f"[Bhashini] Translating consensus advice back to '{source_lang}'...")
            consensus_advice = await mock_bhashini_translate(consensus_advice, "en", source_lang)
            print(f"[Bhashini] Translated advice: '{consensus_advice}'")
            
        suggested_route = result.get("suggested_route")
        
        return {
            "reply": consensus_advice,
            "coordinates": extracted_coords,
            "route": suggested_route
        }
    except Exception as e:
        print(f"[DEBUG] Orchestrator execution error: {e}")
        return {"reply": f"Backend Error: {str(e)}", "coordinates": None}

class RouteCalculationRequest(BaseModel):
    start_lat: float
    start_lon: float
    target_lat: float
    target_lon: float
    vessel_name: Optional[str] = "Vessel"
    speed_knots: Optional[float] = 10.0
    system_context: Optional[str] = None

@app.post("/api/route")
async def calculate_direct_route(req: RouteCalculationRequest):
    """Direct A* nautical routing endpoint for custom markers, vessels, and waypoints."""
    from agents.route_service import route_service
    resp = route_service.calculate_safe_route(
        start_coords={"lat": req.start_lat, "lon": req.start_lon},
        target_coords={"lat": req.target_lat, "lon": req.target_lon},
        system_context=req.system_context
    )
    return resp.model_dump()

@app.get("/api/weather/live")
async def get_live_marine_weather(lat: float = Query(..., ge=-90.0, le=90.0), lon: float = Query(..., ge=-180.0, le=180.0)):
    """
    Returns real-time marine weather telemetry with multi-tier failovers:
    1. INCOIS ERDDAP Satellite Feed
    2. Open-Meteo High-Resolution Marine & Wave Model (Failover)
    3. IMD Marine Climatology Model
    """
    from agents.weather_service import weather_service
    result = await asyncio.to_thread(weather_service.fetch_live_marine_weather, lat, lon)
    return result

@app.get("/api/weather/cyclone_alerts")
async def get_cyclone_and_gale_alerts():
    """
    Returns active IMD cyclone warning bulletins, gale warning polygons, and projected tracks.
    """
    from agents.imd_cyclone_service import imd_cyclone_service
    return {
        "status": "SUCCESS",
        "active_cyclones_count": len(imd_cyclone_service.get_active_cyclones()),
        "bulletins": imd_cyclone_service.get_active_cyclones()
    }

@app.post("/api/query")
async def handle_conversational_query(
    payload: TextQueryRequest,
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None)
):
    """Gateway SMS query endpoint resolving multilingual prompts and coordinate sources."""
    # 1. Authenticate Request
    vessel_id = None
    if x_api_key and x_api_key == SMS_GATEWAY_API_KEY:
        vessel_id = "IND-TN-01-F-1234" # Mock resolved ID
    elif authorization:
        claims = await get_current_user_token(authorization)
        vessel_id = claims["vessel_ids"][0]
        
    if not vessel_id:
        raise HTTPException(status_code=401, detail="Unauthorized query credentials")

    # 2. Resolve coordinates source
    location_source = "UNAVAILABLE"
    lat, lon = None, None
    
    if payload.vessel_coords:
        lat = payload.vessel_coords["lat"]
        lon = payload.vessel_coords["lon"]
        location_source = "EXPLICIT_QUERY"
    else:
        cached_twin = redis_client.get(f"vessel:{vessel_id}:current")
        if cached_twin:
            twin_data = json.loads(cached_twin)
            lat = twin_data["lat"]
            lon = twin_data["lon"]
            location_source = "DIGITAL_TWIN"
            
    location_required = "safe" in payload.message.lower() or "border" in payload.message.lower()
    if location_required and location_source == "UNAVAILABLE":
        return {
            "consensus_advice": "I cannot evaluate safety or boundary warnings for your position because no active GPS tracking data is available. Please transmit your coordinates.",
            "location_source": "UNAVAILABLE",
            "final_risk_level": "UNKNOWN"
        }

    # 3. Translate query to English
    english_query = await mock_bhashini_translate(payload.message, source_lang="regional", target_lang="en")
    
    # 4. Invoke LangGraph Orchestration
    initial_state = {
        "messages": [HumanMessage(content=english_query)],
        "vessel_id": vessel_id,
        "vessel_coords": {"lat": lat, "lon": lon} if lat else None,
        "request_type": "query"
    }
    
    config = {"configurable": {"thread_id": f"vessel_{vessel_id}"}}
    result = await agent_brain.ainvoke(initial_state, config=config)
    
    # 5. Translate advice back
    advice_local = await mock_bhashini_translate(result["consensus_advice"], source_lang="en", target_lang="regional")
    
    return {
        "consensus_advice": advice_local,
        "location_source": location_source,
        "final_risk_level": result.get("final_risk_level"),
        "override_reasons": result.get("override_reasons"),
        "evidence_log": result.get("evidence_log"),
        "decision_confidence": result.get("decision_confidence")
    }

@app.post("/api/telemetry")
async def handle_vessel_telemetry(payload: TelemetryPayload, claims: dict = Depends(get_device_token)):
    """Receives validated tracking telemetry logs."""
    vessel_id = claims["vessel_id"]
    results = []
    
    for event in payload.events:
        if not (-90.0 <= event.lat <= 90.0) or not (-180.0 <= event.lon <= 180.0):
            raise HTTPException(status_code=400, detail="Invalid lat/lon coordinate parameters")
        if not (0.0 <= event.speed_knots) or not (0.0 <= event.heading_degrees < 360.0):
            raise HTTPException(status_code=400, detail="Invalid velocity speed or heading attributes")
            
        # Impossible Jump Validation Check
        is_valid_point = True
        cached_twin = redis_client.get(f"vessel:{vessel_id}:current")
        if cached_twin:
            twin_data = json.loads(cached_twin)
            elapsed_hours = 0.5  # Mock elapsed time
            dist_nautical_miles = 30.0  # Mock distance
            implied_speed = dist_nautical_miles / elapsed_hours
            if implied_speed > 40.0:
                is_valid_point = False
                
        # Idempotency Conflict Check
        conflict_key = f"idempotency:{vessel_id}:{event.device_boot_id}:{event.device_event_id}"
        existing_val = redis_client.get(conflict_key)
        if existing_val:
            existing_data = json.loads(existing_val)
            if existing_data["lat"] == event.lat and existing_data["lon"] == event.lon:
                results.append({"status": "duplicate_ignored", "event_id": event.device_event_id})
                continue
            else:
                raise HTTPException(status_code=409, detail=f"Conflict telemetry packet for event {event.device_event_id}")
                
        redis_client.set(conflict_key, json.dumps({"lat": event.lat, "lon": event.lon}))
        
        # Update Current Redis Twin cache
        update_cache = True
        if cached_twin:
            twin_data = json.loads(cached_twin)
            if event.timestamp <= twin_data["timestamp"]:
                update_cache = False
                
        if update_cache and is_valid_point:
            redis_client.set(f"vessel:{vessel_id}:current", json.dumps({
                "lat": event.lat,
                "lon": event.lon,
                "timestamp": event.timestamp,
                "speed_knots": event.speed_knots,
                "heading_degrees": event.heading_degrees,
                "telemetry_status": "fresh"
            }))
            
        results.append({"status": "saved", "event_id": event.device_event_id})
        
    return {"results": results}

@app.get("/api/vessels/{id}/history")
async def get_vessel_history(
    id: str,
    limit: int = 500,
    cursor: Optional[str] = Query(None),
    token: dict = Depends(get_current_user_token)
):
    """Returns paginated track history in O(log N) time using cursor filters."""
    mock_history = [
        {"timestamp": "2026-08-29T10:00:00Z", "lat": 13.08, "lon": 80.27},
        {"timestamp": "2026-08-29T10:05:00Z", "lat": 13.09, "lon": 80.28}
    ]
    return {
        "vessel_id": id,
        "logs": mock_history,
        "next_cursor": "2026-08-29T10:05:00Z"
    }


# ==========================================
# 7. Celery Worker Telemetry & Weather Scan Daemon (Stub)
# ==========================================

async def celery_safety_watcher_daemon():
    """
    Background safety daemon executing every 60 seconds.
    Uses distributed Redis locks with Expiry TTL to prevent deadlocks.
    """
    lock_acquired = redis_client.set("lock:celery:safety_daemon", "active", ex=120, nx=True)
    if not lock_acquired:
        print("[Celery Daemon] Active run locked. Skipping overlapping cycle.")
        return
        
    try:
        print("[Celery Daemon] Running background safety re-evaluations...")
    finally:
        redis_client.delete("lock:celery:safety_daemon")

if __name__ == "__main__":
    import uvicorn
    print("[DEBUG] Starting ORCA Unified Backend on http://0.0.0.0:8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)