"""
NASA GIBS Near-Real-Time Satellite Context module.
Defines WMS 1.3.0 request contracts, layer identifiers, display ranges,
and startup/runtime availability health-checks with 6-hour caching.
"""

import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

GIBS_WMS_ENDPOINT = "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi"

LAYERS = {
    "sst": {
        "layer_id": "GHRSST_L4_MUR_Sea_Surface_Temperature",
        "title": "Sea Surface Temperature (GHRSST MUR)",
        "cadence": "Daily composite",
        "nominal_latency": "~24 hours",
        "display_range": "18°C to 34°C",
        "styles": "default",
        "format": "image/png",
    },
    "chlorophyll": {
        "layer_id": "MODIS_Aqua_L3_Chlorophyll_A_8Day",
        "title": "Chlorophyll-a Concentration (MODIS Aqua 8-Day)",
        "cadence": "8-Day composite",
        "nominal_latency": "~48 hours",
        "display_range": "0.01 to 64.0 mg/m³",
        "styles": "default",
        "format": "image/png",
    },
}

DEFAULT_INITIAL_BBOX = [7123924.0, 445640.0, 10685880.0, 2998600.0]  # EPSG:3857 Indian Maritime

_health_cache: Dict[str, Any] = {
    "available": True,
    "checked_at": 0.0,
    "latency_ms": 0.0,
}
HEALTH_CACHE_TTL_SECONDS = 21600.0  # 6 hours


def check_gibs_availability(layer_key: str = "sst") -> Dict[str, Any]:
    """
    Performs a lightweight 1x1 test tile GetMap verification against NASA GIBS WMS.
    Results are cached with a 6-hour TTL.
    """
    global _health_cache
    now = time.time()
    if (now - _health_cache["checked_at"]) < HEALTH_CACHE_TTL_SECONDS:
        return {
            "available": _health_cache["available"],
            "latency_ms": _health_cache["latency_ms"],
            "cached": True,
        }

    layer_info = LAYERS.get(layer_key, LAYERS["sst"])
    layer_id = layer_info["layer_id"]

    test_url = (
        f"{GIBS_WMS_ENDPOINT}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap"
        f"&LAYERS={layer_id}&STYLES=default&CRS=EPSG:3857"
        f"&BBOX=7123924.0,445640.0,7123925.0,445641.0"
        f"&WIDTH=1&HEIGHT=1&FORMAT=image/png&TRANSPARENT=TRUE"
    )

    t0 = time.time()
    available = False
    for attempt in range(2):
        try:
            req = urllib.request.Request(test_url, headers={"User-Agent": "ORCA-MarineProductivity/1.0"})
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status == 200:
                    available = True
                    break
        except (urllib.error.URLError, TimeoutError, Exception):
            if attempt == 0:
                time.sleep(0.5)  # Backoff before retry

    latency_ms = round((time.time() - t0) * 1000.0, 1)

    _health_cache["available"] = available
    _health_cache["checked_at"] = now
    _health_cache["latency_ms"] = latency_ms

    return {
        "available": available,
        "latency_ms": latency_ms,
        "cached": False,
    }


def get_satellite_info() -> Dict[str, Any]:
    return {
        "wms_endpoint": GIBS_WMS_ENDPOINT,
        "layers": LAYERS,
        "default_bbox": DEFAULT_INITIAL_BBOX,
        "attribution": "Imagery courtesy of NASA EOSDIS GIBS",
        "disclaimer": (
            "Current satellite context — Near-Real-Time (NRT) satellite composite for visualization only. "
            "Not used in historical correlation calculations."
        ),
        "health": check_gibs_availability("sst"),
    }
