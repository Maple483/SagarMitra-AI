"""Marine productivity analytics for ORCA."""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import re

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/marine-productivity", tags=["Marine Productivity"])
BASE = Path(__file__).resolve().parent / "data"
LANDINGS = BASE / "Combined_Marine_Landings.csv"
ENVIRONMENT = BASE / "synthetic_indian_coastal_sst_chlorophyll_2007_2012.csv"
YEARS = list(range(2007, 2013))


def _state_columns(df: pd.DataFrame) -> dict[str, str]:
    result: dict[str, str] = {}
    aliases = {
        "Pondi- cherry": "Puducherry",
        "A.P.": "Andhra Pradesh",
        "T.N.": "Tamil Nadu",
        "W.B.": "West Bengal",
        "A & N Islands": "Andaman & Nicobar",
        "Orissa": "Odisha",
    }
    for col in df.columns:
        if "REGION NO." not in col or "Total" in col:
            continue
        tail = col.rsplit(" - ", 1)[-1].strip()
        result[aliases.get(tail, tail)] = col
    return result


def _load():
    if not LANDINGS.exists() or not ENVIRONMENT.exists():
        raise FileNotFoundError("Marine productivity data files are missing")
    land = pd.read_csv(LANDINGS)
    env = pd.read_csv(ENVIRONMENT)
    land["Year"] = pd.to_numeric(land["Year"], errors="coerce")
    env["Year"] = pd.to_numeric(env["Year"], errors="coerce").astype(int)
    env["Month"] = pd.to_numeric(env["Month"], errors="coerce").astype(int)
    env["State"] = env["State"].astype(str).str.strip()
    return land, env, _state_columns(land)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip())


def _landing_year_species(land: pd.DataFrame, col: str) -> pd.DataFrame:
    x = land[["Year", "Species", col]].copy()
    x[col] = pd.to_numeric(x[col], errors="coerce").fillna(0)
    x = x.rename(columns={col: "catch_tonnes"})
    x = x[x["Species"].astype(str).str.strip().str.lower() != "total"]
    x["Species"] = x["Species"].astype(str).str.strip()
    return x.groupby(["Year", "Species"], as_index=False)["catch_tonnes"].sum()


def _corr(a: pd.Series, b: pd.Series) -> Optional[float]:
    z = pd.concat([a, b], axis=1).dropna()
    if len(z) < 3 or z.iloc[:, 0].nunique() < 2 or z.iloc[:, 1].nunique() < 2:
        return None
    return float(z.iloc[:, 0].corr(z.iloc[:, 1]))


def _trend(values: pd.Series) -> dict:
    y = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if len(y) < 2:
        return {"direction": "stable", "slope": 0.0, "percent_change": 0.0}
    x = np.arange(len(y), dtype=float)
    slope = float(np.polyfit(x, y, 1)[0])
    first = float(y[0])
    last = float(y[-1])
    percent = ((last - first) / abs(first) * 100.0) if first else 0.0
    mean = float(np.mean(np.abs(y))) or 1.0
    normalized = abs(slope) / mean
    direction = "stable" if normalized <= 0.02 else ("increasing" if slope > 0 else "decreasing")
    return {"direction": direction, "slope": slope, "percent_change": percent}


def _records(df: pd.DataFrame):
    return [
        {k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}
        for row in df.to_dict("records")
    ]


def _association_text(value: Optional[float], variable: str) -> str:
    if value is None:
        return f"There is not enough variation to judge a clear {variable} relationship."
    if value >= 0.30:
        return f"Higher {variable} tends to occur with higher landings in this dataset (a positive relationship)."
    if value <= -0.30:
        return f"Higher {variable} tends to occur with lower landings in this dataset (a negative relationship)."
    return f"There is no clear relationship between {variable} and landings in this dataset."


