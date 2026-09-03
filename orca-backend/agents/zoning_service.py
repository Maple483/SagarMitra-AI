from typing import Dict, Any, Optional

class ZoningService:
    def __init__(self):
        # Define mock critical conservation zones (bounding boxes for demo purposes)
        self.mpas = [
            {
                "name": "Gulf Marine Sanctuary (MPA No-Take Zone)",
                "min_lat": 9.0, "max_lat": 10.0,
                "min_lon": 78.5, "max_lon": 79.5,
                "restriction": "Strictly No-Take Zone. Fishing and anchoring prohibited."
            }
        ]
        
        self.crz_zones = [
            {
                "name": "CRZ-I Ecologically Sensitive Mangrove/Coral Belt",
                "min_lat": 13.0, "max_lat": 13.5,
                "min_lon": 80.1, "max_lon": 80.3,
                "restriction": "Restricted industrial activity and unauthorized nearshore trawling."
            }
        ]

    def check_position(self, lat: float, lon: float) -> Dict[str, Any]:
        """Checks if given coordinates fall inside any MPA or sensitive CRZ."""
        violations = []
        
        # Check MPA compliance
        for mpa in self.mpas:
            if mpa["min_lat"] <= lat <= mpa["max_lat"] and mpa["min_lon"] <= lon <= mpa["max_lon"]:
                violations.append({
                    "zone_type": "MPA",
                    "name": mpa["name"],
                    "details": mpa["restriction"]
                })
                
        # Check CRZ compliance
        for crz in self.crz_zones:
            if crz["min_lat"] <= lat <= crz["max_lat"] and crz["min_lon"] <= lon <= crz["max_lon"]:
                violations.append({
                    "zone_type": "CRZ",
                    "name": crz["name"],
                    "details": crz["restriction"]
                })
                
        return {
            "is_violation": len(violations) > 0,
            "violations": violations
        }

zoning_service = ZoningService()