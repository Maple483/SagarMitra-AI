"""Marine productivity analytics for ORCA."""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import math, re
import numpy as np
import pandas as pd
import requests
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/marine-productivity", tags=["Marine Productivity"])
BASE=Path(__file__).resolve().parent/"data"
LANDINGS=BASE/"Combined_Marine_Landings.csv"
ENVIRONMENT=BASE/"synthetic_indian_coastal_sst_chlorophyll_2007_2012.csv"
PFZ_FILE=BASE/"pfz_advisories.csv"
YEARS=list(range(2007,2013))
OPEN_METEO_MARINE="https://marine-api.open-meteo.com/v1/marine"
NOAA_MUR_ERDDAP="https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.json"
NOAA_CHL_GAPFILLED_ERDDAP="https://coastwatch.pfeg.noaa.gov/erddap/griddap/nesdisVHNnoaaSNPPnoaa20chlaGapfilledDaily.json"
NOAA_CHL_NRT_ERDDAP="https://coastwatch.pfeg.noaa.gov/erddap/griddap/nesdisVHNnoaa20chlaDaily_Lon0360.json"


def _state_columns(df):
    result={}; aliases={"Pondi- cherry":"Puducherry","A.P.":"Andhra Pradesh","T.N.":"Tamil Nadu","W.B.":"West Bengal","A & N Islands":"Andaman & Nicobar","Orissa":"Odisha"}
    for col in df.columns:
        if "REGION NO." not in col or "Total" in col: continue
        tail=col.rsplit(" - ",1)[-1].strip(); result[aliases.get(tail,tail)]=col
    return result

def _load():
    if not LANDINGS.exists() or not ENVIRONMENT.exists(): raise FileNotFoundError("Marine productivity data files are missing")
    land=pd.read_csv(LANDINGS); env=pd.read_csv(ENVIRONMENT)
    land["Year"]=pd.to_numeric(land["Year"],errors="coerce"); env["Year"]=pd.to_numeric(env["Year"],errors="coerce").astype(int); env["Month"]=pd.to_numeric(env["Month"],errors="coerce").astype(int); env["State"]=env["State"].astype(str).str.strip()
    return land,env,_state_columns(land)

def _clean(v): return re.sub(r"\s+"," ",str(v).strip())
def _records(df): return [{k:(v.item() if hasattr(v,"item") else v) for k,v in row.items()} for row in df.to_dict("records")]

def _landing_year_species(land,col):
    x=land[["Year","Species",col]].copy(); x[col]=pd.to_numeric(x[col],errors="coerce").fillna(0); x=x.rename(columns={col:"catch_tonnes"}); x=x[x["Species"].astype(str).str.strip().str.lower()!="total"]; x["Species"]=x["Species"].astype(str).str.strip(); return x.groupby(["Year","Species"],as_index=False)["catch_tonnes"].sum()
def _corr(a,b):
    z=pd.concat([a,b],axis=1).dropna()
    if len(z)<3 or z.iloc[:,0].nunique()<2 or z.iloc[:,1].nunique()<2:return None
    return float(z.iloc[:,0].corr(z.iloc[:,1]))
def _trend(values):
    y=pd.to_numeric(values,errors="coerce").dropna().to_numpy(float)
    if len(y)<2:return {"direction":"stable","slope":0.0,"percent_change":0.0}
    slope=float(np.polyfit(np.arange(len(y),dtype=float),y,1)[0]); first,last=float(y[0]),float(y[-1]); pct=((last-first)/abs(first)*100) if first else 0; norm=abs(slope)/(float(np.mean(abs(y))) or 1); direction="stable" if norm<=.02 else ("increasing" if slope>0 else "decreasing"); return {"direction":direction,"slope":slope,"percent_change":pct}

