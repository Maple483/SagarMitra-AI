(() => {
  const API = 'http://localhost:8000';
  const esc = s => String(s ?? '').replace(/[&<>\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
  const num = n => new Intl.NumberFormat('en-IN',{maximumFractionDigits:1}).format(Number(n)||0);
  const monthNames=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const card=(title,body)=>`<section class="pe-card"><h3>${title}</h3>${body}</section>`;
  const status=(direction)=> direction==='increasing'?'Increasing':direction==='decreasing'?'Decreasing':'Broadly stable';
  const arrow=(direction)=>direction==='increasing'?'↑':direction==='decreasing'?'↓':'→';
  const arrowColor=(direction)=>direction==='increasing'?'#34d399':direction==='decreasing'?'#f87171':'#94a3b8';

  function effectText(variable, trend, effect){
    const direction=status(trend).toLowerCase();
    if(effect==='Positive association') return `${variable} is ${direction}, and higher ${variable} values are linked with higher fish catch in this period.`;
    if(effect==='Negative association') return `${variable} is ${direction}, and higher ${variable} values are linked with lower fish catch in this period.`;
    return `${variable} is ${direction}, but its changes do not show a strong catch response in this period.`;
  }

  function lineChart(rows,key,label,unit,monthly=false){
    if(!rows?.length)return '<div class="pe-empty">No data available.</div>';
    const vals=rows.map(r=>Number(r[key])||0), max=Math.max(...vals), min=Math.min(...vals), range=max-min||1;
    const W=900,H=300,L=68,R=20,T=20,B=52, x=i=>L+i*(W-L-R)/Math.max(rows.length-1,1), y=v=>T+(max-v)*(H-T-B)/range;
    const pts=rows.map((r,i)=>`${x(i)},${y(Number(r[key])||0)}`).join(' ');
    const grid=Array.from({length:6},(_,i)=>{const v=min+range*i/5,yy=y(v);return `<line x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}"/><text x="${L-8}" y="${yy+4}" text-anchor="end">${num(v)}</text>`}).join('');
    const circles=rows.map((r,i)=>{const v=Number(r[key])||0;const title=monthly?`${label}: ${v.toFixed(3)} ${unit}\\n${monthNames[r.Month-1]} ${r.Year}`:`${label}: ${v.toFixed(2)} ${unit}\\nYear: ${r.Year}`;return `<circle cx="${x(i)}" cy="${y(v)}" r="${monthly?3:5}"><title>${esc(title)}</title></circle>`}).join('');
    const labels=monthly?rows.map((r,i)=>r.Month===1?`<text x="${x(i)}" y="${H-16}" text-anchor="middle" class="year">${r.Year}</text>`:``).join(''):rows.map((r,i)=>`<text x="${x(i)}" y="${H-16}" text-anchor="middle" class="year">${r.Year}</text>`).join('');
    return `<div class="pe-scroll"><svg viewBox="0 0 ${W} ${H}" class="pe-svg"><g class="grid">${grid}</g><line class="axis" x1="${L}" y1="${T}" x2="${L}" y2="${H-B}"/><line class="axis" x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}"/><polyline class="line" points="${pts}"/>${circles}${labels}</svg></div>`;
  }

  function barChart(rows,key,labelKey){
    if(!rows?.length)return '<div class="pe-empty">No data available.</div>';
    const max=Math.max(...rows.map(r=>Number(r[key])||0),1), W=760,H=300,L=64,R=20,T=18,B=62, base=H-B, bw=Math.min(80,(W-L-R)/rows.length-16);
    const grid=Array.from({length:6},(_,i)=>{const v=max*i/5,yy=base-(v/max)*(base-T);return `<line x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}"/><text x="${L-8}" y="${yy+4}" text-anchor="end">${num(v)}</text>`}).join('');
    const bars=rows.map((r,i)=>{const v=Number(r[key])||0,h=v/max*(base-T),bx=L+(i+.5)*(W-L-R)/rows.length-bw/2;return `<g><rect x="${bx}" y="${base-h}" width="${bw}" height="${h}" rx="4"><title>${esc(r[labelKey])}: ${num(v)} tonnes</title></rect><text x="${bx+bw/2}" y="${H-28}" text-anchor="middle" class="barlabel">${esc(String(r[labelKey]).length>14?String(r[labelKey]).slice(0,14)+'…':r[labelKey])}</text></g>`}).join('');
    return `<div class="pe-scroll"><svg viewBox="0 0 ${W} ${H}" class="pe-svg"><g class="grid">${grid}</g><line class="axis" x1="${L}" y1="${T}" x2="${L}" y2="${base}"/><line class="axis" x1="${L}" y1="${base}" x2="${W-R}" y2="${base}"/>${bars}</svg></div>`;
  }

  async function getJSON(url){const r=await fetch(url);if(!r.ok)throw new Error(`Backend returned ${r.status}`);return r.json();}

  async function openEnhanced(){
    if(document.getElementById('orca-productivity-enhanced'))return;
    const root=document.createElement('div');root.id='orca-productivity-enhanced';
    root.innerHTML=`<div class="pe-shell"><div class="pe-head"><div><div class="pe-title">Marine Productivity</div><div class="pe-sub">Fish catch (landings) × SST × chlorophyll · 2007–2012</div></div><button id="pe-close">← Back to Dashboard</button></div><div class="pe-controls"><label>Coastal region<select id="pe-region"><option>Loading…</option></select></label><label>Species<select id="pe-species"><option value="">All fish / total catch</option></select></label><button id="pe-run">Run analysis</button><span id="pe-loading"></span></div><div id="pe-content" class="pe-content"><div class="pe-empty">Select a region to load the analysis.</div></div></div>`;
    document.body.appendChild(root);
    const regionSel=root.querySelector('#pe-region'),speciesSel=root.querySelector('#pe-species'),content=root.querySelector('#pe-content'),loading=root.querySelector('#pe-loading');
    root.querySelector('#pe-close').onclick=()=>{root.remove();const b=[...document.querySelectorAll('button')].find(x=>x.textContent?.includes('Back to Dashboard'));if(b)b.click();};

    async function loadRegions(){try{const d=await getJSON(`${API}/api/marine-productivity/regions`);regionSel.innerHTML=(d.regions||[]).map(r=>`<option>${esc(r)}</option>`).join('');await loadSpecies();await load();}catch(e){content.innerHTML=`<div class="pe-error">${esc(e.message)}. Start the ORCA backend on port 8000.</div>`;}}
    async function loadSpecies(){try{const d=await getJSON(`${API}/api/marine-productivity/species?state=${encodeURIComponent(regionSel.value)}`);speciesSel.innerHTML='<option value="">All fish / total catch</option>'+(d.species||[]).map(s=>`<option>${esc(s)}</option>`).join('');}catch(e){speciesSel.innerHTML='<option value="">All fish / total catch</option>';}}
    async function load(){loading.textContent='Loading…';try{const qs=`state=${encodeURIComponent(regionSel.value)}${speciesSel.value?`&species=${encodeURIComponent(speciesSel.value)}`:''}`;const [a,e]=await Promise.all([getJSON(`${API}/api/marine-productivity/analysis?${qs}`),getJSON(`${API}/api/marine-productivity/environment?state=${encodeURIComponent(regionSel.value)}`)]);render(a,e);}catch(err){content.innerHTML=`<div class="pe-error">${esc(err.message)}</div>`;}finally{loading.textContent='';}}

    function render(a,e){
      const catchDirection=a.explanation.direction;
      const corrS=a.correlation.catch_vs_sst, corrC=a.correlation.catch_vs_chlorophyll;
      const sstEffect=a.explanation.sst_effect || (corrS!=null && corrS>=0.3?'Positive association':corrS!=null && corrS<=-0.3?'Negative association':'Weak / no clear association');
      const chlEffect=a.explanation.chlorophyll_effect || (corrC!=null && corrC>=0.3?'Positive association':corrC!=null && corrC<=-0.3?'Negative association':'Weak / no clear association');
      const catchTitle=a.species_filter?`Selected species catch: ${esc(a.species_filter)}`:'Top species catch';
      const catchEffectText=a.species_filter?`For ${esc(a.species_filter)}, fish catch (landings) is ${status(catchDirection).toLowerCase()} over 2007–2012.`:'Fish catch (landings) is '+status(catchDirection).toLowerCase()+' over 2007–2012.';
      content.innerHTML=`
        <div class="pe-summary">
          <div><b>${esc(a.state)}</b>${a.species_filter?`<span> · ${esc(a.species_filter)}</span>`:''}</div>
          <span class="pe-pill" style="color:${arrowColor(catchDirection)}!important;border-color:${arrowColor(catchDirection)}!important">${arrow(catchDirection)} ${status(catchDirection)}</span>
          <p>${catchEffectText}</p>
          <div class="pe-effects">
            <div><b>SST</b><br><span style="color:${arrowColor(a.explanation.sst_trend)}">${arrow(a.explanation.sst_trend)} ${status(a.explanation.sst_trend)}</span><br>${esc(effectText('SST',a.explanation.sst_trend,sstEffect))}</div>
            <div><b>Chlorophyll-a</b><br><span style="color:${arrowColor(a.explanation.chlorophyll_trend)}">${arrow(a.explanation.chlorophyll_trend)} ${status(a.explanation.chlorophyll_trend)}</span><br>${esc(effectText('chlorophyll-a',a.explanation.chlorophyll_trend,chlEffect))}</div>
          </div>
        </div>
        ${card(`${esc(a.species_filter||'Total')} annual fish catch (landings) — exact value on hover`,lineChart(a.annual,'catch','Fish catch','tonnes'))}
        ${card(catchTitle,barChart(a.top_species,'catch_tonnes','Species'))}
        ${card('Monthly SST — every month, 2007–2012',lineChart(e.monthly,'SST_C','SST','°C',true))}
        ${card('Monthly chlorophyll-a — every month, 2007–2012',lineChart(e.monthly,'Chlorophyll_mg_m3','Chlorophyll-a','mg/m³',true))}
        <div class="pe-two">${card('Catch ↔ SST',`<div class="pe-big">${corrS==null?'—':corrS.toFixed(2)}</div><div>${esc(effectText('SST',a.explanation.sst_trend,sstEffect))}</div>`)}${card('Catch ↔ Chlorophyll-a',`<div class="pe-big">${corrC==null?'—':corrC.toFixed(2)}</div><div>${esc(effectText('chlorophyll-a',a.explanation.chlorophyll_trend,chlEffect))}</div>`)}</div>
      `;
    }
    regionSel.onchange=async()=>{await loadSpecies();await load();};speciesSel.onchange=load;root.querySelector('#pe-run').onclick=load;await loadRegions();
  }
  document.addEventListener('click',e=>{const b=e.target.closest?.('button');if(b&&b.getAttribute('title')==='Marine Productivity'){setTimeout(openEnhanced,80);}},true);
})();