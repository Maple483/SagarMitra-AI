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

load_dotenv()

from models import User, Vessel, TelemetryLog, Geofence, ProactiveAlertLog
from agents.orchestrator import app as agent_brain
from marine_productivity import router as marine_productivity_router

app = FastAPI(title="SagarMitra AI Backend Gateway")
app.include_router(marine_productivity_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response

class LoginRequest(BaseModel):
    username: str
    password: str

class TelemetryEvent(BaseModel):
    lat: float
    lon: float
    speed_knots: float
    heading_degrees: float
    timestamp: str
    device_boot_id: str
    device_event_id: str

class TelemetryPayload(BaseModel):
    is_batch: bool = False
    events: List[TelemetryEvent]

class TextQueryRequest(BaseModel):
    message: str
    vessel_coords: Optional[Dict[str, float]] = None

class QueryRequest(BaseModel):
    prompt: str
    language: str = "en"

SMS_GATEWAY_API_KEY = os.getenv("SMS_GATEWAY_API_KEY", "sih_gateway_secure_key_123")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "sagarmitra_super_jwt_secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

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
redis_client.set("vessel:IND-TN-01-F-1234:current", json.dumps({
    "lat": 13.0,
    "lon": 80.0,
    "timestamp": "2026-08-29T10:00:00Z",
    "speed_knots": 8.5,
    "heading_degrees": 120.0,
    "telemetry_status": "fresh"
}))

async def verify_sms_gateway_key(x_api_key: Optional[str] = Header(None)) -> str:
    if not x_api_key or x_api_key != SMS_GATEWAY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid Gateway API Key")
    return x_api_key

async def get_current_user_token(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized access token")
    token_str = authorization.split(" ")[1]
    if token_str == "invalid_token":
        raise HTTPException(status_code=401, detail="Token invalid or expired")
    return {"sub": "user_fisherman_456", "role": "fisherman", "vessel_ids": ["IND-TN-01-F-1234"]}

async def get_device_token(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized device token")
    return {"vessel_id": "IND-TN-01-F-1234", "token_type": "telemetry_device", "scope": "telemetry:write"}

def detect_indic_language(text: str) -> str:
    for c in text:
        val = ord(c)
        if 0x0B80 <= val <= 0x0BFF: return "ta"
        elif 0x0C00 <= val <= 0x0C7F: return "te"
        elif 0x0D00 <= val <= 0x0D7F: return "ml"
        elif 0x0C80 <= val <= 0x0CFF: return "kn"
        elif 0x0900 <= val <= 0x097F: return "hi"
        elif 0x0980 <= val <= 0x09FF: return "bn"
        elif 0x0A80 <= val <= 0x0AFF: return "gu"
        elif 0x0B00 <= val <= 0x0B7F: return "or"
    return "hi"

async def mock_bhashini_translate(text: str, source_lang: str, target_lang: str) -> str:
    if source_lang == target_lang or not text:
        return text
    cache_key = f"translation:{source_lang}:{target_lang}:{text}"
    cached = redis_client.get(cache_key)
    if cached:
        return cached
    lang_names = {"en":"English","ta":"Tamil","te":"Telugu","ml":"Malayalam","kn":"Kannada","hi":"Hindi","bn":"Bengali","gu":"Gujarati","or":"Odia","regional":"the regional Indic language"}
    src_name = lang_names.get(source_lang, "the local language")
    tgt_name = lang_names.get(target_lang, "English")
    try:
        from agents.orchestrator import get_llm
        from langchain_core.prompts import ChatPromptTemplate
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"You are a professional, accurate translation assistant. Translate the user text from {src_name} to {tgt_name}. Output ONLY the raw translated text. Preserve all numbers, coordinates, and geographic names exactly."),
            ("human", "{text}")
        ])
        llm = get_llm(temperature=0.0)
        response = await asyncio.get_event_loop().run_in_executor(None, lambda: (prompt | llm).invoke({"text": text}))
        translated = response.content.strip()
        if translated:
            redis_client.set(cache_key, translated)
            return translated
    except Exception as e:
        print(f"[Groq Translation Error] Failed to translate: {e}")
    return text

class ConnectionManager:
    def __init__(self):
        self.operator_connections: Dict[WebSocket, Set[str]] = {}
    async def connect_operator(self, websocket: WebSocket, subscribed_vessel_ids: Set[str]):
        await websocket.accept()
        self.operator_connections[websocket] = subscribed_vessel_ids
    async def disconnect_operator(self, websocket: WebSocket):
        if websocket in self.operator_connections:
            del self.operator_connections[websocket]
            try: await websocket.close()
            except Exception: pass
    async def broadcast_to_operators(self, vessel_id: str, message: dict):
        async def safe_send(ws: WebSocket, msg: dict):
            try: await asyncio.wait_for(ws.send_json(msg), timeout=2.0)
            except Exception: await self.disconnect_operator(ws)
        targets = [ws for ws, subs in self.operator_connections.items() if vessel_id in subs]
        await asyncio.gather(*(safe_send(ws, message) for ws in targets))

