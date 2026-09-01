import os
import sys
import pytest

# Ensure orca-backend is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from main import app, SMS_GATEWAY_API_KEY, redis_client
import json

client = TestClient(app)

def test_sms_gateway_unauthorized():
    """Verify that requests without valid X-API-Key or Bearer token are rejected with 401."""
    response = client.post(
        "/api/query",
        json={"message": "Is it safe to fish at 13.0, 80.0?"}
    )
    assert response.status_code == 401
    assert "detail" in response.json()

def test_sms_gateway_invalid_api_key():
    """Verify that requests with incorrect API key are rejected."""
    response = client.post(
        "/api/query",
        headers={"X-API-Key": "wrong_key"},
        json={"message": "Is it safe to fish at 13.0, 80.0?"}
    )
    assert response.status_code == 401

def test_sms_gateway_query_with_explicit_coords():
    """Verify SMS query with explicit coordinates provided in vessel_coords."""
    response = client.post(
        "/api/query",
        headers={"X-API-Key": SMS_GATEWAY_API_KEY},
        json={
            "message": "What is the weather and sea condition near Bay of Bengal?",
            "vessel_coords": {"lat": 13.0, "lon": 80.0}
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "consensus_advice" in data
    assert data["location_source"] == "EXPLICIT_QUERY"
    assert "final_risk_level" in data

def test_sms_gateway_query_digital_twin_fallback():
    """Verify SMS query falls back to cached digital twin coordinates when vessel_coords omitted."""
    # Ensure mock redis has vessel position cached
    redis_client.set("vessel:IND-TN-01-F-1234:current", json.dumps({
        "lat": 13.0,
        "lon": 80.0,
        "timestamp": "2026-09-01T07:00:00Z",
        "speed_knots": 6.0,
        "heading_degrees": 90.0,
        "telemetry_status": "fresh"
    }))

    response = client.post(
        "/api/query",
        headers={"X-API-Key": SMS_GATEWAY_API_KEY},
        json={
            "message": "Am I safe near the border?"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "consensus_advice" in data
    assert data["location_source"] == "DIGITAL_TWIN"
    assert data["final_risk_level"] is not None

def test_sms_gateway_location_unavailable_fallback():
    """Verify SMS query returns explanatory message if safety check required but no location available."""
    # Clear cached digital twin for test vessel
    redis_client.delete("vessel:IND-TN-01-F-1234:current")

    response = client.post(
        "/api/query",
        headers={"X-API-Key": SMS_GATEWAY_API_KEY},
        json={
            "message": "Is it safe to fish here?"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["location_source"] == "UNAVAILABLE"
    assert data["final_risk_level"] == "UNKNOWN"
    assert "cannot evaluate safety" in data["consensus_advice"].lower()
