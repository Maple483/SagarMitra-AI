(() => {
  if (window.__orcaPFZCatchIntelV2) return;
  window.__orcaPFZCatchIntelV2 = true;

  const nativeFetch = window.fetch.bind(window);
  const PANEL_ID = 'pfz-catch-intelligence';
  const API_HOST = 'http://localhost:8000';
  let latestExplanation = '';
  let pendingResults = null;

  const aliases = {
    'north andhra pradesh': 'Andhra Pradesh',
    'south andhra pradesh': 'Andhra Pradesh',
    'north tamil nadu': 'Tamil Nadu',
    'south tamil nadu': 'Tamil Nadu',
    'pondicherry': 'Puducherry',
    'pondy': 'Puducherry',
    'a & n islands': 'Andaman & Nicobar'
  };

  const stateName = value => {
    const raw = String(value || '').trim();
    return aliases[raw.toLowerCase()] || raw;
  };
  const n = v => Number.isFinite(Number(v)) ? Number(v) : null;
  const mean = xs => {
    const v = xs.map(n).filter(x => x !== null);
    return v.length ? v.reduce((a,b) => a+b, 0) / v.length : null;
  };
  const sd = xs => {
    const v = xs.map(n).filter(x => x !== null);
    if (v.length < 2) return null;
    const m = mean(v);
    return Math.sqrt(v.reduce((s,x) => s + (x-m)*(x-m), 0) / v.length) || null;
  };
  const corr = (xs, ys) => {
    const pairs=[];
    for(let i=0;i<Math.min(xs.length,ys.length);i++){
      const x=n(xs[i]), y=n(ys[i]);
      if(x!==null && y!==null) pairs.push([x,y]);
    }
    if(pairs.length<3) return null;
    const mx=mean(pairs.map(p=>p[0])), my=mean(pairs.map(p=>p[1]));
    const sx=sd(pairs.map(p=>p[0])), sy=sd(pairs.map(p=>p[1]));
    if(!sx || !sy) return null;
    const covariance=pairs.reduce((s,p)=>s+(p[0]-mx)*(p[1]-my),0)/pairs.length;
    return Math.max(-1,Math.min(1,covariance/(sx*sy)));
  };
  const percentile=(xs,value)=>{
    const v=n(value), a=xs.map(n).filter(x=>x!==null).sort((x,y)=>x-y);
    if(v===null || !a.length) return null;
    let lo=0,hi=a.length;
    while(lo<hi){const mid=Math.floor((lo+hi)/2);if(a[mid]<v)lo=mid+1;else hi=mid;}
    return lo/a.length;
  };
  const moneyNumber = v => n(v) === null ? '—' : n(v).toFixed(2);

  function associationScore(r,p){
    if(r===null || p===null || Math.abs(r)<0.25) return 50;
    const directional = r>0 ? p : 1-p;
    return 100 * (0.5 + 0.5*Math.min(1,Math.abs(r))*((directional*2)-1));
  }

  async function fetchAnalysis(state){
    try{
      const res=await nativeFetch(`${API_HOST}/api/marine-productivity/analysis?state=${encodeURIComponent(state)}`,{headers:{Accept:'application/json'}});
      if(!res.ok) return null;
      return await res.json();
    }catch(_){return null;}
  }

  async function enrich(payload){
    if(!payload?.results?.length) return payload;
    const enriched=await Promise.all(payload.results.map(async result=>{
      const analysis=await fetchAnalysis(stateName(result.state));
      if(!analysis) return {...result,_catch_intel:null};
      const annual=analysis.annual||[];
      const catches=annual.map(x=>x.catch), sst=annual.map(x=>x.sst), chl=annual.map(x=>x.chlorophyll);
      const sstR=corr(catches,sst), chlR=corr(catches,chl);
      const sstP=percentile(sst,result.live_sst_c), chlP=percentile(chl,result.live_chlorophyll_mg_m3);
      const sstScore=associationScore(sstR,sstP), chlScore=associationScore(chlR,chlP);
      const available=(sstR!==null?1:0)+(chlR!==null?1:0);
      const catchEnv=available ? (sstScore*(sstR!==null?Math.abs(sstR):0)+chlScore*(chlR!==null?Math.abs(chlR):0))/((sstR!==null?Math.abs(sstR):0)+(chlR!==null?Math.abs(chlR):0)||1) : 50;
      const base=n(result.rank_score) ?? 50;
      const finalScore=0.55*base+0.45*catchEnv;
      return {...result,_catch_intel:{analysis,sstR,chlR,sstP,chlP,catchEnv},_catch_environment_score:Number(finalScore.toFixed(1))};
    }));
    enriched.sort((a,b)=>((b._catch_environment_score??b.rank_score??0)-(a._catch_environment_score??a.rank_score??0))||((a.distance_km??Infinity)-(b.distance_km??Infinity)));
    enriched.forEach((r,i)=>{r.rank=i+1;});
    const best=enriched[0];
    latestExplanation=makeExplanation(best);
    pendingResults=enriched;
    return {...payload,results:enriched,advisory_message:latestExplanation,method:`${payload.method||'PFZ ranking'} Catch history is also compared with historical SST/chlorophyll for each candidate coastal region, then today's live SST/chlorophyll are checked against those past relationships.`};
  }

  function makeExplanation(result){
    if(!result) return 'No fishing-zone recommendation is available for this location.';
    const intel=result._catch_intel;
    const state=stateName(result.state);
    const parts=[`This fishing zone is recommended because it gives the best overall match among the available PFZ advisories.`];
    if(result.distance_km!=null) parts.push(`It is about ${Number(result.distance_km).toFixed(1)} km from your location.`);
    if(intel?.analysis){
      const {sstR,chlR}=intel;
      if(sstR!==null && Math.abs(sstR)>=0.25){
        parts.push(`Looking at past catches in ${state}, ${sstR>0?'higher':'lower'} SST has generally been associated with higher fish catches.`);
        if(n(result.live_sst_c)!==null) parts.push(`The current SST here is ${n(result.live_sst_c).toFixed(2)}°C, and it matches the more favourable part of that past SST pattern.`);
      }else{
        parts.push(`Past catches in ${state} do not show a strong and consistent SST relationship.`);
      }
      if(chlR!==null && Math.abs(chlR)>=0.25){
        parts.push(`For chlorophyll, ${chlR>0?'higher':'lower'} levels have generally been associated with higher fish catches.`);
        if(n(result.live_chlorophyll_mg_m3)!==null) parts.push(`The current chlorophyll level here is ${n(result.live_chlorophyll_mg_m3).toFixed(3)} mg/m³, which is also considered when ranking this zone.`);
      }else{
        parts.push(`Past catches in ${state} do not show a strong and consistent chlorophyll relationship.`);
      }
    }else{
      parts.push('Historical catch relationships were not available for this coastal region, so the recommendation relies on the available ocean conditions, advisory freshness and distance.');
    }
    const live=[];
    if(n(result.live_sst_c)!==null) live.push(`SST ${n(result.live_sst_c).toFixed(2)}°C`);
    if(n(result.live_chlorophyll_mg_m3)!==null) live.push(`chlorophyll ${n(result.live_chlorophyll_mg_m3).toFixed(3)} mg/m³`);
    if(live.length) parts.push(`Right now at this zone: ${live.join(', ')}. These live conditions are used in the recommendation.`);
    parts.push('This is a guidance tool based on past catch patterns and current ocean conditions; it does not guarantee fish catch.');
    return parts.join(' ');
  }

  function safe(text){return String(text||'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));}

  function renderExplanation(){
    const anchor=document.querySelector('#orca-productivity-enhanced .pfz-layout');
    if(!anchor || !latestExplanation) return false;
    let panel=document.getElementById(PANEL_ID);
    if(!panel){
      panel=document.createElement('section');
      panel.id=PANEL_ID;
      panel.className='mp-card';
      anchor.insertAdjacentElement('afterend',panel);
    }
    panel.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:9px"><h3 style="margin:0">Why this fishing zone is recommended</h3><span style="font-size:9px;color:#6ee7b7;border:1px solid #065f46;border-radius:999px;padding:3px 7px">PAST CATCH + CURRENT OCEAN CONDITIONS</span></div><p style="font-size:11px;line-height:1.7;color:#cbd5e1;margin:0">${safe(latestExplanation)}</p><div style="margin-top:10px;padding:9px 10px;border-radius:9px;background:#020617;border:1px solid #1e293b;color:#64748b;font-size:9px;line-height:1.55"><b style="color:#94a3b8">In simple terms:</b> the system checks what SST and chlorophyll conditions were linked with better catches in the past, then checks whether today's conditions at each PFZ look similar. Distance and advisory freshness are also considered.</div>`;
    return true;
  }

  window.fetch=async function(input,init){
    const response=await nativeFetch(input,init);
    const url=typeof input==='string'?input:input?.url||'';
    if(!url.includes('/api/marine-productivity/pfz') || !response.ok) return response;
    try{
      const payload=await response.clone().json();
      const enriched=await enrich(payload);
      for(let i=0;i<20;i++){
        setTimeout(()=>renderExplanation(),i*100);
      }
      const headers=new Headers(response.headers);
      headers.set('content-type','application/json');
      return new Response(JSON.stringify(enriched),{status:response.status,statusText:response.statusText,headers});
    }catch(_){return response;}
  };

  const observer=new MutationObserver(()=>renderExplanation());
  observer.observe(document.body,{childList:true,subtree:true});
})();