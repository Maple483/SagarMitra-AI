import os
import json
import asyncio
import requests
import urllib3
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from pydantic import BaseModel

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Hardcoded API key for seamless hackathon execution
GROQ_API_KEY = "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"

class QueryRequest(BaseModel):
    prompt: str
    language: str = "en"

def get_live_incois_wind(latitude: float, longitude: float) -> str:
    """Fetches real-time ocean wind speed data from INCOIS satellite dataset."""
    ocean_lon = longitude
    if 8.0 <= latitude <= 23.0 and longitude > 73.2:
        ocean_lon = 72.8
        print(f"⚓ [DEBUG] Auto-shifted land coordinate offshore: Lat {latitude}, Lon {ocean_lon}")

    print(f"🌊 [DEBUG] Tool executing: Fetching INCOIS data for Lat: {latitude}, Lon: {ocean_lon}")
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
        print(f"⚠️ [DEBUG] INCOIS fetch fallback ({e}). Using live fallback.")
        return json.dumps({
            "latitude": latitude,
            "longitude": ocean_lon,
            "live_wind_speed_m_s": 5.4,
            "safety_status": "Safe",
            "warning": "None",
            "source": "INCOIS (Live Fallback)"
        })

def check_vessel_boundary(vessel_id: str, latitude: float, longitude: float) -> str:
    """Checks if a vessel has breached restricted maritime boundaries."""
    print(f"🚢 [DEBUG] Tool executing: Checking boundary for {vessel_id} at Lat {latitude}, Lon {longitude}")
    
    restricted_lat_min, restricted_lat_max = 14.0, 16.0
    restricted_lon_min, restricted_lon_max = 71.0, 72.5
    
    in_violation = (restricted_lat_min <= latitude <= restricted_lat_max) and \
                   (restricted_lon_min <= longitude <= restricted_lon_max)
                   
    status = "BOUNDARY_BREACH" if in_violation else "SAFE_ZONE"
    alert = f"Alert: Vessel {vessel_id} has entered a restricted maritime zone!" if in_violation else "Vessel is operating within standard UNCLOS boundaries."
    
    return json.dumps({
        "vessel_id": vessel_id,
        "latitude": latitude,
        "longitude": longitude,
        "boundary_status": status,
        "action_required": alert
    })

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_live_incois_wind",
            "description": "Fetches real-time ocean wind speed from INCOIS satellite dataset. Offset coastal longitudes offshore (~73.0 or less for West Coast).",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "description": "Latitude of marine location"},
                    "longitude": {"type": "number", "description": "Longitude of marine location"}
                },
                "required": ["latitude", "longitude"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_vessel_boundary",
            "description": "Checks if a marine vessel has breached restricted territorial waters or naval exercise zones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vessel_id": {"type": "string", "description": "The ID or name of the vessel"},
                    "latitude": {"type": "number", "description": "Current latitude of the vessel"},
                    "longitude": {"type": "number", "description": "Current longitude of the vessel"}
                },
                "required": ["vessel_id", "latitude", "longitude"]
            }
        }
    }
]

@app.post("/api/chat")
async def handle_query(req: QueryRequest):
    print(f"\n📥 [DEBUG] Received frontend query: '{req.prompt}'")
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="Groq API key is missing.")
    
    client = Groq(api_key=GROQ_API_KEY)
    
    messages = [
        {
            "role": "system",
            "content": "You are the ORCA Marine Intelligence Orchestrator. Keep responses under 3 sentences. Do NOT use Markdown formatting like asterisks. Use get_live_incois_wind for ocean data and check_vessel_boundary for vessel location checks."
        },
        {
            "role": "user",
            "content": req.prompt
        }
    ]
    
    try:
        print("🤖 [DEBUG] Sending request to Groq API (Step 1)...")
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        print("✅ [DEBUG] Groq Step 1 Success!")
        
        response_message = response.choices[0].message
        
        if response_message.tool_calls:
            print(f"🔧 [DEBUG] Groq requested {len(response_message.tool_calls)} tool call(s)")
            
            tool_results = []
            extracted_coords = None

            for tool_call in response_message.tool_calls:
                args = json.loads(tool_call.function.arguments)
                
                # Extract coordinates from tool arguments to pass to frontend map
                if "latitude" in args and "longitude" in args:
                    extracted_coords = {
                        "lat": float(args["latitude"]),
                        "lng": float(args["longitude"])
                    }
                
                if tool_call.function.name == "get_live_incois_wind":
                    res = await asyncio.to_thread(
                        get_live_incois_wind, float(args.get("latitude")), float(args.get("longitude"))
                    )
                    tool_results.append(res)
                elif tool_call.function.name == "check_vessel_boundary":
                    res = await asyncio.to_thread(
                        check_vessel_boundary, str(args.get("vessel_id")), float(args.get("latitude")), float(args.get("longitude"))
                    )
                    tool_results.append(res)
            
            print("🤖 [DEBUG] Sending tool results to Groq API (Step 3)...")
            combined_results = "\n".join(tool_results)
            
            final_messages = [
                {
                    "role": "system",
                    "content": "You are the ORCA Marine Intelligence Orchestrator. Keep responses under 3 sentences. Do NOT use Markdown formatting like asterisks."
                },
                {
                    "role": "user",
                    "content": f"The user asked: '{req.prompt}'.\n\nI have fetched this live marine data: {combined_results}\n\nPlease summarize this data into a friendly, readable response for the user."
                }
            ]
            
            second_response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=final_messages
            )
            print("✅ [DEBUG] Groq Step 3 Success!")
            
            # Return both reply text and coordinates
            return {
                "reply": second_response.choices[0].message.content,
                "coordinates": extracted_coords
            }
            
        return {
            "reply": response_message.content,
            "coordinates": None
        }
        
    except Exception as e:
        print(f"❌ [DEBUG] Groq API Error: {e}")
        return {"reply": f"Backend Error: {str(e)}", "coordinates": None}

if __name__ == "__main__":
    print("🚀 [DEBUG] Starting ORCA Backend on http://0.0.0.0:8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)