def _explain(m,seasonal,species,trends):
    d=_trend(m["catch"])["direction"]; sr=_corr(m["catch"],m["sst"]); cr=_corr(m["catch"],m["chlorophyll"]); peak=seasonal.loc[seasonal["mean_catch"].idxmax(),"Season"] if not seasonal.empty else None
    text=(f"For {species}, " if species else "For total catch, ")+(("Landings are broadly stable over 2007–2012." if d=="stable" else f"Landings are {d} over 2007–2012."))+f" SST is {trends['sst']['direction']} and chlorophyll-a is {trends['chlorophyll']['direction']}. "
    text+=("Higher SST tends to occur with higher landings. " if sr is not None and sr>=.3 else "Higher SST tends to occur with lower landings. " if sr is not None and sr<=-.3 else "There is no clear SST relationship. ")
    text+=("Higher chlorophyll-a tends to occur with higher landings." if cr is not None and cr>=.3 else "Higher chlorophyll-a tends to occur with lower landings." if cr is not None and cr<=-.3 else "There is no clear chlorophyll-a relationship.")
    if peak:text+=f" Highest average catch is in {peak.replace('_',' ')}."
    return {"direction":d,"text":text,"caution":"The 2007–2012 SST/chlorophyll series is synthetic and is retained for historical visualization only.","peak_season":peak,"sst_trend":trends["sst"]["direction"],"chlorophyll_trend":trends["chlorophyll"]["direction"],"sst_effect":"Positive association" if sr is not None and sr>=.3 else "Negative association" if sr is not None and sr<=-.3 else "No clear association","chlorophyll_effect":"Positive association" if cr is not None and cr>=.3 else "Negative association" if cr is not None and cr<=-.3 else "No clear association"}

def build_analysis(state,species=None,start_year=2007,end_year=2012):
    land,env,states=_load(); state=_clean(state)
    if state not in states: raise HTTPException(404,detail={"message":"Unknown coastal region","supported_states":sorted(states)})
    x=_landing_year_species(land,states[state]); x=x[x["Year"].between(start_year,end_year)]
    if species:x=x[x["Species"].str.lower()==species.strip().lower()]
    annual=x.groupby("Year",as_index=False)["catch_tonnes"].sum().rename(columns={"catch_tonnes":"catch"}); annual=pd.DataFrame({"Year":list(range(start_year,end_year+1))}).merge(annual,on="Year",how="left").fillna({"catch":0}); aa=annual.copy(); sd=aa["catch"].std(ddof=0); aa["catch_z"]=0 if sd==0 else (aa["catch"]-aa["catch"].mean())/sd; aa["catch_anomaly"]=aa["catch_z"].abs()>=2
    e=env[(env["State"]==state)&env["Year"].between(start_year,end_year)].copy(); e["catch"]=e["Year"].map(dict(zip(annual["Year"],annual["catch"])))
    ea=e.groupby("Year",as_index=False).agg(sst=("SST_C","mean"),chlorophyll=("Chlorophyll_mg_m3","mean"),sst_anomaly=("SST_anomaly_C","mean"),chlorophyll_anomaly=("Chlorophyll_anomaly_mg_m3","mean")); m=annual.merge(ea,on="Year",how="left"); m["catch_z"]=aa["catch_z"].values; m["catch_anomaly"]=aa["catch_anomaly"].values; m["catch_growth_pct"]=(m["catch"].pct_change()*100).replace([np.inf,-np.inf],None)
    seasonal=e.groupby("Season",as_index=False).agg(mean_catch=("catch","mean"),mean_sst=("SST_C","mean"),mean_chlorophyll=("Chlorophyll_mg_m3","mean"),months=("Month","count")); order={"Winter":0,"Pre-Monsoon":1,"Monsoon":2,"Post-Monsoon":3}; seasonal["_o"]=seasonal["Season"].map(order).fillna(99); seasonal=seasonal.sort_values("_o").drop(columns="_o")
    sy=x.groupby(["Year","Species"],as_index=False)["catch_tonnes"].sum(); top=sy.groupby("Species",as_index=False)["catch_tonnes"].sum().sort_values("catch_tonnes",ascending=False).head(8); annual_env=m[["Year","sst","chlorophyll"]].dropna(); trends={"sst":_trend(annual_env["sst"]),"chlorophyll":_trend(annual_env["chlorophyll"])}
    return {"state":state,"species_filter":species,"environment_is_synthetic":True,"annual":_records(m.fillna(0).round(4)),"seasonal":_records(seasonal.fillna(0).round(4)),"top_species":_records(top.round(2)),"species":sorted(sy["Species"].unique().tolist()),"correlation":{"catch_vs_sst":_corr(m["catch"],m["sst"]),"catch_vs_chlorophyll":_corr(m["catch"],m["chlorophyll"])},"environment_trends":trends,"anomaly_rule":"|z-score| >= 2","anomalies":_records(m.loc[m["catch_anomaly"],["Year","catch","catch_z"]]),"explanation":_explain(m,seasonal,species,trends)}