def _explain(m: pd.DataFrame, seasonal: pd.DataFrame, species: Optional[str], env_trends: dict) -> dict:
    catch_trend = _trend(m["catch"])
    direction = catch_trend["direction"]
    if direction == "stable":
        trend_text = "Landings are broadly stable over 2007–2012, so there is no meaningful overall increase or decrease."
    else:
        trend_text = f"Landings are {direction} over 2007–2012."

    sr = _corr(m["catch"], m["sst"])
    cr = _corr(m["catch"], m["chlorophyll"])
    peak = seasonal.loc[seasonal["mean_catch"].idxmax(), "Season"] if not seasonal.empty else None
    peak = peak.replace("_", " ") if peak else None

    sst_word = env_trends["sst"]["direction"]
    chl_word = env_trends["chlorophyll"]["direction"]
    sst_change = env_trends["sst"]["percent_change"]
    chl_change = env_trends["chlorophyll"]["percent_change"]

    species_prefix = f"For {species}, " if species else "For total catch, "
    text = (
        f"{species_prefix}{trend_text} Sea temperature (SST) is {sst_word} over the period "
        f"({sst_change:+.1f}% from 2007 to 2012), while chlorophyll-a is {chl_word} "
        f"({chl_change:+.1f}%). {_association_text(sr, 'SST')} {_association_text(cr, 'chlorophyll-a')} "
        "These are associations, not proof that either variable directly caused the catch change."
    )
    if peak:
        text += f" The highest average catch is in {peak}."

    if sr is not None and sr >= 0.30:
        sst_effect = "Positive association"
    elif sr is not None and sr <= -0.30:
        sst_effect = "Negative association"
    else:
        sst_effect = "No clear association"
    if cr is not None and cr >= 0.30:
        chl_effect = "Positive association"
    elif cr is not None and cr <= -0.30:
        chl_effect = "Negative association"
    else:
        chl_effect = "No clear association"

    return {
        "direction": direction,
        "text": text,
        "caution": "The SST/chlorophyll series is synthetic. Treat this as an analytical demonstration, not proof of ecological causation, until observed satellite/oceanographic data are used.",
        "peak_season": peak,
        "sst_trend": sst_word,
        "chlorophyll_trend": chl_word,
        "sst_effect": sst_effect,
        "chlorophyll_effect": chl_effect,
    }


def build_analysis(state: str, species: Optional[str] = None, start_year: int = 2007, end_year: int = 2012):
    land, env, states = _load()
    state = _clean(state)
    if state not in states:
        raise HTTPException(404, detail={"message": "Unknown coastal region", "supported_states": sorted(states.keys())})

    x = _landing_year_species(land, states[state])
    x = x[x["Year"].between(start_year, end_year)]
    if species:
        x = x[x["Species"].str.lower() == species.strip().lower()]

    annual = x.groupby("Year", as_index=False)["catch_tonnes"].sum().rename(columns={"catch_tonnes": "catch"})
    annual = pd.DataFrame({"Year": YEARS}).merge(annual, on="Year", how="left").fillna({"catch": 0})
    aa = annual.copy()
    sd = aa["catch"].std(ddof=0)
    aa["catch_z"] = 0 if sd == 0 else (aa["catch"] - aa["catch"].mean()) / sd
    aa["catch_anomaly"] = aa["catch_z"].abs() >= 2

    e = env[(env["State"] == state) & env["Year"].between(start_year, end_year)].copy()
    annual_map = dict(zip(annual["Year"], annual["catch"]))
    e["catch"] = e["Year"].map(annual_map)
    ea = e.groupby("Year", as_index=False).agg(
        sst=("SST_C", "mean"),
        chlorophyll=("Chlorophyll_mg_m3", "mean"),
        sst_anomaly=("SST_anomaly_C", "mean"),
        chlorophyll_anomaly=("Chlorophyll_anomaly_mg_m3", "mean"),
    )
    m = annual.merge(ea, on="Year", how="left")
    m["catch_z"] = aa["catch_z"].values
    m["catch_anomaly"] = aa["catch_anomaly"].values
    m["catch_growth_pct"] = (m["catch"].pct_change() * 100).replace([np.inf, -np.inf], None)

    seasonal = e.groupby("Season", as_index=False).agg(
        mean_catch=("catch", "mean"),
        mean_sst=("SST_C", "mean"),
        mean_chlorophyll=("Chlorophyll_mg_m3", "mean"),
        months=("Month", "count"),
    )
    season_order = {"Winter": 0, "Pre-Monsoon": 1, "Monsoon": 2, "Post-Monsoon": 3}
    seasonal["_order"] = seasonal["Season"].map(season_order).fillna(99)
    seasonal = seasonal.sort_values("_order").drop(columns="_order")

    sy = x.groupby(["Year", "Species"], as_index=False)["catch_tonnes"].sum()
    top = sy.groupby("Species", as_index=False)["catch_tonnes"].sum().sort_values("catch_tonnes", ascending=False).head(8)

    annual_env = m[["Year", "sst", "chlorophyll"]].dropna()
    env_trends = {"sst": _trend(annual_env["sst"]), "chlorophyll": _trend(annual_env["chlorophyll"])}
    return {
        "state": state,
        "species_filter": species,
        "environment_is_synthetic": True,
        "annual": _records(m.fillna(0).round(4)),
        "seasonal": _records(seasonal.fillna(0).round(4)),
        "top_species": _records(top.round(2)),
        "species": sorted(sy["Species"].unique().tolist()),
        "correlation": {
            "catch_vs_sst": _corr(m["catch"], m["sst"]),
            "catch_vs_chlorophyll": _corr(m["catch"], m["chlorophyll"]),
        },
        "environment_trends": env_trends,
        "anomaly_rule": "|z-score| >= 2",
        "anomalies": _records(m.loc[m["catch_anomaly"], ["Year", "catch", "catch_z"]]),
        "explanation": _explain(m, seasonal, species, env_trends),
    }


