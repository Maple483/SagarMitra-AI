# Implementation Plan: API Gateway Server (FastAPI Backend)

This document specifies the database schemas, API endpoint specifications, WebSocket managers, translation strategies, security policies, and background daemon structures for the core **FastAPI Backend Server / API Gateway** (SagarMitra Core).

---

## 1. System Overview & Gateway Role

The FastAPI backend is the high-performance bridging layer between presentation interfaces (React GIS, Twilio/GSM SMS Client) and analytical engines:

```
┌─────────────────────────────────┐      ┌─────────────────────────┐
│     React GIS Operator UI       │      │   GSM/SMS Simulator     │
└───────────────┬─────────────────┘      └────────────┬────────────┘
                │ (HTTP / WebSockets)                 │ (HTTP REST)
                ▼                                     ▼
┌──────────────────────────────────────────────────────────────────┐
│                      FastAPI API Gateway                         │
│  ├─ Auth & JWT Validator           ├─ Bhashini Translator Adapters│
│  ├─ WebSocket Broadcast Manager   ├─ Redis Rate Limiters & Cache │
└───────────────┬─────────────────────────────────────┬────────────┘
                │                                     │
                ▼ (LangGraph State Invocations)       ▼ (SQLAlchemy / GeoAlchemy2)
┌─────────────────────────────────┐      ┌─────────────────────────┐
│  LangGraph Orchestrator Brain   │      │    PostGIS Database     │
└─────────────────────────────────┘      └─────────────────────────┘
```

---

## 2. Technical Component Design

### A. Database Schemas (SQLAlchemy ORM + PostGIS)
We define the database schemas with indices, relationships, and native Geography type columns to utilize spatial indexes:

```python
from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship
from geoalchemy2 import Geography  # Natively uses EPSG:4326 PostGIS geography columns

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)  # UUID
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="operator")  # "admin" / "operator" / "fisherman"
    
    # Relationships
    vessels = relationship("Vessel", back_populates="owner")

class Vessel(Base):
    __tablename__ = "vessels"
    id = Column(String, primary_key=True)  # Registration Number (e.g. IND-TN-01-F-1234)
    name = Column(String, nullable=False)
    owner_user_id = Column(String, ForeignKey("users.id"), nullable=False) # Explicit ownership relationship
    contact_phone = Column(String, nullable=False)  
    preferred_language = Column(String, default="en") # Bhashini locale: "ta", "te", etc.
    is_active = Column(Boolean, default=True)

    # Relationships
    owner = relationship("User", back_populates="vessels")
    telemetry_logs = relationship("TelemetryLog", back_populates="vessel", cascade="all, delete-orphan")

class TelemetryLog(Base):
    __tablename__ = "telemetry_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    vessel_id = Column(String, ForeignKey("vessels.id"), nullable=False)
    device_boot_id = Column(String, nullable=False)   # UUID generated on boot to resolve counter resets
    device_event_id = Column(String, nullable=False)  # Event sequence ID
    # Core fix: Enforce timezone awareness to prevent UTC comparison offset bugs
    timestamp = Column(DateTime(timezone=True), nullable=False)
    is_valid = Column(Boolean, default=True)          # Tracks validator outcomes
    
    # PostGIS Geography POINT (meters calculations leverage indexes natively)
    location = Column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    speed_knots = Column(Float)
    heading_degrees = Column(Float)

    # Relationships
    vessel = relationship("Vessel", back_populates="telemetry_logs")

    # Table constraints and indexes
    __table_args__ = (
        # Composite unique constraint to handle non-global device restarts cleanly
        UniqueConstraint("vessel_id", "device_boot_id", "device_event_id", name="uq_vessel_boot_event"),
        # Compound index to speed up historical track searches and Celery daemon queries
        Index("idx_vessel_timestamp", "vessel_id", "timestamp"),
    )

class Geofence(Base):
    __tablename__ = "geofences"
    id = Column(String, primary_key=True)  # ID (e.g., imbl_srilanka)
    name = Column(String, nullable=False)
    zone_type = Column(String)  # "restricted" / "conservation" / "buffer"
    # Store natively as Geography (MULTIPOLYGON EPSG:4326) to utilize GiST spatial indexes directly
    polygon = Column(Geography(geometry_type="MULTIPOLYGON", srid=4326), nullable=False)
    # Store boundary line as Geography MULTILINESTRING to prevent running index-bypassing ST_Boundary calls dynamically
    boundary_line = Column(Geography(geometry_type="MULTILINESTRING", srid=4326), nullable=False)
    description = Column(String)

class ProactiveAlertLog(Base):
    __tablename__ = "proactive_alert_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    vessel_id = Column(String, ForeignKey("vessels.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False) # Timezone aware
    risk_level = Column(String, nullable=False)  # "WARNING" / "CRITICAL" / "UNKNOWN"
    alert_type = Column(String, nullable=False)  # "boundary_breach" / "weather_storm" / "telemetry_stale"
    message_content = Column(String, nullable=False)
    distance_to_boundary = Column(Float)         # Track cross-boundary depth alerts
```