@router.get("/regions")
def regions():
    _,e,_=_load(); return {"regions":sorted(e["State"].unique().tolist()),"years":YEARS}
@router.get("/species")
def species(state:str=Query(...)):
    land,_,states=_load(); state=_clean(state)
    if state not in states:raise HTTPException(404,detail={"message":"Unknown coastal region","supported_states":sorted(states)})
    x=_landing_year_species(land,states[state]); return {"state":state,"species":sorted(x["Species"].dropna().unique().tolist())}
@router.get("/environment")
def environment(state:str=Query(...),start_year:int=2007,end_year:int=2012):
    _,env,_=_load(); state=_clean(state); x=env[(env["State"]==state)&env["Year"].between(start_year,end_year)].copy()
    if x.empty:raise HTTPException(404,detail={"message":"No environmental data for this coastal region","state":state})
    x=x.sort_values(["Year","Month"]); rows=x[["Year","Month","Season","SST_C","Chlorophyll_mg_m3","SST_anomaly_C","Chlorophyll_anomaly_mg_m3"]].copy(); rows["label"]=rows["Year"].astype(str)+"-"+rows["Month"].astype(str).str.zfill(2); return {"state":state,"start_year":start_year,"end_year":end_year,"monthly":_records(rows.round(4)),"sst_trend":_trend(rows["SST_C"]),"chlorophyll_trend":_trend(rows["Chlorophyll_mg_m3"]),"note":"Monthly means from the synthetic 2007–2012 coastal dataset."}
@router.get("/analysis")
def analysis(state:str=Query(...),species:Optional[str]=Query(None),start_year:int=2007,end_year:int=2012):return build_analysis(state,species,start_year,end_year)
@router.get("/compare")
def compare(region_a:str=Query(...),region_b:str=Query(...),species:Optional[str]=Query(None)):
    a,b=build_analysis(region_a,species),build_analysis(region_b,species); avg=lambda rows,key:float(np.mean([r[key] for r in rows])) if rows else 0
    return {"region_a":{"state":a["state"],"mean_catch":avg(a["annual"],"catch"),"mean_sst":avg(a["annual"],"sst"),"mean_chlorophyll":avg(a["annual"],"chlorophyll"),"correlation":a["correlation"]},"region_b":{"state":b["state"],"mean_catch":avg(b["annual"],"catch"),"mean_sst":avg(b["annual"],"sst"),"mean_chlorophyll":avg(b["annual"],"chlorophyll"),"correlation":b["correlation"]}}

# PFZ finder: existing advisory locations ranked using proximity, advisory freshness,
# candidate-level live SST/chlorophyll and the repository's 2007–2012 historical SST/chlorophyll climatology.
def _hav(a,b,c,d):
    R=6371.0088; p1,p2=math.radians(a),math.radians(c); dp=math.radians(c-a); dl=math.radians(d-b); q=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2; return 2*R*math.asin(min(1,math.sqrt(q)))
def _pfz():
    if not PFZ_FILE.exists():return pd.DataFrame()
    d=pd.read_csv(PFZ_FILE,encoding="utf-8-sig"); d.columns=[str(c).strip() for c in d.columns]
    for c in ["Latitude_Decimal","Longitude_Decimal","Bearing (deg)"]:d[c]=pd.to_numeric(d[c],errors="coerce")
    return d.dropna(subset=["Latitude_Decimal","Longitude_Decimal"]).copy()
