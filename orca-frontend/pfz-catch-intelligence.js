(() => {
  const nativeFetch = window.fetch.bind(window);
  const PANEL_ID = 'pfz-catch-intelligence';
  const STYLE_ID = 'pfz-catch-intelligence-styles';

  const apiBase = url => {
    try { return new URL(url, window.location.href).origin; }
    catch (_) { return ''; }
  };

  const stateAliases = {
    'north andhra pradesh': 'Andhra Pradesh',
    'south andhra pradesh': 'Andhra Pradesh',
    'north tamil nadu': 'Tamil Nadu',
    'south tamil nadu': 'Tamil Nadu',
    'pondicherry': 'Puducherry',
    'pondy': 'Puducherry',
    'a & n islands': 'Andaman & Nicobar'
  };

  const normalizeState = state => {
    const raw = String(state || '').trim();
    const key = raw.toLowerCase();
    return stateAliases[key] || raw;
  };

  const finite = v => Number.isFinite(Number(v)) ? Number(v) : null;
  const avg = values => {
    const x = values.map(finite).filter(v => v !== null);
    return x.length ? x.reduce((a,b) => a+b, 0) / x.length : null;
  };
  const std = values => {
    const x = values.map(finite).filter(v => v !== null);
    if (x.length < 2) return null;
    const m = x.reduce((a,b) => a+b,0) / x.length;
    return Math.sqrt(x.reduce((a,b) => a + (b-m)*(b-m),0) / x.length) || null;
  };

  function correlation(xs, ys) {
    const pairs = [];
    for (let i=0;i<Math.min(xs.length,ys.length);i++) {
      const x=finite(xs[i]), y=finite(ys[i]);
      if (x!==null && y!==null) pairs.push([x,y]);
    }
    if (pairs.length < 3) return null;
    const mx = avg(pairs.map(p=>p[0])), my = avg(pairs.map(p=>p[1]));
    const sx = std(pairs.map(p=>p[0])), sy = std(pairs.map(p=>p[1]));
    if (!sx || !sy) return null;
    const cov = pairs.reduce((s,p)=>s+(p[0]-mx)*(p[1]-my),0)/pairs.length;
    return Math.max(-1,Math.min(1,cov/(sx*sy)));
  }

  function percentile(values, value) {
    const x = values.map(finite).filter(v => v !== null).sort((a,b)=>a-b);
    const v = finite(value);
    if (!x.length || v === null) return null;
    if (x.length === 1) return 0.5;
    let lo=0, hi=x.length;
    while (lo<hi) { const mid=Math.floor((lo+hi)/2); if (x[mid] < v) lo=mid+1; else hi=mid; }
    return Math.max(0,Math.min(1,lo/x.length));
  }

  function directionText(r, variable) {
    if (r === null || Math.abs(r) < 0.25) return `${variable} does not show a clear link with past catch`;
    return r > 0 ? `higher ${variable} has generally gone with higher past catch` : `lower ${variable} has generally gone with higher past catch`;
  }

  function matchText(r, variable, live, historical) {
    if (live === null || !historical.length || r === null || Math.abs(r) < 0.25) return '';
    const p = percentile(historical, live);
    if (p === null) return '';
    const favorable = r > 0 ? p >= 0.6 : p <= 0.4;
    const unfavorable = r > 0 ? p <= 0.4 : p >= 0.6;
    if (favorable) return `${variable} is in a range that has usually been more favourable in the past`;
    if (unfavorable) return `${variable} is outside the range that has usually been more favourable in the past`;
    return `${variable} is around the middle of its historical range`;
  }

  function scoreCandidate(result, analysis) {
    const annual = analysis?.annual || [];
    if (!annual.length) return {score:null, detail:null};
    const sstHist = annual.map(r=>r.sst);
    const chlHist = annual.map(r=>r.chlorophyll);
    const catches = annual.map(r=>r.catch);
    const sstR = correlation(catches, sstHist);
    const chlR = correlation(catches, chlHist);
    const sstP = percentile(sstHist, result.live_sst_c);
    const chlP = percentile(chlHist, result.live_chlorophyll_mg_m3);

    let weighted=0, weight=0;
    if (sstR !== null && sstP !== null && Math.abs(sstR) >= 0.25) {
      const directional = sstR > 0 ? sstP : 1-sstP;
      weighted += Math.min(1,Math.abs(sstR))*directional; weight += Math.min(1,Math.abs(sstR));
    }
    if (chlR !== null && chlP !== null && Math.abs(chlR) >= 0.25) {
      const directional = chlR > 0 ? chlP : 1-chlP;
      weighted += Math.min(1,Math.abs(chlR))*directional; weight += Math.min(1,Math.abs(chlR));
    }

    const catchEnvScore = weight ? 100*(weighted/weight) : 50;
    const base = finite(result.rank_score) ?? 50;
    const finalScore = 0.55*base + 0.45*catchEnvScore;
    return {
      score: Number(finalScore.toFixed(1)),
      detail: { sstCorrelation: sstR, chlorophyllCorrelation: chlR, catchEnvironmentScore: Number(catchEnvScore.toFixed(1)), sstPercentile: sstP, chlorophyllPercentile: chlP }
    };
  }

  function humanExplanation(result, analysis) {
    if (!result) return 'No PFZ recommendation is available for this location.';
    const annual = analysis?.annual || [];
    const catchVals = annual.map(r=>r.catch);
    const sstHist = annual.map(r=>r.sst);
    const chlHist = annual.map(r=>r.chlorophyll);
    const sstR = correlation(catchVals, sstHist);
    const chlR = correlation(catchVals, chlHist);
    const parts=[];

    parts.push(`We recommend this fishing zone because it gives the best overall match with the available PFZ advisories and ocean conditions.`);
    if (result.distance_km != null) parts.push(`It is about ${Number(result.distance_km).toFixed(1)} km from your location.`);

    if (sstR !== null && Math.abs(sstR) >= 0.25) {
      const live=finite(result.live_sst_c);
      const histText=directionText(sstR,'SST');
      const match=matchText(sstR,'Current SST',live,sstHist);
      parts.push(`Looking at past catches in this coastal region, ${histText}.` + (match ? ` ${match}.` : ''));
    } else {
      parts.push('Past catches in this coastal region do not show a strong or consistent SST link.');
    }

    if (chlR !== null && Math.abs(chlR) >= 0.25) {
      const live=finite(result.live_chlorophyll_mg_m3);
      const histText=directionText(chlR,'chlorophyll');
      const match=matchText(chlR,'Current chlorophyll',live,chlHist);
      parts.push(`For chlorophyll, ${histText}.` + (match ? ` ${match}.` : ''));
    } else {
      parts.push('Past catches in this coastal region do not show a strong or consistent chlorophyll link.');
    }

    const liveSst=finite(result.live_sst_c);
    const liveChl=finite(result.live_chlorophyll_mg_m3);
    if (liveSst !== null || liveChl !== null) {
      const liveBits=[];
      if (liveSst !== null) liveBits.push(`the current SST is ${liveSst.toFixed(2)}°C`);
      if (liveChl !== null) liveBits.push(`the current chlorophyll level is ${liveChl.toFixed(3)} mg/m³`);
      parts.push(`At this fishing zone now, ${liveBits.join(' and ')}. These current conditions are used when choosing between the recommended zones.`);
    } else {
      parts.push('Live SST and chlorophyll were not available for this zone right now, so the recommendation gives more weight to the available past data, advisory freshness and distance.');
    }

    parts.push('This is a guidance tool, not a guarantee of fish catch.');
    return parts.join(' ');
  }

  function addStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style=document.createElement('style');
    style.id=STYLE_ID;
    style.textContent=`
      #${PANEL_ID}{margin-top:14px}
      #${PANEL_ID} .pci-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:9px}
      #${PANEL_ID} .pci-head h3{margin:0;font-size:14px;color:#cbd5e1}
      #${PANEL_ID} .pci-tag{font-size:9px;color:#6ee7b7;border:1px solid #065f46;border-radius:999px;padding:3px 7px;white-space:nowrap}
      #${PANEL_ID} .pci-text{font-size:11px;line-height:1.7;color:#cbd5e1;margin:0}
      #${PANEL_ID} .pci-method{margin-top:9px;padding:9px 10px;border-radius:9px;background:#020617;border:1px solid #1e293b;color:#64748b;font-size:9px;line-height:1.55}
      #${PANEL_ID} .pci-method b{color:#94a3b8}
    `;
    document.head.appendChild(style);
  }

  function renderExplanation(text) {
    const anchor=document.querySelector('#orca-productivity-enhanced .pfz-layout');
    if (!anchor) return;
    let panel=document.getElementById(PANEL_ID);
    if (!panel) {
      panel=document.createElement('section');
      panel.id=PANEL_ID;
      panel.className='mp-card';
      anchor.insertAdjacentElement('afterend',panel);
    }
    panel.innerHTML=`<div class="pci-head"><h3>Why this fishing zone is recommended</h3><span class="pci-tag">CATCH + OCEAN CONDITIONS</span></div><p class="pci-text">${escapeHTML(text)}</p><div class="pci-method"><b>In simple terms:</b> we look at where you are, how fresh the PFZ advisory is, what the ocean is like there now, and what SST and chlorophyll looked like during years when catches were higher in that coastal region.</div>`;
  }

  function escapeHTML(text) {
    return String(text || '').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
  }

  async function enrichPFZPayload(payload, pfzUrl) {
    if (!payload?.results?.length) return payload;
    const base=apiBase(pfzUrl);
    const enriched=await Promise.all(payload.results.map(async result=>{
      try {
        const state=normalizeState(result.state);
        if (!state) return {...result};
        const res=await nativeFetch(`${base}/api/marine-productivity/analysis?state=${encodeURIComponent(state)}`,{headers:{Accept:'application/json'}});
        if (!res.ok) return {...result};
        const analysis=await res.json();
        const scored=scoreCandidate(result,analysis);
        return {...result, _catch_environment_score:scored.score, _catch_environment_detail:scored.detail};
      } catch (_) { return {...result}; }
    }));

    enriched.sort((a,b)=>((b._catch_environment_score ?? b.rank_score ?? 0)-(a._catch_environment_score ?? a.rank_score ?? 0)) || ((a.distance_km ?? Infinity)-(b.distance_km ?? Infinity)));
    enriched.forEach((item,i)=>{ item.rank=i+1; });

    const best=enriched[0];
    let bestAnalysis=null;
    try {
      const state=normalizeState(best?.state);
      if (state) {
        const res=await nativeFetch(`${base}/api/marine-productivity/analysis?state=${encodeURIComponent(state)}`,{headers:{Accept:'application/json'}});
        if (res.ok) bestAnalysis=await res.json();
      }
    } catch (_) {}

    payload.results=enriched;
    payload.method=(payload.method||'PFZ advisory ranking')+' Catch-environment evidence is then used to refine the ranking using historical catch vs SST/chlorophyll relationships for each candidate coastal region.';
    payload.catch_environment_note='For each candidate coastal region, historical catch is correlated separately with historical SST and chlorophyll. The candidate\'s live SST/chlorophyll are then checked against those historical relationships. This refines the existing PFZ ranking; it is not an ML prediction model.';
    payload.advisory_message=humanExplanation(best,bestAnalysis);
    return payload;
  }

  window.fetch=async function(input,init){
    const response=await nativeFetch(input,init);
    const url=typeof input==='string' ? input : input?.url || '';
    if (!url.includes('/api/marine-productivity/pfz') || !response.ok) return response;
    try {
      const payload=await response.clone().json();
      const enriched=await enrichPFZPayload(payload,url);
      setTimeout(()=>renderExplanation(enriched.advisory_message),40);
      const headers=new Headers(response.headers);
      headers.set('content-type','application/json');
      return new Response(JSON.stringify(enriched),{status:response.status,statusText:response.statusText,headers});
    } catch (_) {
      return response;
    }
  };

  addStyles();
  const observer=new MutationObserver(()=>{ if(!document.getElementById(PANEL_ID)) return; });
  observer.observe(document.body,{childList:true,subtree:true});
})();