"""
Fishermen SMS Communication Simulator & Test Runner
===================================================
Simulates SMS queries from fishermen sent via SMS Gateway / GSM Modem / USSD
to the SagarMitra AI Gateway endpoint (/api/query).

Usage:
  python simulate_sms.py [--url http://localhost:8000] [--key sih_gateway_secure_key_123]
"""

import os
import sys
import json
import argparse
import requests

# Enable UTF-8 Codepage on Windows Console
if sys.platform == "win32":
    os.system("chcp 65001 > NUL")
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

DEFAULT_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
DEFAULT_API_KEY = os.getenv("SMS_GATEWAY_API_KEY", "sih_gateway_secure_key_123")

TEST_SCENARIOS = [
    {
        "name": "1. Fisherman SMS Query with Explicit GPS Coords (Bay of Bengal)",
        "message": "Is it safe to fish at 13.0N 80.0E today?",
        "vessel_coords": {"lat": 13.0, "lon": 80.0}
    },
    {
        "name": "2. Fisherman SMS Border Geofence Check (Near Maritime Boundary)",
        "message": "Am I close to the International Maritime Boundary Line?",
        "vessel_coords": {"lat": 10.1, "lon": 79.8}
    },
    {
        "name": "3. Fisherman SMS Query using Digital Twin Fallback (No GPS provided in SMS)",
        "message": "Give me weather advisory for my vessel position",
        "vessel_coords": None
    },
    {
        "name": "4. Multilingual Fisherman Query (Tamil / Regional simulation)",
        "message": "Is fishing safe in regional waters?",
        "vessel_coords": {"lat": 12.5, "lon": 80.2}
    }
]

def send_sms_query(backend_url: str, api_key: str, message: str, vessel_coords: dict = None):
    endpoint = f"{backend_url.rstrip('/')}/api/query"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key
    }
    payload = {
        "message": message
    }
    if vessel_coords:
        payload["vessel_coords"] = vessel_coords

    print("\n=======================================================", flush=True)
    print(f"[OUTGOING SMS FROM FISHERMAN]", flush=True)
    print(f"   SMS Text : '{message}'", flush=True)
    if vessel_coords:
        print(f"   GPS Coords: Lat {vessel_coords['lat']}, Lon {vessel_coords['lon']}", flush=True)
    else:
        print(f"   GPS Coords: [None - relying on Digital Twin cache]", flush=True)
    print("-------------------------------------------------------", flush=True)
    
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=25)
        print(f"HTTP Status: {response.status_code}", flush=True)
        
        if response.status_code == 200:
            data = response.json()
            print("\n[INCOMING SMS RESPONSE TO FISHERMAN]", flush=True)
            print(f"   Risk Level     : {data.get('final_risk_level', 'N/A')}", flush=True)
            print(f"   Location Src   : {data.get('location_source', 'N/A')}", flush=True)
            
            advice_en = data.get('consensus_advice_en')
            advice_local = data.get('consensus_advice')
            
            if advice_en:
                print(f"   SMS Advisory (English):\n   \"{advice_en}\"", flush=True)
            if advice_local and advice_local != advice_en:
                print(f"   SMS Advisory (Regional):\n   \"{advice_local}\"", flush=True)
        else:
            print(f"[ERROR] Response: {response.text}", flush=True)
    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Could not connect to backend server at {backend_url}.", flush=True)
        print("   Ensure the backend FastAPI server is running (`uvicorn main:app --reload` or `python main.py`)", flush=True)
    except Exception as e:
        print(f"[ERROR] Unexpected Error: {e}", flush=True)

def run_all_tests(backend_url: str, api_key: str):
    print("=" * 60, flush=True)
    print("   SAGAR MITRA - FISHERMEN SMS GATEWAY SIMULATION RUNNER   ", flush=True)
    print("=" * 60, flush=True)
    print(f"Target Backend API: {backend_url}", flush=True)
    print(f"SMS Gateway API Key: {api_key}", flush=True)
    
    for scenario in TEST_SCENARIOS:
        print(f"\n---> Running Scenario: {scenario['name']}", flush=True)
        send_sms_query(
            backend_url=backend_url,
            api_key=api_key,
            message=scenario["message"],
            vessel_coords=scenario["vessel_coords"]
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test SagarMitra SMS Gateway Query Endpoint")
    parser.add_argument("--url", default=DEFAULT_URL, help="Backend URL (default: http://localhost:8000)")
    parser.add_argument("--key", default=DEFAULT_API_KEY, help="SMS Gateway API Key")
    parser.add_argument("--msg", default=None, help="Custom SMS message text")
    parser.add_argument("--lat", type=float, default=None, help="Vessel Latitude")
    parser.add_argument("--lon", type=float, default=None, help="Vessel Longitude")
    
    args = parser.parse_args()
    
    if args.msg:
        coords = {"lat": args.lat, "lon": args.lon} if args.lat is not None and args.lon is not None else None
        send_sms_query(args.url, args.key, args.msg, coords)
    else:
        run_all_tests(args.url, args.key)