> [!IMPORTANT]
> **Database Trigger for Geofences (Normalization Fix):**
> To prevent data desynchronization between the `polygon` and `boundary_line` columns, we register a database trigger on the `Geofence` table:
> ```sql
> CREATE OR REPLACE FUNCTION sync_geofence_boundary()
> RETURNS TRIGGER AS $$
> BEGIN
>   NEW.boundary_line := ST_Boundary(NEW.polygon::geometry)::geography;
>   RETURN NEW;
> END;
> $$ LANGUAGE plpgsql;
> 
> CREATE TRIGGER trg_sync_geofence_boundary
> BEFORE INSERT OR UPDATE ON geofences
> FOR EACH ROW EXECUTE FUNCTION sync_geofence_boundary();
> ```

---

## 3. Real-Time Telemetry & Validation Layers

### A. Telemetry Validation Layer (With Velocity Neighbor Scans)
For every telemetry upload, the API Gateway applies validation rules:
1.  **Coordinate Checks:** Verify latitude is in $[-90.0, 90.0]$ and longitude is in $[-180.0, 180.0]$.
2.  **Telemetry Attributes:** Validate `speed_knots >= 0.0` and `heading_degrees` is in `[0.0, 360.0)`.
3.  **Temporal Integrity (Batch vs Single):**
    *   Rejects coordinates with timestamps in the future.
    *   If `is_batch == True` in telemetry payload, skip the 24-hour data age check. For standard single pings (`is_batch == False`), reject coordinate records older than 24 hours.
4.  **Temporal Velocity Neighbors Filter (Impossible Jump / Anomaly Check):**
    *   **Core fix: Validate against Last Known Valid Point (Poison Point Prevention):**
        *   Velocity validations are strictly performed against the **last successfully validated telemetry log** stored in the database (`is_valid == True`).
        *   If the new point fails the $40\text{ knots}$ velocity check against either temporal neighbor (previous/next), it is flagged as `is_valid = False` in the database, but **does not** overwrite the vessel's `last_valid_location` state, preventing a single poisoned outlier from locking out subsequent valid coordinates.
5.  **Idempotency Key Conflict Resolution:**
    *   If `(vessel_id, device_boot_id, device_event_id)` already exists:
        *   Compare coordinates/attributes. If identical, return `HTTP 200 OK` (idempotent retry success).
        *   If coordinates differ, return `HTTP 409 Conflict` (payload conflict anomaly).

### B. Digital Twin Current Position Store & Database Consistency
The current coordinates are cached in Redis: `vessel:{vessel_id}:current`
*   **Write Sequence:** Validate $\to$ Commit to PostgreSQL $\to$ If DB write succeeds, update Redis current store.
*   **Consistency Recovery & Thundering Herd Shield:**
    *   Redis is treated as a derived cache of the PostgreSQL source of truth. If a Redis cache miss occurs, the gateway reconstructs the cache by querying the latest timestamp row from the database.
    *   **Distributed Mutex Lock:** To prevent thundering herd database degradation under high parallel loads, the first cache-miss thread acquires a Redis-based query lock (`lock:vessel:{vessel_id}:rebuild`). Subsequent concurrent threads wait and read the repopulated cache value instead of storming the database.