def _marine(lat,lon):
    try:
        p={"latitude":lat,"longitude":lon,"current":"sea_surface_temperature,wave_height,wave_direction,wave_period,ocean_current_velocity,ocean_current_direction","timezone":"GMT","cell_selection":"sea"}; r=requests.get(OPEN_METEO_MARINE,params=p,timeout=8); r.raise_for_status(); c=r.json().get("current",{}); return {"sst_c":c.get("sea_surface_temperature"),"wave_height_m":c.get("wave_height"),"wave_direction_deg":c.get("wave_direction"),"wave_period_s":c.get("wave_period"),"current_velocity_kmh":c.get("ocean_current_velocity"),"current_direction_deg":c.get("ocean_current_direction"),"source":"Open-Meteo Marine"}
    except Exception as e:return {"sst_c":None,"wave_height_m":None,"wave_direction_deg":None,"wave_period_s":None,"current_velocity_kmh":None,"current_direction_deg":None,"source":"Live marine feed unavailable","error":str(e)}
def _sat_sst(lat,lon):
    date=datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    try:
        q=f"analysed_sst[({date})][({lat})][({lon})]"; r=requests.get(NOAA_MUR_ERDDAP,params={"query":q},timeout=8); r.raise_for_status(); rows=r.json().get("table",{}).get("rows",[]); v=rows[0][-1] if rows else None; return float(v) if v is not None and float(v)>-100 else None
    except Exception:return None

def _sat_chlorophyll(lat,lon):
    end=datetime.now(timezone.utc); start=end-timedelta(days=14)
    start_s=start.strftime("%Y-%m-%dT00:00:00Z"); end_s=end.strftime("%Y-%m-%dT23:59:59Z")
    for endpoint in (NOAA_CHL_GAPFILLED_ERDDAP,NOAA_CHL_NRT_ERDDAP):
        try:
            q=f"chlor_a[({start_s}):1:({end_s})][({lat})][({lon})]"; r=requests.get(endpoint,params={"query":q},timeout=10); r.raise_for_status(); rows=r.json().get("table",{}).get("rows",[])
            vals=[]
            for row in rows:
                try:
                    v=float(row[-1])
                    if math.isfinite(v) and v>0: vals.append(v)
                except Exception: pass
            if vals:return float(vals[-1])
        except Exception: pass
    return None

def _fresh(text,now):
    m=re.search(r"FROM\s+(\d{1,2}\s+\w+\s+\d{4})\s+TO\s+(\d{1,2}\s+\w+\s+\d{4})",str(text),re.I)
    if not m:return .5
    try:s,e=datetime.strptime(m.group(1),"%d %b %Y").replace(tzinfo=timezone.utc),datetime.strptime(m.group(2),"%d %b %Y").replace(tzinfo=timezone.utc)
    except ValueError:return .5
    if s<=now<=e:return 1.0
    return max(0.0,1.0-(now-e).total_seconds()/(14*86400)) if now>e else .8

def _state_key(state):
    s=_clean(state).lower()
    aliases={
        "north andhra pradesh":"andhra pradesh",
        "south andhra pradesh":"andhra pradesh",
        "north tamil nadu":"tamil nadu",
        "south tamil nadu":"tamil nadu",
        "pondicherry":"puducherry",
        "pondy":"puducherry",
        "a & n islands":"andaman & nicobar",
    }
    return aliases.get(s,s)

def _sst_suitability(sst):
    if sst is None:return None
    try:
        v=float(sst)
        if not math.isfinite(v):return None
        # Generic PFZ suitability centered near 27°C; broad 21–33°C envelope.
        return round(max(0.0,min(100.0,100.0-abs(v-27.0)/6.0*100.0)),1)
    except Exception:return None

