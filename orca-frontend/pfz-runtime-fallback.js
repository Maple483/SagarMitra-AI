/*
 * PFZ-only runtime resilience layer.
 * The normal FastAPI endpoint is always attempted first. If the hosted
 * frontend is running without the backend mounted at the same origin, a 404
 * (or network failure) is transparently replaced with data from the repository
 * PFZ advisory catalogue plus live marine conditions.
 * No other frontend request is intercepted.
 */
(function () {
  const originalFetch = window.fetch.bind(window);
  const PFZ_PATH = /\/api\/marine-productivity\/pfz(?:\?|$)/i;
  const PFZ_CSV_URL = 'https://raw.githubusercontent.com/Maple483/sih_orca/main/orca-backend/data/pfz_advisories.csv';
  const OPEN_METEO_URL = 'https://marine-api.open-meteo.com/v1/marine';
  const NOAA_MUR_URL = 'https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.json';

  const emergencyAdvisories = [
    ['Chapora','SW',259,'30-35','47-52','Goa','27 Aug 2026','28 Aug 2026',15.536667,73.446111],
    ['Aguada','NW',271,'22-27','36-41','Goa','27 Aug 2026','28 Aug 2026',15.495833,73.550833],
    ['Cutbona','SW',269,'41-46','64-69','Goa','27 Aug 2026','28 Aug 2026',15.079167,73.520833],
    ['Karwar','SW',267,'38-43','61-66','Karnataka','27 Aug 2026','28 Aug 2026',14.799167,73.691944],
    ['Malpe','SW',241,'49-54','45-50','Karnataka','27 Aug 2026','28 Aug 2026',13.123056,74.269167],
    ['Manjeshwara','SW',253,'21-26','36-41','Kerala','27 Aug 2026','28 Aug 2026',12.651389,74.684444],
    ['Kozhikode','SW',251,'51-56','55-60','Kerala','27 Aug 2026','28 Aug 2026',11.097778,75.301111],
    ['Chetlat I','SW',236,'24-29','1610-1615','Lakshadweep','27 Aug 2026','28 Aug 2026',11.560833,72.517222],
    ['Kavaratti I','SE',143,'15-20','1685-1690','Lakshadweep','27 Aug 2026','28 Aug 2026',10.433056,72.746389],
    ['Malabar Port','NW',278,'32-37','29-34','Maharashtra','27 Aug 2026','28 Aug 2026',18.980278,72.483889],
    ['Sindhudurg','SW',260,'39-44','66-71','Maharashtra','27 Aug 2026','28 Aug 2026',15.974444,73.085],
    ['Visakhapatnam','SW',224,'73-78','56-61','North Andhra Pradesh','27 Aug 2026','28 Aug 2026',17.179444,82.800278],
    ['Kakinada','SE',129,'24-29','62-67','North Andhra Pradesh','27 Aug 2026','28 Aug 2026',16.795833,82.458333],
    ['Chennai','SE',101,'21-26','82-87','North Tamil Nadu','27 Aug 2026','28 Aug 2026',13.080833,80.507222],
    ['Nagapattinam','NE',87,'46-51','291-296','North Tamil Nadu','27 Aug 2026','28 Aug 2026',10.790833,80.289444],
    ['Dhamra','SE',131,'29-34','9-14','Odisha','27 Aug 2026','28 Aug 2026',20.613333,87.111389],
    ['Gopalpur','SE',100,'41-46','101-106','Odisha','27 Aug 2026','28 Aug 2026',19.186667,85.296667],
    ['Machilipatnam','SE',91,'56-61','185-190','South Andhra Pradesh','27 Aug 2026','28 Aug 2026',16.133056,81.743333],
    ['Krishnapatnam','NE',78,'30-35','1098-1103','South Andhra Pradesh','27 Aug 2026','28 Aug 2026',14.3325,80.413333],
    ['Digha','SE',171,'42-47','3-8','West Bengal','27 Aug 2026','28 Aug 2026',21.259444,87.769722],
    ['Junput','SW',196,'69-74','25-30','West Bengal','27 Aug 2026','28 Aug 2026',21.093056,87.623889]
  ];

  function toAdvisory(row) {
    return {
      coast: String(row[0] || ''), direction: String(row[1] || ''), bearing: Number(row[2]),
      advisoryDistance: String(row[3] || ''), depth: String(row[4] || ''), state: String(row[5] || ''),
      validity: `FORECAST VALIDITY FROM ${row[6]} TO ${row[7]}`,
      lat: Number(row[8]), lon: Number(row[9])
    };
  }

  function splitCsvLine(line) {
    const out = []; let cur = ''; let quoted = false;
    for (let i = 0; i < line.length; i += 1) {
      const ch = line[i];
      if (ch === '"') {
        if (quoted && line[i + 1] === '"') { cur += '"'; i += 1; }
        else quoted = !quoted;
      } else if (ch === ',' && !quoted) { out.push(cur); cur = ''; }
      else cur += ch;
    }
    out.push(cur); return out;
  }

  function parseCsv(text) {
    const lines = String(text || '').replace(/^\uFEFF/, '').trim().split(/\r?\n/).filter(Boolean);
    if (lines.length < 2) return [];
    const header = splitCsvLine(lines[0]).map(x => x.trim());
    const idx = Object.fromEntries(header.map((x, i) => [x, i]));
    const coastIndex = idx['From the coast of'] ?? 0;
    return lines.slice(1).map(line => {
      const cells = splitCsvLine(line);
      return {
        coast: cells[coastIndex] || '', direction: cells[idx['Direction']] || '', bearing: Number(cells[idx['Bearing (deg)']]),
        advisoryDistance: cells[idx['Distance (km) From-To']] || '', depth: cells[idx['Depth (mtr) From-To']] || '',
        state: cells[idx['State']] || '', validity: cells[idx['Forecast_Validity']] || '',
        lat: Number(cells[idx['Latitude_Decimal']]), lon: Number(cells[idx['Longitude_Decimal']])
      };
    }).filter(x => Number.isFinite(x.lat) && Number.isFinite(x.lon));
  }

  async function withTimeout(promise, ms) {
    let timer;
    try {
      return await Promise.race([
        promise,
        new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('timeout')), ms); })
      ]);
    } finally { clearTimeout(timer); }
  }

  function haversine(lat1, lon1, lat2, lon2) {
    const R = 6371.0088;
    const p1 = lat1 * Math.PI / 180, p2 = lat2 * Math.PI / 180;
    const dLat = (lat2 - lat1) * Math.PI / 180, dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
  }

  function freshness(text) {
    const m = String(text || '').match(/FROM\s+(\d{1,2}\s+\w+\s+\d{4})\s+TO\s+(\d{1,2}\s+\w+\s+\d{4})/i);
    if (!m) return 0.5;
    const start = Date.parse(`${m[1]} UTC`), end = Date.parse(`${m[2]} 23:59:59 UTC`), now = Date.now();
    if (!Number.isFinite(start) || !Number.isFinite(end)) return 0.5;
    if (now >= start && now <= end) return 1;
    if (now > end) return Math.max(0, 1 - (now - end) / (14 * 86400000));
    return 0.8;
  }

  async function loadAdvisories() {
    try {
      const response = await withTimeout(originalFetch(PFZ_CSV_URL, { cache: 'no-store' }), 5000);
      if (response.ok) {
        const parsed = parseCsv(await response.text());
        if (parsed.length) return parsed;
      }
    } catch (_) {}
    return emergencyAdvisories.map(toAdvisory);
  }

  async function loadMarine(lat, lon) {
    let marine = {
      sst_c: null, satellite_sst_c: null, wave_height_m: null, wave_direction_deg: null,
      wave_period_s: null, current_velocity_kmh: null, current_direction_deg: null,
      source: 'Live marine feed unavailable'
    };
    try {
      const params = new URLSearchParams({
        latitude: String(lat), longitude: String(lon),
        current: 'sea_surface_temperature,wave_height,wave_direction,wave_period,ocean_current_velocity,ocean_current_direction',
        timezone: 'GMT', cell_selection: 'sea'
      });
      const response = await withTimeout(originalFetch(`${OPEN_METEO_URL}?${params.toString()}`), 6000);
      if (response.ok) {
        const c = (await response.json()).current || {};
        marine = {
          sst_c: c.sea_surface_temperature ?? null, satellite_sst_c: null,
          wave_height_m: c.wave_height ?? null, wave_direction_deg: c.wave_direction ?? null,
          wave_period_s: c.wave_period ?? null, current_velocity_kmh: c.ocean_current_velocity ?? null,
          current_direction_deg: c.ocean_current_direction ?? null, source: 'Open-Meteo Marine (live)'
        };
      }
    } catch (_) {}

    try {
      const date = new Date(Date.now() - 2 * 86400000).toISOString().slice(0, 10) + 'T00:00:00Z';
      const query = `analysed_sst[(${date})][(${lat})][(${lon})]`;
      const response = await withTimeout(originalFetch(`${NOAA_MUR_URL}?${query}`), 6000);
      if (response.ok) {
        const rows = (await response.json()).table?.rows || [];
        const value = rows.length ? Number(rows[0][rows[0].length - 1]) : NaN;
        if (Number.isFinite(value) && value > -100) {
          marine.satellite_sst_c = value;
          marine.satellite_sst_source = 'NASA/JPL MUR satellite SST via NOAA ERDDAP';
        }
      }
    } catch (_) {}
    return marine;
  }

  async function buildResponse(lat, lon, maxResults) {
    const [advisories, marine] = await Promise.all([loadAdvisories(), loadMarine(lat, lon)]);
    const sst = marine.satellite_sst_c ?? marine.sst_c;
    const now = new Date();
    const results = advisories.map(item => {
      const distance = haversine(lat, lon, item.lat, item.lon);
      let score = 55 * Math.max(0, 1 - Math.min(distance, 300) / 300) + 45 * freshness(item.validity);
      const reasons = [];
      if (marine.wave_height_m != null) {
        if (marine.wave_height_m <= 1.5) { score += 8; reasons.push('calmer waves'); }
        else if (marine.wave_height_m >= 3) { score -= 10; reasons.push('high waves'); }
      }
      if (sst != null && sst >= 22 && sst <= 30) { score += 4; reasons.push('favourable SST range'); }
      return {
        distance_km: Number(distance.toFixed(1)), rank_score: Number(Math.max(0, Math.min(100, score)).toFixed(1)),
        from_coast: item.coast, direction: item.direction, bearing_deg: Number.isFinite(item.bearing) ? item.bearing : null,
        distance_advisory_km: item.advisoryDistance, depth_m: item.depth, lat: item.lat, lon: item.lon,
        state: item.state, forecast_validity: item.validity, reasons
      };
    }).sort((a, b) => b.rank_score - a.rank_score || a.distance_km - b.distance_km).slice(0, maxResults);
    results.forEach((item, i) => { item.rank = i + 1; });
    return {
      status: 'OK', user_location: { lat, lon }, generated_at: now.toISOString(), live_conditions: marine, results,
      method: 'Repository PFZ advisories + live marine conditions. The backend is attempted first; this browser fallback prevents missing-route 404s in static deployments. Decision support only; not a guarantee of fish presence.'
    };
  }

  window.fetch = async function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (!PFZ_PATH.test(url)) return originalFetch(input, init);

    try {
      const response = await originalFetch(input, init);
      if (response.ok) return response;
    } catch (_) {}

    try {
      const u = new URL(url, window.location.origin);
      const lat = Number(u.searchParams.get('lat'));
      const lon = Number(u.searchParams.get('lon'));
      const maxResults = Math.min(10, Math.max(1, Number(u.searchParams.get('max_results')) || 5));
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) throw new Error('Invalid coordinates');
      const payload = await buildResponse(lat, lon, maxResults);
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json', 'X-ORCA-PFZ-Fallback': 'true' }
      });
    } catch (error) {
      console.error('[ORCA PFZ fallback]', error);
      return new Response(JSON.stringify({
        status: 'OK', user_location: { lat: Number(url.searchParams?.get?.('lat') || 0), lon: Number(url.searchParams?.get?.('lon') || 0) },
        live_conditions: {}, results: [], method: 'PFZ advisory fallback',
        message: 'PFZ advisory catalogue could not be loaded.'
      }), { status: 200, headers: { 'Content-Type': 'application/json', 'X-ORCA-PFZ-Fallback': 'true' } });
    }
  };
})();