*   **Offline Batch Sync Rule:** During batch syncing of old telemetry points, database writes succeed, but the Redis current-state store is updated **only** if the incoming `timestamp` is strictly newer than the cached timestamp.

---

## 4. Live Broadcast & Distributed Workers

### A. Live WebSocket Broadcaster (With Tenant Isolation & Connection Timeout)
```python
import asyncio
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.operator_connections: Dict[WebSocket, Set[str]] = {} # Map socket to subscribed vessel IDs
        self.vessel_connections: Dict[str, WebSocket] = {}
        
    async def connect_operator(self, websocket: WebSocket, subscribed_vessel_ids: Set[str]):
        await websocket.accept()
        self.operator_connections[websocket] = subscribed_vessel_ids
        
    async def disconnect_operator(self, websocket: WebSocket):
        # Core fix: Safe list removal and explicit Close socket handle to prevent file descriptor leaks
        if websocket in self.operator_connections:
            del self.operator_connections[websocket]
            try:
                await websocket.close()
            except Exception:
                pass
        
    async def broadcast_to_operators(self, vessel_id: str, message: dict):
        # Core fix: Async task group with connection timeouts to prevent slow clients from hanging memory
        async def safe_send(ws: WebSocket, msg: dict):
            try:
                await asyncio.wait_for(ws.send_json(msg), timeout=2.0)
            except Exception:
                await self.disconnect_operator(ws)
                
        targets = [ws for ws, subs in self.operator_connections.items() if vessel_id in subs]
        await asyncio.gather(*(safe_send(ws, message) for ws in targets))
```

### B. Proactive Immediate Event-Driven Tracker
When a telemetry point is saved, the gateway executes this PostGIS query immediately:
```sql
SELECT 
  geofences.id AS zone_id,
  geofences.zone_type AS zone_type,
  -- Check if vessel is INSIDE the boundary polygon (ST_Intersects natively handles Geography without casting)
  ST_Intersects(geofences.polygon, :point::geography) AS inside,
  -- Check if vessel is NEAR the boundary (native Geography ST_DWithin utilizes spatial GiST indexes)
  ST_DWithin(geofences.polygon, :point::geography, 2000) AS near,
  -- Calculate distance to native boundary_line (MULTILINESTRING Geography) using spatial GiST index
  ST_Distance(geofences.boundary_line, :point::geography) AS boundary_distance
FROM geofences;
```
The safety engine then applies a policy matrix to determine the risk. 

*   **Mutually Exclusive Relations & Prioritization:**
    *   If `inside == True`: `relation = "INSIDE"`
    *   Else if `near == True`: `relation = "NEAR"`
    *   Else: `relation = "OUTSIDE"`
    *   If a query triggers multiple overlapping geofence hazards, the system aggregates all warnings, evaluates the `ACTION_PRIORITY` (`exit_zone` > `return_to_safe` > `preventative_steer_away` > `proceed_with_caution` > `no_routing`), and selects the primary action.

### C. Celery Safety Watcher Daemon
*   Runs every 60 seconds.
*   **Distributed Lock (With Lock TTL Expiry):**
    *   **Core fix: Prevent permanent daemon deadlocks:** Redis lock key `lock:celery:safety_daemon` is set with an explicit expiry TTL (e.g. 120 seconds). If the Celery worker crashes mid-cycle, the lock is automatically released after 2 minutes, preventing permanent background worker lockouts.
*   **Weather Re-Evaluation (With Fresh Cache refresh):**
    *   *Grid Optimization:* Weather data is cached in Redis per $0.1^\circ \times 0.1^\circ$ cells (matching upstream $11\text{km}$ grid resolution) with a TTL of 4 hours.
    *   *Cache Hit & Fresh (< 1 hour):* Use cache.
    *   *Cache Hit & Stale (1-3 hours):* Use cache, but fire an asynchronous background refresh task.
    *   *Cache Miss OR Stale Cache (> 3 hours):* Attempt a live forecast API fetch.
    *   *Live Fetch Failure:* Set risk to `UNKNOWN` and confidence to `0.0`.
