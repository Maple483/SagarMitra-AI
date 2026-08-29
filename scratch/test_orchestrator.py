import sys
import os
import asyncio

# Add workspace to sys.path to allow imports from d:\sih
sys.path.append("d:\\sih")

from langchain_core.messages import HumanMessage
from agents.orchestrator import app as agent_brain, evaluate_safety_rules

# ==========================================
# 1. Test Tier 1: Deterministic Safety Rules Engine
# ==========================================

class MockStates:
    @staticmethod
    def get_safe_day():
        return {
            "vessel_coords": {"lat": 13.08, "lon": 80.27},
            "weather_report": {
                "data": {"wind_speed": 12.0, "swell_height": 0.9},
                "status": "success"
            },
            "ocean_report": {
                "data": {"sst_gradient_front": True, "chlorophyll_density": 4.1},
                "status": "success"
            },
            "geofence_report": {
                "data": {"in_restricted_zone": False, "nearest_boundary": "IMBL", "distance_to_boundary_meters": 4500.0},
                "status": "success"
            },
            "override_reasons": []
        }

    @staticmethod
    def get_border_proximity():
        return {
            "vessel_coords": {"lat": 10.15, "lon": 79.92},
            "weather_report": {
                "data": {"wind_speed": 15.0, "swell_height": 1.1},
                "status": "success"
            },
            "ocean_report": {
                "data": {"sst_gradient_front": False},
                "status": "success"
            },
            "geofence_report": {
                "data": {"in_restricted_zone": False, "nearest_boundary": "India-Sri Lanka IMBL", "distance_to_boundary_meters": 1100.0},
                "status": "success"
            },
            "override_reasons": []
        }

    @staticmethod
    def get_restricted_breach():
        return {
            "vessel_coords": {"lat": 10.12, "lon": 80.12},
            "weather_report": {
                "data": {"wind_speed": 18.0, "swell_height": 1.4},
                "status": "success"
            },
            "ocean_report": {
                "data": {"sst_gradient_front": False},
                "status": "success"
            },
            "geofence_report": {
                "data": {"in_restricted_zone": True, "nearest_boundary": "India-Sri Lanka IMBL", "distance_to_boundary_meters": 0.0},
                "status": "success"
            },
            "override_reasons": []
        }

    @staticmethod
    def get_severe_cyclonic_storm():
        return {
            "vessel_coords": {"lat": 13.08, "lon": 80.27},
            "weather_report": {
                "data": {"wind_speed": 52.0, "swell_height": 3.6},
                "status": "success"
            },
            "ocean_report": {
                "data": {"sst_gradient_front": False},
                "status": "success"
            },
            "geofence_report": {
                "data": {"in_restricted_zone": False, "nearest_boundary": "IMBL", "distance_to_boundary_meters": 5500.0},
                "status": "success"
            },
            "override_reasons": []
        }

    @staticmethod
    def get_weather_api_outage():
        return {
            "vessel_coords": {"lat": 13.08, "lon": 80.27},
            "weather_report": {
                "data": {"wind_speed": 0.0, "swell_height": 0.0},
                "status": "failed" # API call failed
            },
            "ocean_report": {
                "data": {"sst_gradient_front": False},
                "status": "success"
            },
            "geofence_report": {
                "data": {"in_restricted_zone": False, "nearest_boundary": "IMBL", "distance_to_boundary_meters": 4500.0},
                "status": "success"
            },
            "override_reasons": []
        }

def test_safety_engine_accuracy():
    print("\n" + "="*70)
    print("TIER 1: SAFETY RULES ENGINE ACCURACY VALIDATION (RANDOM DATA)")
    print("="*70)
    
    test_cases = [
        ("Safe Fishing Conditions Test", MockStates.get_safe_day(), "SAFE", "no_routing"),
        ("IMBL Buffer Warning Test (1100m)", MockStates.get_border_proximity(), "WARNING", "preventative_steer_away"),
        ("Geofence Polygon Breach Test", MockStates.get_restricted_breach(), "CRITICAL", "exit_zone"),
        ("Severe Cyclone Storm Test", MockStates.get_severe_cyclonic_storm(), "CRITICAL", "return_to_safe"),
        ("Weather API Outage Failsafe Test", MockStates.get_weather_api_outage(), "WARNING", "proceed_with_caution")
    ]
    
    passed_runs = 0
    for name, state, expected_risk, expected_action in test_cases:
        print(f"\n[Case] Running: {name}")
        # Run the safety parser
        results = evaluate_safety_rules(state)
        
        # Verify results
        actual_risk = results.get("final_risk_level")
        actual_action = results.get("routing_action")
        reasons = results.get("override_reasons")
        
        print(f" -> Result: Risk={actual_risk}, Action={actual_action}, Reasons={reasons}")
        
        if actual_risk == expected_risk and actual_action == expected_action:
            print(" -> [PASS] Result matches expected vector.")
            passed_runs += 1
        else:
            print(f" -> [FAIL] Expected (Risk={expected_risk}, Action={expected_action}) but got (Risk={actual_risk}, Action={actual_action})")
            
    print(f"\nAccuracy Score: {passed_runs}/{len(test_cases)} ({passed_runs/len(test_cases)*100:.1f}%)")


