import os
from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, ForeignKey, Index, UniqueConstraint, event, func
from sqlalchemy.orm import declarative_base, relationship
from geoalchemy2 import Geography  # Supports EPSG:4326 PostGIS geography columns

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
    contact_phone = Column(String, nullable=False)  # SMS / WhatsApp target (allows multiple vessels per owner)
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
    # Enforce timezone awareness to prevent UTC offset comparison bugs
    timestamp = Column(DateTime(timezone=True), nullable=False)
    is_valid = Column(Boolean, default=True)          # Outlier flag tracking
    
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
    boundary_line = Column(Geography(geometry_type="MULTILINESTRING", srid=4326), nullable=True)
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


# ==========================================
# ORM Listeners: Database-Agnostic Triggers
# ==========================================

@event.listens_for(Geofence, 'before_insert')
@event.listens_for(Geofence, 'before_update')
def sync_boundary_listener(mapper, connection, target):
    """
    Database-agnostic trigger logic. Generates the multilinestring boundary
    from the geography polygon before saving, avoiding manual SQL function casting.
    """
    if target.polygon is not None:
        # Automatically compute ST_Boundary using geography expression
        target.boundary_line = func.ST_Boundary(target.polygon)