def _scale_score(value,low,high):
    if value is None:return None
    try:
        v=float(value); lo=float(low); hi=float(high)
        if not (math.isfinite(v) and math.isfinite(lo) and math.isfinite(hi)) or hi<=lo:return None
        return round(max(0.0,min(100.0,(v-lo)/(hi-lo)*100.0)),1)
    except Exception:return None

def _historical_profiles(env):
    h=env[["State","SST_C","Chlorophyll_mg_m3"]].copy()
    h["SST_C"]=pd.to_numeric(h["SST_C"],errors="coerce"); h["Chlorophyll_mg_m3"]=pd.to_numeric(h["Chlorophyll_mg_m3"],errors="coerce"); h=h.dropna(subset=["State","SST_C","Chlorophyll_mg_m3"])
    if h.empty:return {},None,None
    chl_low=float(h["Chlorophyll_mg_m3"].quantile(.10)); chl_high=float(h["Chlorophyll_mg_m3"].quantile(.90))
    profiles={}
    for state,g in h.groupby("State"):
        profiles[_state_key(state)]={
            "sst_mean_c":float(g["SST_C"].mean()),
            "chlorophyll_mean_mg_m3":float(g["Chlorophyll_mg_m3"].mean()),
            "sst_score":float(np.mean([_sst_suitability(v) for v in g["SST_C"].tolist() if _sst_suitability(v) is not None])),
            "chlorophyll_score":_scale_score(float(g["Chlorophyll_mg_m3"].mean()),chl_low,chl_high),
        }
    return profiles,chl_low,chl_high

def _candidate_live(point):
    lat=float(point["Latitude_Decimal"]); lon=float(point["Longitude_Decimal"])
    sst=_sat_sst(lat,lon); chl=_sat_chlorophyll(lat,lon); sst_source="NASA/JPL MUR satellite SST via NOAA ERDDAP" if sst is not None else ""
    if sst is None:
        fallback=_marine(lat,lon); sst=fallback.get("sst_c"); sst_source=fallback.get("source","") if sst is not None else ""
    return {"sst_c":sst,"chlorophyll_mg_m3":chl,"sst_source":sst_source,"chlorophyll_source":"NOAA VIIRS chlorophyll via CoastWatch ERDDAP" if chl is not None else ""}