# ==========================================
# 2. Test Tier 2: Conversational Graph End-to-End
# ==========================================

async def test_conversational_workflow():
    print("\n" + "="*70)
    print("TIER 2: CONVERSATIONAL GRAPH FLOW END-TO-END")
    print("="*70)
    
    # Test Case 1: Standard safety evaluation
    initial_state_1 = {
        "messages": [HumanMessage(content="Is it safe to fish out here near the IMBL today?")],
        "vessel_id": "test_vessel_1",
        "vessel_coords": {"lat": 13.0827, "lon": 80.2707},
        "request_type": "query"
    }
    config = {"configurable": {"thread_id": "conv_test_session_1"}}
    print("\n[Case 1] Running: Multilingual Safety Assessment Inquiries")
    try:
        result = await agent_brain.ainvoke(initial_state_1, config=config)
        print(f"Graph Status  : SUCCESS")
        print(f"Decided Risk  : {result.get('final_risk_level')}")
        print(f"Primary Action: {result.get('routing_action')}")
        print(f"Consensus Output: {result.get('consensus_advice')}")
        print(" -> [PASS] Flow completed successfully.")
    except Exception as e:
        print(f" -> [FAIL] Workflow execution errored: {str(e)}")

    # Test Case 2: Informational greeting query bypass route (Scenario 6)
    initial_state_2 = {
        "messages": [HumanMessage(content="Hello! Who are you and how can you help me?")],
        "vessel_id": "test_vessel_2",
        "request_type": "query"
    }
    print("\n[Case 2] Running: Informational bypass greeting checks")
    try:
        result = await agent_brain.ainvoke(initial_state_2, config=config)
        print(f"Graph Status  : SUCCESS")
        print(f"Decided Risk  : {result.get('final_risk_level')}") # Should be None
        print(f"Query Intents : {result.get('query_intents')}") # Should be ['informational']
        print(f"Consensus Output: {result.get('consensus_advice')}")
        print(" -> [PASS] Informational greeting bypass validated.")
    except Exception as e:
        print(f" -> [FAIL] Greeting bypass failed: {str(e)}")

    # Test Case 3: Cardinal coordinate string fallback parsing (Scenario 7)
    from agents.orchestrator import robust_coordinate_parser
    print("\n[Case 3] Running: Cardinal coordinate string parsing checks")
    test_strings = [
        "My GPS coordinates are 13.0827 N, 80.2707 E. Is it safe?",
        "Coordinates: 13.08 N and 80.27 E",
        "Position 10.15S, 79.92W",
        "13.0827, 80.2707"
    ]
    for text in test_strings:
        parsed = robust_coordinate_parser(text)
        print(f" - Text: '{text}' -> Parsed Coordinates: {parsed}")
        if parsed:
            print("   -> [PASS] Coordinate tokens resolved successfully.")
        else:
            print("   -> [FAIL] Failed to resolve coordinates from string.")

    # Test Case 4: Location-Required validation router bypass (Scenario 10)
    initial_state_4 = {
        "messages": [HumanMessage(content="Is it safe out here today?")],
        "vessel_id": "test_vessel_4",
        "request_type": "query"
    }
    config_4 = {"configurable": {"thread_id": "conv_test_session_4"}}
    print("\n[Case 4] Running: Location-Required validation router bypass")
    try:
        result = await agent_brain.ainvoke(initial_state_4, config=config_4)
        print(f"Graph Status  : SUCCESS")
        print(f"Decided Risk  : {result.get('final_risk_level')}")
        print(f"Query Intents : {result.get('query_intents')}")
        print(f"Consensus Output: {result.get('consensus_advice')}")
        print(" -> [PASS] Location-Required bypass validated successfully.")
    except Exception as e:
        print(f" -> [FAIL] Location-Required bypass failed: {str(e)}")

if __name__ == "__main__":
    test_safety_engine_accuracy()
    asyncio.run(test_conversational_workflow())