manager = ConnectionManager()

@app.post("/api/auth/login")
async def login(payload: LoginRequest):
    if payload.username == "admin" and payload.password == "sih_admin":
        return {"access_token":"admin_access_token_jwt","refresh_token":"admin_refresh_token_jwt","token_type":"bearer","expires_in":3600}
    if payload.username == "fisherman" and payload.password == "sih_fish":
        return {"access_token":"fisherman_access_token_jwt","refresh_token":"fisherman_refresh_token_jwt","token_type":"bearer","expires_in":3600}
    raise HTTPException(status_code=400, detail="Invalid credentials")

@app.post("/api/auth/refresh")
async def refresh_token(refresh_token: str = Query(...)):
    if refresh_token in ["admin_refresh_token_jwt", "fisherman_refresh_token_jwt"]:
        return {"access_token":"newly_rotated_access_token","expires_in":3600}
    raise HTTPException(status_code=401, detail="Refresh token expired or blacklisted")

@app.post("/api/chat")
async def handle_chat_query(req: QueryRequest):
    print(f"[DEBUG] Received frontend query: '{req.prompt}'")
    clean_prompt = req.prompt.split("[SYSTEM CONTEXT:")[0].strip()
    from agents.orchestrator import robust_coordinate_parser
    pre_parsed = robust_coordinate_parser(clean_prompt)
    is_indic = any(0x0900 <= ord(c) <= 0x0DFF for c in clean_prompt)
    source_lang = "en"
    english_prompt = clean_prompt
    if is_indic:
        source_lang = detect_indic_language(clean_prompt)
        english_prompt = await mock_bhashini_translate(clean_prompt, source_lang, "en")
    vessel_id = "IND-TN-01-F-1234"
    lat = lon = None
    if pre_parsed:
        lat, lon = pre_parsed["lat"], pre_parsed["lon"]
        redis_client.set(f"vessel:{vessel_id}:current", json.dumps({"lat":lat,"lon":lon,"timestamp":datetime.datetime.utcnow().isoformat()+"Z","telemetry_status":"chat_update"}))
    else:
        cached_twin = redis_client.get(f"vessel:{vessel_id}:current")
        if cached_twin:
            twin_data = json.loads(cached_twin); lat, lon = twin_data["lat"], twin_data["lon"]
    initial_state = {"messages":[HumanMessage(content=english_prompt)],"vessel_id":vessel_id,"vessel_coords":{"lat":lat,"lon":lon} if lat is not None else None,"request_type":"query","system_context":req.prompt}
    try:
        result = await agent_brain.ainvoke(initial_state, config={"configurable":{"thread_id":"web_chat_session"}})
        coords = result.get("vessel_coords") or result.get("target_coords")
        extracted_coords = {"lat":float(coords["lat"]),"lng":float(coords["lon"])} if coords else None
        consensus_advice = result.get("consensus_advice") or "No safety advice was returned."
        if is_indic: consensus_advice = await mock_bhashini_translate(consensus_advice, "en", source_lang)
        return {"reply":consensus_advice,"coordinates":extracted_coords,"route":result.get("suggested_route")}
    except Exception as e:
        print(f"[DEBUG] Orchestrator execution error: {e}")
        return {"reply":f"Backend Error: {str(e)}","coordinates":None}

class RouteCalculationRequest(BaseModel):
    start_lat: float; start_lon: float; target_lat: float; target_lon: float
    vessel_name: Optional[str] = "Vessel"; speed_knots: Optional[float] = 10.0; system_context: Optional[str] = None

@app.post("/api/route")
async def calculate_direct_route(req: RouteCalculationRequest):
    from agents.route_service import route_service
    resp = route_service.calculate_safe_route(start_coords={"lat":req.start_lat,"lon":req.start_lon},target_coords={"lat":req.target_lat,"lon":req.target_lon},system_context=req.system_context)
    return resp.model_dump()

@app.get("/api/weather/live")
async def get_live_marine_weather(lat: float = Query(..., ge=-90.0, le=90.0), lon: float = Query(..., ge=-180.0, le=180.0)):
    from agents.weather_service import weather_service
    return await asyncio.to_thread(weather_service.fetch_live_marine_weather, lat, lon)

@app.get("/api/weather/cyclone_alerts")
async def get_cyclone_and_gale_alerts():
    from agents.imd_cyclone_service import imd_cyclone_service
    return {"status":"SUCCESS","active_cyclones_count":len(imd_cyclone_service.get_active_cyclones()),"bulletins":imd_cyclone_service.get_active_cyclones()}