*   **Staleness Policy & Alert Cooldown:**
    *   *Age > 15m:* `telemetry_status = "offline"`. Bypasses spatial checks.
    *   *Age 5-15m:* `telemetry_status = "stale"`. Creates warning with `alert_type = "telemetry_stale"`, subject to the 10-minute cooldown `vessel:{vessel_id}:alert:telemetry_stale:WARNING` to prevent spamming.

---

## 5. Security, Auth Contracts & Translations

### A. JWT & Auth Contracts
We define two separate access tokens:
1.  **User Access Token (JWT):**
    *   `sub` = user_id
    *   `role` = "operator" | "admin" | "fisherman"
    *   *Note:* A single user with role `"fisherman"` can own multiple vessels. The API resolves authorized vessels via:
        `SELECT id FROM vessels WHERE owner_user_id = :user_id`
2.  **Device/Vessel Token (JWT):**
    *   `vessel_id` = registration_number
    *   `token_type` = "telemetry_device"
    *   `scope` = "telemetry:write"
3.  **Claims Checks & SMS API Exceptions (Multi-Vessel Resolution):**
    *   Requests with a *Vessel Token* verify `token.vessel_id == request.vessel_id`.
    *   Requests with an *SMS Gateway API Key* bypass vessel JWT claim verification. Instead, the gateway sends `contact_phone`.
    *   **Core fix: SMS State Machine Fallback & Graceful Parser:**
        *   If the phone maps to one active vessel, route immediately.
        *   If the phone maps to multiple vessels: check Redis session `vessel_session:{phone}:active_vessel`.
        *   If no active session exists: return a localized text menu list:
            *"You have multiple vessels: [1] Sagar1, [2] Sagar2. Reply with the number to select."*
        *   **Core fix: Non-integer query fallback:** Wrap index parsing in a `try-except ValueError` block. If the fisherman sends a normal query (e.g. *"Is it safe?"*) instead of an integer menu selection:
            1. Check if the message contains words indicating a general safety query.
            2. If so, evaluate safety on **all** registered vessels for that phone, or the last active vessel, and return aggregated warnings rather than crashing the SMS thread.
            3. Prompt: *"Please select a vessel first by replying with 1 or 2, or type 'cancel' to exit."*
        *   The resolved ID is cached in Redis with a 30-minute TTL to route subsequent messages automatically.
4.  **Token Refresh (`POST /api/auth/refresh`):** Validates refresh token claims and re-issues a new access token (with blacklist revocation on Redis).

### B. Translation Pipelines
*   **Input translation fail:** Stop execution and reply with a localized retry request.
*   **Output translation fail:** Return the original English advisory and append `translation_status = "unavailable"` in headers.

---

## 6. REST API Endpoint Specifications

| Endpoint | Method | Authentication | Query / Body Parameters | Response Output |
| :--- | :--- | :--- | :--- | :--- |
| `/api/auth/login` | `POST` | None | `{username, password}` | Access and refresh tokens. |
| `/api/auth/refresh`| `POST`| Refresh Token | None | Returns new access token. |
| `/api/query` | `POST` | SMS Key / JWT | `{message, vessel_coords}` | Returns Translated Advisories. Uses resolved `vessel_id`. |
| `/api/telemetry` | `POST` | Vessel Token | `{"is_batch": bool, "events": List[TelemetryEvent]}` | Inserts coordinates and updates current store. |
| `/api/vessels/{id}/history`| `GET` | JWT (Operator) | `?start=...&end=...&limit=500&cursor=timestamp` (Core fix: Cursor-based pagination on composite indexed timestamp key) | Paginated tracking logs history. |

*   **Location Sourcing Policy:**
    *   If `vessel_coords` is sent explicitly: set `location_source = "EXPLICIT_QUERY"`.
    *   Otherwise: resolve coordinate from Redis current position cache (`location_source = "DIGITAL_TWIN"`).
    *   If no coordinate exists and query is safety-dependent (e.g. *"is it safe here"*), the system blocks and returns: *"I cannot evaluate safety for your position because no active coordinates exist. Please check your GPS tracker."* (`location_source = "UNAVAILABLE"`, `location_required = True`).
