(() => {
  const API = 'http://localhost:8000';
  const WMS_URL = 'https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi';
  const INDIA_BOUNDS = [[4,64],[26,96]];
  const INDIA_CENTER = [15,80];
  const esc = s => String(s ?? '').replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
  const num = n => new Intl.NumberFormat('en-IN',{maximumFractionDigits:1}).format(Number(n)||0);
  const status = direction => direction === 'increasing' ? 'Increasing' : direction === 'decreasing' ? 'Decreasing' : 'Broadly stable';
  const arrow = direction => direction === 'increasing' ? '↑' : direction === 'decreasing' ? '↓' : '→';
  const arrowColor = direction => direction === 'increasing' ? '#34d399' : direction === 'decreasing' ? '#f87171' : '#94a3b8';
  const getJSON = async url => { const r = await fetch(url); if(!r.ok) throw new Error(`Backend returned ${r.status}`); return r.json(); };
  let pfzMap = null, sstMap = null, chlMap = null;

  function effectText(variable, trend, effect){
    const direction = status(trend).toLowerCase();
    if(effect === 'Positive association') return `${variable} is ${direction}, and higher ${variable} values are linked with higher fish catch in this period.`;
    if(effect === 'Negative association') return `${variable} is ${direction}, and higher ${variable} values are linked with lower fish catch in this period.`;
    return `${variable} is ${direction}, but its changes do not show a strong catch response in this period.`;
  }

  function addStyles(){
    if(document.getElementById('orca-mp-v2-styles')) return;
    const s = document.createElement('style'); s.id='orca-mp-v2-styles';
    s.textContent = `
      #orca-productivity-enhanced{position:fixed;inset:0;z-index:1500;background:#020617;color:#e2e8f0;font-family:ui-sans-serif,system-ui,sans-serif;overflow:auto}
      #orca-productivity-enhanced *{box-sizing:border-box}
      .mp-shell{min-height:100%;background:radial-gradient(circle at 80% 0%,rgba(16,185,129,.07),transparent 32%),#020617}
      .mp-head{position:sticky;top:0;z-index:30;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:15px 22px;border-bottom:1px solid #1e293b;background:rgba(2,6,23,.94);backdrop-filter:blur(14px)}
      .mp-brand{display:flex;align-items:center;gap:12px}.mp-title{font-weight:800;font-size:18px}.mp-sub{font-size:10px;color:#6ee7b7;margin-top:2px;text-transform:uppercase;letter-spacing:.12em}
      .mp-back{border:1px solid #334155;background:#0f172a;color:#cbd5e1;border-radius:9px;padding:8px 12px;cursor:pointer}.mp-back:hover{background:#1e293b;color:#fff}
      .mp-tabs{display:grid;grid-template-columns:1fr 1fr;max-width:920px;margin:20px auto 0;padding:5px;background:#0b1220;border:1px solid #1e293b;border-radius:14px;gap:5px}.mp-tab{border:0;background:transparent;color:#94a3b8;padding:13px 16px;border-radius:10px;font-weight:700;cursor:pointer;text-align:left}.mp-tab.active{background:#064e3b;color:#d1fae5;box-shadow:0 0 0 1px rgba(16,185,129,.25)}.mp-tab small{display:block;font-weight:400;color:#64748b;margin-top:3px}.mp-tab.active small{color:#86efac}
      .mp-main{max-width:1100px;margin:0 auto;padding:18px 20px 48px}.mp-card{background:#0b1220;border:1px solid #1e293b;border-radius:15px;padding:17px;box-shadow:0 12px 35px rgba(0,0,0,.16)}.mp-card h3{font-size:14px;margin:0 0 13px;color:#cbd5e1}.mp-grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.mp-grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.mp-controls{display:flex;flex-wrap:wrap;align-items:end;gap:10px;margin-bottom:14px}.mp-controls label{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#64748b;display:flex;flex-direction:column;gap:5px}.mp-controls select,.mp-controls input{min-width:170px;background:#020617;border:1px solid #334155;color:#fff;border-radius:8px;padding:9px}.mp-btn{border:0;background:#059669;color:#fff;border-radius:8px;padding:9px 13px;font-weight:700;cursor:pointer}.mp-btn:hover{background:#10b981}.mp-btn.secondary{background:#1e293b}.mp-error{padding:13px;border:1px solid rgba(248,113,113,.3);background:rgba(248,113,113,.08);border-radius:10px;color:#fca5a5;font-size:13px}.mp-empty{padding:55px 10px;text-align:center;color:#64748b;font-size:13px}.mp-summary{margin-bottom:14px}.mp-summary-top{display:flex;justify-content:space-between;gap:10px;align-items:start}.mp-pill{padding:5px 9px;border-radius:999px;background:#0f172a;border:1px solid #334155;font-size:11px;color:#94a3b8}.mp-note{font-size:11px;color:#fbbf24;margin-top:10px}.mp-big{font-size:25px;font-weight:800;color:#f1f5f9;margin-top:4px}.mp-svg{width:100%;height:auto;min-width:520px}.mp-scroll{overflow:auto}.mp-svg .grid line{stroke:#1e293b}.mp-svg .grid text{fill:#64748b;font-size:10px}.mp-svg .axis{stroke:#475569}.mp-svg .line{fill:none;stroke-width:3;stroke-linejoin:round;stroke-linecap:round}.mp-svg circle{stroke:none}.mp-svg .year{fill:#64748b;font-size:9px}.mp-legend{font-size:10px;color:#64748b;margin-top:5px}.mp-table{width:100%;border-collapse:collapse;font-size:11px}.mp-table th,.mp-table td{padding:8px;border-bottom:1px solid #1e293b;text-align:left}.mp-table th{color:#64748b;text-transform:uppercase;font-size:9px}
      .pfz-controls{display:grid;grid-template-columns:1fr 1fr 1fr auto;gap:10px;align-items:end}.pfz-controls label{display:flex;flex-direction:column;gap:5px;font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.07em}.pfz-controls input{background:#020617;border:1px solid #334155;border-radius:8px;color:#fff;padding:9px;width:100%}.pfz-loc{display:flex;gap:8px}.pfz-loc .mp-btn{white-space:nowrap}.pfz-map{height:480px;border-radius:12px;overflow:hidden;border:1px solid #334155;background:#020617}.pfz-layout{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(300px,.8fr);gap:14px}.pfz-results{max-height:480px;overflow:auto;display:flex;flex-direction:column;gap:9px}.pfz-result{border:1px solid #1e293b;background:#070d18;border-radius:11px;padding:11px;cursor:pointer}.pfz-result:hover{border-color:#059669;background:#0a1717}.pfz-result.best{border-color:rgba(16,185,129,.55);box-shadow:inset 3px 0 #10b981}.pfz-rank{font-size:10px;color:#34d399;font-weight:800}.pfz-name{font-size:13px;font-weight:800;color:#e2e8f0;margin-top:2px}.pfz-meta{font-size:10px;color:#64748b;margin-top:5px;line-height:1.55}.pfz-score{float:right;font-size:15px;font-weight:800;color:#a7f3d0}.cond{padding:10px;border:1px solid #1e293b;border-radius:10px;background:#070d18}.cond-label{font-size:9px;color:#64748b;text-transform:uppercase}.cond-value{font-size:16px;font-weight:800;margin-top:3px}.map-title{display:flex;justify-content:space-between;gap:8px;align-items:center}.live{font-size:9px;color:#34d399;border:1px solid #065f46;border-radius:999px;padding:3px 7px}.sat-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.sat-map{height:390px;border-radius:10px;overflow:hidden;border:1px solid #334155;background:#020617}.sat-meta{font-size:10px;color:#64748b;margin-top:7px}.leaflet-container{font:11px ui-sans-serif,system-ui,sans-serif}.pfz-user-icon,.pfz-advisory-icon{background:transparent!important;border:0!important}
      @media(max-width:800px){.mp-grid2,.sat-grid,.pfz-layout{grid-template-columns:1fr}.pfz-controls{grid-template-columns:1fr 1fr}.mp-tabs{margin-left:12px;margin-right:12px}.mp-main{padding:14px 12px 35px}.mp-head{padding:12px}.pfz-map{height:420px}}
    `; document.head.appendChild(s);
  }

  function lineChart(rows,key,label,unit,monthly=false,color='#10b981'){
    if(!rows?.length)return '<div class="mp-empty">No data available.</div>';
    const vals=rows.map(r=>Number(r[key])||0), max=Math.max(...vals), min=Math.min(...vals), range=max-min||1;
    const W=900,H=300,L=68,R=20,T=20,B=52,x=i=>L+i*(W-L-R)/Math.max(rows.length-1,1),y=v=>T+(max-v)*(H-T-B)/range;
    const pts=rows.map((r,i)=>`${x(i)},${y(Number(r[key])||0)}`).join(' ');
    const grid=Array.from({length:6},(_,i)=>{const v=min+range*i/5,yy=y(v);return `<line x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}"/><text x="${L-8}" y="${yy+4}" text-anchor="end">${num(v)}</text>`}).join('');
    const circles=rows.map((r,i)=>{const v=Number(r[key])||0;const title=monthly?`${label}: ${v.toFixed(3)} ${unit}\\n${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][r.Month-1]} ${r.Year}`:`${label}: ${v.toFixed(2)} ${unit}\\nYear: ${r.Year}`;return `<circle cx="${x(i)}" cy="${y(v)}" r="${monthly?3:5}" fill="${color}"><title>${esc(title)}</title></circle>`}).join('');
    const labels=monthly?rows.map((r,i)=>r.Month===1?`<text x="${x(i)}" y="${H-16}" text-anchor="middle" class="year">${r.Year}</text>`:``).join(''):rows.map((r,i)=>`<text x="${x(i)}" y="${H-16}" text-anchor="middle" class="year">${r.Year}</text>`).join('');
    return `<div class="mp-scroll"><svg viewBox="0 0 ${W} ${H}" class="mp-svg"><g class="grid">${grid}</g><line class="axis" x1="${L}" y1="${T}" x2="${L}" y2="${H-B}"/><line class="axis" x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}"/><polyline class="line" points="${pts}" style="stroke:${color}"/>${circles}${labels}</svg></div>${monthly?'<div class="mp-legend">All monthly observations are plotted. Hover a point for the exact value.</div>':''}`;
  }

  function barChart(rows,key,labelKey,color='#10b981'){
    if(!rows?.length)return '<div class="mp-empty">No data available.</div>';
    const max=Math.max(...rows.map(r=>Number(r[key])||0),1),W=760,H=300,L=64,R=20,T=18,B=62,base=H-B,bw=Math.min(80,(W-L-R)/rows.length-16);
    const grid=Array.from({length:6},(_,i)=>{const v=max*i/5,yy=base-(v/max)*(base-T);return `<line x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}"/><text x="${L-8}" y="${yy+4}" text-anchor="end">${num(v)}</text>`}).join('');
    const bars=rows.map((r,i)=>{const v=Number(r[key])||0,h=v/max*(base-T),bx=L+(i+.5)*(W-L-R)/rows.length-bw/2;return `<g><rect x="${bx}" y="${base-h}" width="${bw}" height="${h}" rx="4" fill="${color}"><title>${esc(r[labelKey])}: ${num(v)} tonnes</title></rect><text x="${bx+bw/2}" y="${H-28}" text-anchor="middle" class="barlabel">${esc(String(r[labelKey]).length>14?String(r[labelKey]).slice(0,14)+'…':r[labelKey])}</text></g>`}).join('');
    return `<div class="mp-scroll"><svg viewBox="0 0 ${W} ${H}" class="mp-svg"><g class="grid">${grid}</g><line class="axis" x1="${L}" y1="${T}" x2="${L}" y2="${base}"/><line class="axis" x1="${L}" y1="${base}" x2="${W-R}" y2="${base}"/>${bars}</svg></div>`;
  }

  async function openEnhanced(){
    if(document.getElementById('orca-productivity-enhanced'))return;
    addStyles();
    const root=document.createElement('div');root.id='orca-productivity-enhanced';
    root.innerHTML=`<div class="mp-shell"><header class="mp-head"><div><div class="mp-title">Marine Productivity</div><div class="mp-sub">Historical analytics · Potential Fishing Zone decision support</div></div><button class="mp-back" id="mp-close">← Back to Dashboard</button></header><div class="mp-tabs"><button class="mp-tab active" data-tab="trends">Past Trends<small>Historical catch, SST, chlorophyll & species analytics</small></button><button class="mp-tab" data-tab="pfz">PFZ Finder<small>Recommended fishing zones + live marine conditions + satellite maps</small></button></div><main class="mp-main" id="mp-body"></main></div>`;
    document.body.appendChild(root);
    const body=root.querySelector('#mp-body');
    root.querySelector('#mp-close').onclick=()=>{destroyMaps();root.remove();const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.includes('Back to Dashboard'));if(b)b.click();};
    root.querySelectorAll('.mp-tab').forEach(b=>b.onclick=()=>switchTab(b.dataset.tab));
    let regions=[], region='', species='';

    async function switchTab(tab){
      root.querySelectorAll('.mp-tab').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));
      if(tab==='trends') renderTrends(); else renderPFZ();
    }

    async function loadRegions(){
      try{const d=await getJSON(`${API}/api/marine-productivity/regions`);regions=d.regions||[];region=regions[0]||'';}catch(e){body.innerHTML=`<div class="mp-error">${esc(e.message)}. Start the ORCA backend on port 8000.</div>`;return false;}return true;
    }
    async function loadSpecies(){if(!region)return[];try{const d=await getJSON(`${API}/api/marine-productivity/species?state=${encodeURIComponent(region)}`);return d.species||[]}catch(e){return[]}}

    async function renderTrends(){
      destroyMaps();
      body.innerHTML=`<div class="mp-card"><div class="mp-controls"><label>Coastal region<select id="mp-region"></select></label><label>Species<select id="mp-species"><option value="">All fish / total catch</option></select></label><button class="mp-btn" id="mp-run">Run analysis</button><span id="mp-load" style="font-size:11px;color:#64748b"></span></div></div><div id="trend-content"></div>`;
      const rs=body.querySelector('#mp-region'),ss=body.querySelector('#mp-species'),tc=body.querySelector('#trend-content'),load=body.querySelector('#mp-load');
      rs.innerHTML=regions.map(r=>`<option>${esc(r)}</option>`).join('');rs.value=region;
      const sp=await loadSpecies();ss.innerHTML='<option value="">All fish / total catch</option>'+sp.map(s=>`<option>${esc(s)}</option>`).join('');
      async function run(){
        region=rs.value;species=ss.value;load.textContent='Loading…';tc.innerHTML='';
        try{const qs=`state=${encodeURIComponent(region)}${species?`&species=${encodeURIComponent(species)}`:''}`;const [a,e]=await Promise.all([getJSON(`${API}/api/marine-productivity/analysis?${qs}`),getJSON(`${API}/api/marine-productivity/environment?state=${encodeURIComponent(region)}`)]);renderAnalysis(a,e,tc);}catch(err){tc.innerHTML=`<div class="mp-error">${esc(err.message)}</div>`}finally{load.textContent='';}
      }
      rs.onchange=async()=>{region=rs.value;const sp=await loadSpecies();ss.innerHTML='<option value="">All fish / total catch</option>'+sp.map(s=>`<option>${esc(s)}</option>`).join('');await run();};
      ss.onchange=run;body.querySelector('#mp-run').onclick=run;await run();
    }

    function renderAnalysis(a,e,tc){
      const corrS=a.correlation.catch_vs_sst,corrC=a.correlation.catch_vs_chlorophyll;
      const sstEffect=a.explanation.sst_effect||(corrS!=null&&corrS>=.3?'Positive association':corrS!=null&&corrS<=-.3?'Negative association':'Weak / no clear association');
      const chlEffect=a.explanation.chlorophyll_effect||(corrC!=null&&corrC>=.3?'Positive association':corrC!=null&&corrC<=-.3?'Negative association':'Weak / no clear association');
      const catchTitle=a.species_filter?`Selected species catch: ${esc(a.species_filter)}`:'Top species catch';
      const catchEffectText=a.species_filter?`For ${esc(a.species_filter)}, fish catch (landings) is ${status(a.explanation.direction).toLowerCase()} over 2007–2012.`:'Fish catch (landings) is '+status(a.explanation.direction).toLowerCase()+' over 2007–2012.';
      tc.innerHTML=`
        <div class="mp-card mp-summary">
          <div class="mp-summary-top"><div><b>${esc(a.state)}</b>${a.species_filter?`<span style="color:#64748b"> · ${esc(a.species_filter)}</span>`:''}</div><span class="mp-pill" style="color:${arrowColor(a.explanation.direction)};border-color:${arrowColor(a.explanation.direction)}">${arrow(a.explanation.direction)} ${status(a.explanation.direction)}</span></div>
          <p style="font-size:12px;color:#cbd5e1;line-height:1.6;margin:12px 0 0">${catchEffectText}</p>
          <div class="mp-grid2" style="margin-top:12px"><div style="font-size:11px;color:#94a3b8"><b style="color:#e2e8f0">SST</b><br><span style="color:${arrowColor(a.explanation.sst_trend)}">${arrow(a.explanation.sst_trend)} ${status(a.explanation.sst_trend)}</span><br>${esc(effectText('SST',a.explanation.sst_trend,sstEffect))}</div><div style="font-size:11px;color:#94a3b8"><b style="color:#e2e8f0">Chlorophyll-a</b><br><span style="color:${arrowColor(a.explanation.chlorophyll_trend)}">${arrow(a.explanation.chlorophyll_trend)} ${status(a.explanation.chlorophyll_trend)}</span><br>${esc(effectText('chlorophyll-a',a.explanation.chlorophyll_trend,chlEffect))}</div></div>
          <div class="mp-note">Historical SST/chlorophyll values for 2007–2012 are synthetic and are retained for historical visualization only.</div>
        </div>
        <section class="mp-card"><h3>${esc(a.species_filter||'Total')} Annual Fish Catch (landings) — exact value on hover</h3>${lineChart(a.annual,'catch','Fish catch','tonnes',false,'#10b981')}</section>
        <section class="mp-card"><h3>${catchTitle}</h3>${barChart(a.top_species,'catch_tonnes','Species','#facc15')}</section>
        <section class="mp-card"><h3>Monthly SST — every month, 2007–2012</h3>${lineChart(e.monthly,'SST_C','SST','°C',true,'#3b82f6')}</section>
        <section class="mp-card"><h3>Monthly chlorophyll-a — every month, 2007–2012</h3>${lineChart(e.monthly,'Chlorophyll_mg_m3','Chlorophyll-a','mg/m³',true,'#3b82f6')}</section>
        <div class="mp-grid2"><section class="mp-card"><h3>Catch ↔ SST</h3><div class="mp-big">${corrS==null?'—':corrS.toFixed(2)}</div><div style="font-size:11px;color:#94a3b8;margin-top:4px">${esc(effectText('SST',a.explanation.sst_trend,sstEffect))}</div></section><section class="mp-card"><h3>Catch ↔ Chlorophyll-a</h3><div class="mp-big">${corrC==null?'—':corrC.toFixed(2)}</div><div style="font-size:11px;color:#94a3b8;margin-top:4px">${esc(effectText('chlorophyll-a',a.explanation.chlorophyll_trend,chlEffect))}</div></section></div>
      `;
    }

    async function renderPFZ(){
      destroyMaps();
      body.innerHTML=`<section class="mp-card"><div class="pfz-controls"><label>Latitude<input id="pfz-lat" type="number" step="any" value="15.4900"></label><label>Longitude<input id="pfz-lon" type="number" step="any" value="73.5500"></label><label>Number of PFZs<input id="pfz-max" type="number" min="1" max="10" value="5"></label><div class="pfz-loc"><button class="mp-btn secondary" id="pfz-gps">Use my location</button><button class="mp-btn" id="pfz-find">Find PFZs</button></div></div><div style="font-size:10px;color:#64748b;margin-top:9px">Your position is shown in blue. Recommended PFZ advisories are shown in yellow; the best-ranked zone is highlighted in green.</div></section><div id="pfz-error"></div><div class="pfz-layout" style="margin-top:14px"><section class="mp-card"><div class="map-title"><h3>PFZ Recommendation Map</h3><span class="live">LIVE CONDITIONS</span></div><div id="pfz-map" class="pfz-map"></div></section><section class="mp-card"><h3>Recommended PFZs</h3><div id="pfz-results" class="pfz-results"><div class="mp-empty">Enter a location and find recommended PFZs.</div></div></section></div><section class="mp-card" style="margin-top:14px"><h3>Live Marine Conditions at Your Location</h3><div id="pfz-conditions" class="mp-grid3"></div></section><section class="sat-grid" style="margin-top:14px"><section class="mp-card"><h3 class="map-title"><span>Live Satellite SST — Indian Marine Waters</span><span class="live">LIVE / BEST AVAILABLE</span></h3><div id="pfz-sst" class="sat-map"></div><div class="sat-meta">NASA GIBS · GHRSST Level 4 MUR Sea Surface Temperature. Click/drag to explore.</div></section><section class="mp-card"><h3 class="map-title"><span>Live Satellite Chlorophyll-a — Indian Marine Waters</span><span class="live">LIVE / BEST AVAILABLE</span></h3><div id="pfz-chl" class="sat-map"></div><div class="sat-meta">NASA GIBS · VIIRS NOAA-20 Chlorophyll-a. Click/drag to explore.</div></section></div>`;
      initSatelliteMaps();
      body.querySelector('#pfz-gps').onclick=()=>navigator.geolocation?.getCurrentPosition(p=>{body.querySelector('#pfz-lat').value=p.coords.latitude.toFixed(5);body.querySelector('#pfz-lon').value=p.coords.longitude.toFixed(5);findPFZ();},()=>setError('Location permission was unavailable. You can enter coordinates manually.'));
      body.querySelector('#pfz-find').onclick=findPFZ;await findPFZ();
    }

    function setError(t){body.querySelector('#pfz-error').innerHTML=`<div class="mp-error" style="margin-top:14px">${esc(t)}</div>`}
    async function findPFZ(){
      const lat=Number(body.querySelector('#pfz-lat').value),lon=Number(body.querySelector('#pfz-lon').value),max=Number(body.querySelector('#pfz-max').value)||5;
      if(!Number.isFinite(lat)||!Number.isFinite(lon)){setError('Please enter valid latitude and longitude.');return;}
      body.querySelector('#pfz-error').innerHTML='';
      try{const d=await getJSON(`${API}/api/marine-productivity/pfz?lat=${lat}&lon=${lon}&max_results=${Math.min(10,Math.max(1,max))}`);renderPFZData(d,lat,lon);}catch(e){setError(e.message)}
    }

    function renderPFZData(d,lat,lon){
      if(pfzMap){try{pfzMap.remove()}catch(_){} }
      const results=d.results||[];
      pfzMap=window.L.map('pfz-map',{zoomControl:true,minZoom:4,maxZoom:9,maxBounds:INDIA_BOUNDS,maxBoundsViscosity:.8}).setView([lat,lon],6);
      window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors'}).addTo(pfzMap);
      const userIcon=window.L.divIcon({className:'pfz-user-icon',html:'<div style="width:18px;height:18px;border-radius:50%;background:#38bdf8;border:3px solid white;box-shadow:0 0 0 5px rgba(56,189,248,.25)"></div>',iconSize:[18,18],iconAnchor:[9,9]});
      window.L.marker([lat,lon],{icon:userIcon}).addTo(pfzMap).bindPopup(`<b>Your location</b><br>${lat.toFixed(4)}, ${lon.toFixed(4)}`);
      results.forEach((r,i)=>{const best=i===0;const size=best?24:18;const color=best?'#34d399':'#e39000';const icon=window.L.divIcon({className:'pfz-advisory-icon',html:`<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:3px solid white;box-shadow:0 0 12px ${best?'rgba(52,211,153,.7)':'rgba(250,204,21,.5)'};display:grid;place-items:center;color:#111;font-weight:900;font-size:9px">${r.rank||i+1}</div>`,iconSize:[size,size],iconAnchor:[size/2,size/2]});window.L.marker([r.lat,r.lon],{icon}).addTo(pfzMap).bindPopup(`<b>PFZ #${r.rank||i+1}: ${esc(r.from_coast)}</b><br>Score: ${r.rank_score}/100<br>Distance from you: ${r.distance_km} km<br>Direction: ${esc(r.direction||'—')} · Bearing: ${num(r.bearing_deg)}°<br>Advisory distance: ${esc(r.distance_advisory_km)} km<br>Depth: ${esc(r.depth_m)} m<br>${esc(r.forecast_validity)}<br>${esc((r.reasons||[]).join(', '))}`)});
      const all=[[lat,lon],...results.map(r=>[r.lat,r.lon])];if(results.length)pfzMap.fitBounds(all,{padding:[25,25],maxZoom:7});
      const rc=body.querySelector('#pfz-results');rc.innerHTML=results.length?results.map((r,i)=>`<div class="pfz-result ${i===0?'best':''}" data-i="${i}"><span class="pfz-score">${r.rank_score}/100</span><div class="pfz-rank">PFZ #${r.rank||i+1} · ${r.distance_km} km away</div><div class="pfz-name">${esc(r.from_coast||'Advisory zone')}</div><div class="pfz-meta">${esc(r.state||'')} · ${esc(r.direction||'')} · Bearing ${num(r.bearing_deg)}°<br>Advisory distance: ${esc(r.distance_advisory_km)} km · Depth: ${esc(r.depth_m)} m<br>${esc(r.forecast_validity||'')}<br>${esc((r.reasons||[]).join(' · '))}</div></div>`).join(''):'<div class="mp-empty">No PFZ advisories are currently available for this request.</div>';
      rc.querySelectorAll('.pfz-result').forEach(el=>el.onclick=()=>{const r=results[Number(el.dataset.i)];pfzMap.flyTo([r.lat,r.lon],8);});
      const m=d.live_conditions||{};const c=[['SST',m.satellite_sst_c??m.sst_c,m.satellite_sst_c!=null?'°C · satellite':'°C'],['Wave height',m.wave_height_m,'m'],['Wave direction',m.wave_direction_deg,'°'],['Wave period',m.wave_period_s,'s'],['Current speed',m.current_velocity_kmh,'km/h'],['Current direction',m.current_direction_deg,'°']];
      body.querySelector('#pfz-conditions').innerHTML=c.map(x=>`<div class="cond"><div class="cond-label">${x[0]}</div><div class="cond-value">${x[1]==null?'—':num(x[1])} <span style="font-size:10px;color:#64748b;font-weight:500">${x[2]}</span></div></div>`).join('');
    }

    function makeSatMap(id,layer){const m=window.L.map(id,{minZoom:4,maxZoom:8,maxBounds:INDIA_BOUNDS,maxBoundsViscosity:1}).setView(INDIA_CENTER,5);window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors'}).addTo(m);window.L.tileLayer.wms(WMS_URL,{layers:layer,styles:'',format:'image/png',transparent:true,version:'1.3.0',opacity:.88,attribution:'NASA GIBS'}).addTo(m);return m;}
    function initSatelliteMaps(){requestAnimationFrame(()=>{if(!window.L)return;sstMap=makeSatMap('pfz-sst','GHRSST_L4_MUR_Sea_Surface_Temperature');chlMap=makeSatMap('pfz-chl','VIIRS_NOAA20_Chlorophyll_a');setTimeout(()=>{sstMap.invalidateSize();chlMap.invalidateSize()},100)});}
    function destroyMaps(){[pfzMap,sstMap,chlMap].forEach(m=>{try{m&&m.remove()}catch(_){}});pfzMap=sstMap=chlMap=null;}

    if(await loadRegions()) await renderTrends();
  }

  document.addEventListener('click',e=>{const b=e.target.closest?.('button');if(b&&b.getAttribute('title')==='Marine Productivity')setTimeout(openEnhanced,80)},true);
})();