@router.get("/pfz")
def find_pfz(lat:float=Query(...,ge=-90,le=90),lon:float=Query(...,ge=-180,le=180),max_results:int=Query(5,ge=1,le=10)):
    d=_pfz(); now=datetime.now(timezone.utc); marine=_marine(lat,lon); sat=_sat_sst(lat,lon)
    if sat is not None:marine["satellite_sst_c"]=sat; marine["satellite_sst_source"]="NASA/JPL MUR satellite SST via NOAA ERDDAP"
    if d.empty:return {"status":"NO_ADVISORIES","user_location":{"lat":lat,"lon":lon},"live_conditions":marine,"results":[],"message":"No PFZ advisory records are available."}

    _,env,_=_load(); profiles,chl_low,chl_high=_historical_profiles(env)

    live_by_index={}
    with ThreadPoolExecutor(max_workers=min(8,len(d))) as executor:
        futures={executor.submit(_candidate_live,row):idx for idx,(_,row) in enumerate(d.iterrows())}
        for future in as_completed(futures):
            idx=futures[future]
            try:live_by_index[idx]=future.result()
            except Exception:live_by_index[idx]={"sst_c":None,"chlorophyll_mg_m3":None,"sst_source":"","chlorophyll_source":""}

    out=[]
    for idx,(_,r) in enumerate(d.iterrows()):
        dist=_hav(lat,lon,float(r["Latitude_Decimal"]),float(r["Longitude_Decimal"])); fresh=_fresh(r.get("Forecast_Validity",""),now)
        live=live_by_index.get(idx,{"sst_c":None,"chlorophyll_mg_m3":None}); live_sst=live.get("sst_c"); live_chl=live.get("chlorophyll_mg_m3")
        hist=profiles.get(_state_key(r.get("State","")))
        components=[]; component_details={}

        distance_score=max(0.0,min(100.0,100.0*math.exp(-dist/250.0))); components.append((.20,distance_score)); component_details["proximity"] = round(distance_score,1)
        freshness_score=max(0.0,min(100.0,fresh*100.0)); components.append((.10,freshness_score)); component_details["advisory_freshness"] = round(freshness_score,1)

        live_sst_score=_sst_suitability(live_sst)
        if live_sst_score is not None:components.append((.20,live_sst_score)); component_details["live_sst"] = live_sst_score
        live_chl_score=_scale_score(live_chl,chl_low,chl_high)
        if live_chl_score is not None:components.append((.20,live_chl_score)); component_details["live_chlorophyll"] = live_chl_score

        if hist:
            if hist.get("sst_score") is not None:components.append((.15,float(hist["sst_score"])*1.0)); component_details["historical_sst"] = round(float(hist["sst_score"]),1)
            if hist.get("chlorophyll_score") is not None:components.append((.15,float(hist["chlorophyll_score"])*1.0)); component_details["historical_chlorophyll"] = round(float(hist["chlorophyll_score"]),1)

        weight_total=sum(w for w,_ in components) or 1.0
        score=sum(w*s for w,s in components)/weight_total
        reasons=[]
        if live_sst is not None:reasons.append(f"live SST {live_sst:.2f}°C (suitability {live_sst_score:.0f}/100)")
        if live_chl is not None:reasons.append(f"live chlorophyll {live_chl:.3f} mg/m³ (productivity {live_chl_score:.0f}/100)")
        if hist:
            reasons.append(f"historical {hist['sst_mean_c']:.2f}°C SST mean (2007–2012)")
            reasons.append(f"historical {hist['chlorophyll_mean_mg_m3']:.3f} mg/m³ chlorophyll mean (2007–2012)")
        reasons.append(f"{dist:.1f} km from your location")

        out.append({
            "distance_km":round(dist,1),"rank_score":round(max(0,min(100,score)),1),
            "from_coast":r.get("From the coast of",r.get("﻿From the coast of","")),"direction":r.get("Direction",""),"bearing_deg":r.get("Bearing (deg)"),
            "distance_advisory_km":r.get("Distance (km) From-To",""),"depth_m":r.get("Depth (mtr) From-To",""),"lat":float(r["Latitude_Decimal"]),"lon":float(r["Longitude_Decimal"]),
            "state":r.get("State",""),"forecast_validity":r.get("Forecast_Validity",""),"reasons":reasons,
            "live_sst_c":live_sst,"live_chlorophyll_mg_m3":live_chl,
            "historical_sst_mean_c":round(hist["sst_mean_c"],3) if hist else None,
            "historical_chlorophyll_mean_mg_m3":round(hist["chlorophyll_mean_mg_m3"],4) if hist else None,
            "score_components":component_details,
        })

    out.sort(key=lambda x:(-x["rank_score"],x["distance_km"])); [item.update(rank=i) for i,item in enumerate(out[:max_results],1)]
    return {
        "status":"OK","user_location":{"lat":lat,"lon":lon},"generated_at":now.isoformat(),"live_conditions":marine,"results":out[:max_results],
        "method":"PFZ ranking uses 20% proximity + 10% advisory freshness + 20% live SST + 20% live chlorophyll + 15% historical SST + 15% historical chlorophyll. Historical SST/chlorophyll are the repository's synthetic 2007–2012 coastal series; live SST uses NASA/JPL MUR via NOAA ERDDAP and live chlorophyll uses NOAA VIIRS via CoastWatch ERDDAP. Decision support only; not a guarantee of fish presence.",
        "sources":{"pfz_advisories":"orca-backend/data/pfz_advisories.csv","historical_environment":"orca-backend/data/synthetic_indian_coastal_sst_chlorophyll_2007_2012.csv","satellite_sst":"NASA/JPL MUR via NOAA ERDDAP","satellite_chlorophyll":"NOAA VIIRS via CoastWatch ERDDAP","marine_conditions":"Open-Meteo Marine"}
    }