@router.get("/regions")
def regions():
    _, e, _ = _load()
    return {"regions": sorted(e["State"].unique().tolist()), "years": YEARS}


@router.get("/species")
def species(state: str = Query(...)):
    land, _, states = _load()
    state = _clean(state)
    if state not in states:
        raise HTTPException(404, detail={"message": "Unknown coastal region", "supported_states": sorted(states.keys())})
    x = _landing_year_species(land, states[state])
    return {"state": state, "species": sorted(x["Species"].dropna().unique().tolist())}


@router.get("/environment")
def environment(state: str = Query(...), start_year: int = 2007, end_year: int = 2012):
    _, env, _ = _load()
    state = _clean(state)
    x = env[(env["State"] == state) & env["Year"].between(start_year, end_year)].copy()
    if x.empty:
        raise HTTPException(404, detail={"message": "No environmental data for this coastal region", "state": state})
    x = x.sort_values(["Year", "Month"])
    rows = x[["Year", "Month", "Season", "SST_C", "Chlorophyll_mg_m3", "SST_anomaly_C", "Chlorophyll_anomaly_mg_m3"]].copy()
    rows["label"] = rows["Year"].astype(str) + "-" + rows["Month"].astype(str).str.zfill(2)
    return {
        "state": state,
        "start_year": start_year,
        "end_year": end_year,
        "monthly": _records(rows.round(4)),
        "sst_trend": _trend(rows["SST_C"]),
        "chlorophyll_trend": _trend(rows["Chlorophyll_mg_m3"]),
        "note": "Monthly means from the synthetic 2007–2012 coastal dataset.",
    }


@router.get("/analysis")
def analysis(state: str = Query(...), species: Optional[str] = Query(None), start_year: int = 2007, end_year: int = 2012):
    return build_analysis(state, species, start_year, end_year)


@router.get("/compare")
def compare(region_a: str = Query(...), region_b: str = Query(...), species: Optional[str] = Query(None)):
    a = build_analysis(region_a, species)
    b = build_analysis(region_b, species)

    def avg(rows, key):
        return float(np.mean([r[key] for r in rows])) if rows else 0

    return {
        "region_a": {
            "state": a["state"],
            "mean_catch": avg(a["annual"], "catch"),
            "mean_sst": avg(a["annual"], "sst"),
            "mean_chlorophyll": avg(a["annual"], "chlorophyll"),
            "correlation": a["correlation"],
        },
        "region_b": {
            "state": b["state"],
            "mean_catch": avg(b["annual"], "catch"),
            "mean_sst": avg(b["annual"], "sst"),
            "mean_chlorophyll": avg(b["annual"], "chlorophyll"),
            "correlation": b["correlation"],
        },
    }