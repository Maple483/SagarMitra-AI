"""
End-to-End API Route tests for Marine Productivity endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_api_regions():
    resp = client.get("/api/marine-productivity/regions")
    assert resp.status_code == 200
    regions = resp.json()
    assert len(regions) == 9
    assert "Karnataka" in regions
    assert "Kerala" in regions
    assert "Gujarat" in regions


def test_api_species():
    resp = client.get("/api/marine-productivity/species?state=Karnataka")
    assert resp.status_code == 200
    species_list = resp.json()
    assert len(species_list) >= 8
    assert "Sardine" in species_list or "Oil Sardine" in species_list


def test_api_timeseries():
    resp = client.get(
        "/api/marine-productivity/timeseries?state=Karnataka&species=Sardine&variable=sst"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "Karnataka"
    assert data["observed_years"] == [2007, 2008, 2009, 2010, 2011, 2012]
    assert len(data["scenario_years"]) == 14
    assert "landings" in data
    assert "environmental" in data
    assert "trajectories" in data
    assert "seasonal_profile" in data
    assert "provenance_encoding" in data


def test_api_explain_grounded():
    payload = {
        "state": "Karnataka",
        "species": "Sardine",
        "environmental_variable": "sst",
        "lag_years": 1,
        "query_text": "Why did productivity change in Karnataka?",
    }
    resp = client.post("/api/marine-productivity/explain", json=payload)
    assert resp.status_code == 200
    res = resp.json()

    # Verify audit metadata
    assert res["analysis_id"].startswith("ORCA-MP-")
    assert res["snapshot_id"] == "CMFRI-NOAA-ESA-SNAPSHOT-2026A"
    assert len(res["dataset_sha256_hash"]) == 64

    # Verify observed evidence
    obs = res["observed_evidence"]
    assert obs["n_observed_years"] == 6
    assert obs["n_paired"] == 5
    assert obs["n_valid"] == 5
    assert obs["n_difference_pairs"] == 4
    assert obs["pearson_r"] is not None
    assert obs["level_nominal_p_value_iid_assumed"] is not None

    # Verify scenario section
    scen = res["scenario_trajectory"]
    assert scen["n_modeled"] == 14
    assert scen["n_total"] == 20
    assert scen["modeled_fraction_pct"] == 70.0

    # Verify non-causal phrasing in narrative
    assert "caused" not in res["direct_answer"].lower()
    assert "drove" not in res["direct_answer"].lower()
    assert "led to" not in res["direct_answer"].lower()


def test_api_explain_ungrounded_query():
    payload = {
        "state": "Karnataka",
        "species": "Sardine",
        "environmental_variable": "sst",
        "lag_years": 1,
        "query_text": "Did fuel subsidies and trawler boat quotas increase sardine catch?",
    }
    resp = client.post("/api/marine-productivity/explain", json=payload)
    assert resp.status_code == 200
    res = resp.json()
    assert res["grounding_status"] == "UNSUPPORTED_VARIABLES_DETECTED"
    assert any(w in res["unsupported_variables"] for w in ["fuel", "subsidy", "boat", "quota"])


def test_api_satellite_info():
    resp = client.get("/api/marine-productivity/satellite-info")
    assert resp.status_code == 200
    data = resp.json()
    assert "wms_endpoint" in data
    assert "layers" in data
    assert "sst" in data["layers"]
    assert "chlorophyll" in data["layers"]
    assert "attribution" in data
    assert "NASA EOSDIS GIBS" in data["attribution"]