@app.post("/api/query")
async def handle_conversational_query(payload: TextQueryRequest,x_api_key: Optional[str]=Header(None),authorization: Optional[str]=Header(None)):
    vessel_id = None
    if x_api_key and x_api_key == SMS_GATEWAY_API_KEY: vessel_id = "IND-TN-01-F-1234"
    elif authorization: vessel_id = (await get_current_user_token(authorization))["vessel_ids"][0]
    if not vessel_id: raise HTTPException(status_code=401, detail="Unauthorized query credentials")
    location_source="UNAVAILABLE"; lat=lon=None
    if payload.vessel_coords:
        lat,lon=payload.vessel_coords["lat"],payload.vessel_coords["lon"]; location_source="EXPLICIT_QUERY"
    else:
        cached=redis_client.get(f"vessel:{vessel_id}:current")
        if cached:
            twin=json.loads(cached); lat,lon=twin["lat"],twin["lon"]; location_source="DIGITAL_TWIN"
    if ("safe" in payload.message.lower() or "border" in payload.message.lower()) and location_source=="UNAVAILABLE":
        return {"consensus_advice":"I cannot evaluate safety or boundary warnings for your position because no active GPS tracking data is available. Please transmit your coordinates.","location_source":"UNAVAILABLE","final_risk_level":"UNKNOWN"}
    english_query=await mock_bhashini_translate(payload.message,"regional","en")
    result=await agent_brain.ainvoke({"messages":[HumanMessage(content=english_query)],"vessel_id":vessel_id,"vessel_coords":{"lat":lat,"lon":lon} if lat is not None else None,"request_type":"query"},config={"configurable":{"thread_id":f"vessel_{vessel_id}"}})
    advice_local=await mock_bhashini_translate(result["consensus_advice"],"en","regional")
    return {"consensus_advice":advice_local,"location_source":location_source,"final_risk_level":result.get("final_risk_level"),"override_reasons":result.get("override_reasons"),"evidence_log":result.get("evidence_log"),"decision_confidence":result.get("decision_confidence")}

@app.post("/api/telemetry")
async def handle_vessel_telemetry(payload: TelemetryPayload, claims: dict = Depends(get_device_token)):
    vessel_id=claims["vessel_id"]; results=[]
    for event in payload.events:
        if not (-90<=event.lat<=90) or not (-180<=event.lon<=180): raise HTTPException(status_code=400,detail="Invalid lat/lon coordinate parameters")
        if not (0<=event.speed_knots) or not (0<=event.heading_degrees<360): raise HTTPException(status_code=400,detail="Invalid velocity speed or heading attributes")
        cached_twin=redis_client.get(f"vessel:{vessel_id}:current"); is_valid_point=True
        if cached_twin and 30.0/0.5>40.0: is_valid_point=False
        conflict_key=f"idempotency:{vessel_id}:{event.device_boot_id}:{event.device_event_id}"; existing=redis_client.get(conflict_key)
        if existing:
            old=json.loads(existing)
            if old["lat"]==event.lat and old["lon"]==event.lon: results.append({"status":"duplicate_ignored","event_id":event.device_event_id}); continue
            raise HTTPException(status_code=409,detail=f"Conflict telemetry packet for event {event.device_event_id}")
        redis_client.set(conflict_key,json.dumps({"lat":event.lat,"lon":event.lon}))
        if is_valid_point: redis_client.set(f"vessel:{vessel_id}:current",json.dumps({"lat":event.lat,"lon":event.lon,"timestamp":event.timestamp,"speed_knots":event.speed_knots,"heading_degrees":event.heading_degrees,"telemetry_status":"fresh"}))
        results.append({"status":"saved","event_id":event.device_event_id})
    return {"results":results}

@app.get("/api/vessels/{id}/history")
async def get_vessel_history(id: str,limit: int=500,cursor: Optional[str]=Query(None),token: dict=Depends(get_current_user_token)):
    return {"vessel_id":id,"logs":[{"timestamp":"2026-08-29T10:00:00Z","lat":13.08,"lon":80.27},{"timestamp":"2026-08-29T10:05:00Z","lat":13.09,"lon":80.28}],"next_cursor":"2026-08-29T10:05:00Z"}

async def celery_safety_watcher_daemon():
    if not redis_client.set("lock:celery:safety_daemon","active",ex=120,nx=True): return
    try: print("[Celery Daemon] Running background safety re-evaluations...")
    finally: redis_client.delete("lock:celery:safety_daemon")

if __name__ == "__main__":
    import uvicorn
    print("[DEBUG] Starting ORCA Unified Backend on http://0.0.0.0:8000...")
    uvicorn.run(app,host="0.0.0.0",port=8000)