// meteograma.js
(function () {
  // ===== Config de rutas (autodetecta si estás bajo /pronosticos_numericos/) =====
  const REPO = 'pronosticos_numericos';
  const BASE = location.pathname.startsWith('/' + REPO + '/') ? ('/' + REPO) : '';
  const DATA_BASE  = `${BASE}/data/meteogram`;
  const MODEL_DIR  = 'wrf';
  const CITIES_URL = `${DATA_BASE}/${MODEL_DIR}/cities.json`;

  // ===== DOM =====
  const $ = (id) => document.getElementById(id);
  const PANEL = $('meteoPanel');
  const DD_CITY = $('citySelect');
  const TITLE = $('mtTitle');
  const META  = $('mtMeta');
  const RANGE_BADGE = $('mtRange');
  const LINK = $('deepLink');

  const CANVAS = {
    temp: $('cTemp'),
    ppn:  $('cPpn'),
    wind: $('cWind'),
    rh:   $('cRh'),
  };

  // ===== Estado =====
  let CITIES = [];
  let LAST = null;

  // ===== Utils =====
  function fmtDateRange(timestamps) {
    if (!timestamps?.length) return '—';
    const a = new Date(timestamps[0]);
    const b = new Date(timestamps[timestamps.length - 1]);
    const pad = (n) => String(n).padStart(2, '0');
    const fa = `${a.getFullYear()}-${pad(a.getMonth()+1)}-${pad(a.getDate())} ${pad(a.getHours())}h`;
    const fb = `${b.getFullYear()}-${pad(b.getMonth()+1)}-${pad(b.getDate())} ${pad(b.getHours())}h`;
    return `${fa} → ${fb}`;
  }
  function findCityBySlug(slug) {
    return CITIES.find(c => c.slug === slug) || CITIES[0];
  }
  function qsEncode(obj) {
    const p = new URLSearchParams();
    Object.keys(obj || {}).forEach(k => p.append(k, obj[k]));
    return p.toString();
  }
  const isValidDateStr = (s) => !isNaN(new Date(s).getTime());

  // ===== Carga de datos =====
  async function fetchCityJson(slug) {
    const url = `${DATA_BASE}/${MODEL_DIR}/${slug}.json`;
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status + ' al cargar ' + url);
    return res.json();
  }
  async function loadCities() {
    try {
      const res = await fetch(CITIES_URL, { cache: 'no-store' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      CITIES = await res.json();
    } catch (e) {
      console.warn('[meteograma] No se pudo cargar cities.json -> usando fallback:', e);
      // Fallback mínimo (ajusta a tus ciudades reales)
      CITIES = [
        { name:'Ciudad de México', slug:'ciudad-de-mexico', lat:19.433, lon:-99.133 },
        { name:'Veracruz', slug:'veracruz', lat:19.1738, lon:-96.1342 },
        { name:'Guadalajara', slug:'guadalajara', lat:20.6736, lon:-103.344 }
      ];
    }
  }

  function normalizePayload(slug, raw) {
    const safe = (k, fb=[]) => Array.isArray(raw[k]) ? raw[k] : fb;
    const ts = Array.isArray(raw.timestamps) ? raw.timestamps.filter(isValidDateStr) : [];
    const fb = findCityBySlug(slug) || {name: slug, lat: 0, lon: 0};
    const out = {
      city: raw.city ?? fb.name,
      lat:  (typeof raw.lat === 'number') ? raw.lat : fb.lat,
      lon:  (typeof raw.lon === 'number') ? raw.lon : fb.lon,
      timestamps: ts,
      temp:   safe('temp'),
      precip: safe('precip'),
      wind:   safe('wind'),
      rh:     safe('rh'),
    };
    const n = Math.min(out.timestamps.length, out.temp.length, out.precip.length, out.wind.length, out.rh.length);
    out.timestamps = out.timestamps.slice(0, n);
    out.temp   = out.temp.slice(0, n);
    out.precip = out.precip.slice(0, n);
    out.wind   = out.wind.slice(0, n);
    out.rh     = out.rh.slice(0, n);
    return out;
  }

  // ===== Canvas helpers =====
  function clearCanvas(ctx, w, h) {
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, w, h);
  }
  function linMap(x, x0, x1, y0, y1) { return x1 === x0 ? y0 : y0 + (y1 - y0) * ((x - x0) / (x1 - x0)); }
  function findMinMax(arr) {
    let mn=+Infinity, mx=-Infinity;
    for (const v of arr || []) { if(v<mn) mn=v; if(v>mx) mx=v; }
    if (!isFinite(mn) || !isFinite(mx)) { mn=0; mx=1; }
    if (mn===mx) { mn-=1; mx+=1; }
    return [mn,mx];
  }
  function drawLineSeries(ctx, xs, ys, color, rect) {
    const n = Math.min(xs.length, ys.length); if (n<=0) return;
    ctx.beginPath();
    for (let i=0;i<n;i++) {
      const x = linMap(i, 0, n-1, rect.x, rect.x+rect.w);
      const y = linMap(ys[i], rect.yMin, rect.yMax, rect.y+rect.h, rect.y);
      if (i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
    }
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke();
  }
  function drawBars(ctx, xs, ys, color, rect) {
    const n = Math.min(xs.length, ys.length); if (n<=0) return;
    const gap=2, bw=Math.max(1,(rect.w/n)-gap); ctx.fillStyle=color;
    for (let i=0;i<n;i++){
      const x = linMap(i,0,n-1,rect.x,rect.x+rect.w) - bw/2;
      const yVal = linMap(ys[i], rect.yMin, rect.yMax, rect.y+rect.h, rect.y);
      const y0 = rect.y + rect.h; const top = Math.min(y0, Math.max(rect.y, yVal));
      ctx.fillRect(x, top, bw, y0 - top);
    }
  }
  function yTicks(min,max,count=4){ const t=[]; for(let i=0;i<=count;i++){ t.push(min+(i*(max-min)/count)); } return t; }
  function drawYTicks(ctx, rect, min, max, unit) {
    ctx.fillStyle='#667085';
    ctx.font='12px system-ui, -apple-system, Segoe UI, Roboto, Inter, Arial';
    ctx.textAlign='right'; ctx.textBaseline='middle';
    const ticks = yTicks(min,max,4);
    ticks.forEach(v=>{
      const y = linMap(v, min, max, rect.y+rect.h, rect.y);
      ctx.fillText(`${Math.round(v)}${unit||''}`, rect.x-6, y);
      ctx.strokeStyle='#f1f5f9'; ctx.lineWidth=1; ctx.beginPath();
      ctx.moveTo(rect.x,y); ctx.lineTo(rect.x+rect.w,y); ctx.stroke();
    });
  }
  function drawXLabels(ctx, rect, timestamps) {
    if (!timestamps?.length) return;
    if (isNaN(new Date(timestamps[0]).getTime())) return;
    const n = timestamps.length;
    const maxLabels = Math.max(3, Math.floor(rect.w / 90));
    const step = Math.max(1, Math.floor(n / maxLabels));
    ctx.fillStyle = '#667085';
    ctx.font = '12px system-ui, -apple-system, Segoe UI, Roboto, Inter, Arial';
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (let i = 0; i < n; i += step) {
      const d = new Date(timestamps[i]);
      const label = `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}h`;
      const x = linMap(i, 0, n - 1, rect.x, rect.x + rect.w);
      ctx.fillText(label, x, rect.y + rect.h + 4);
    }
  }

  // === renderChart con DPI y paddings compactos ===
  function renderChart(canvas, data, opts) {
    if (!canvas) return;
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const cssW = canvas.clientWidth || 300;
    const cssH = canvas.clientHeight || 150;
    canvas.width  = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);

    const ctx = canvas.getContext('2d');
    ctx.setTransform(1,0,0,1,0,0);
    ctx.scale(dpr, dpr);
    const w = cssW, h = cssH;

    clearCanvas(ctx, w, h);

    // ✔ NO usar padding negativo
    const padding = { l: 42, r: 8, t: 8, b: 30 };
    const rect = { x: padding.l, y: padding.t, w: w - padding.l - padding.r, h: h - padding.t - padding.b };

    // Marco
    ctx.strokeStyle = '#e5e7eb';
    ctx.lineWidth = 1;
    ctx.strokeRect(padding.l, padding.t, rect.w, rect.h);

    const ys = data.values || [];
    const [mn, mx] = (opts.lockMinMax && ys.length) ? opts.lockMinMax : findMinMax(ys);
    const view = { ...rect, yMin: mn, yMax: mx };

    drawYTicks(ctx, view, mn, mx, opts.unit);
    if (opts.type === 'bar') drawBars(ctx, data.timestamps || [], ys, opts.color || '#94a3b8', view);
    else drawLineSeries(ctx, data.timestamps || [], ys, opts.color || '#334155', view);
    drawXLabels(ctx, view, data.timestamps || []);
  }

  // ===== UI panel =====
  function openPanel() { PANEL.classList.add('open'); }
  function closePanel() { PANEL.classList.remove('open'); }
  $('closeBtn')?.addEventListener('click', closePanel);

  function fillCitiesSelect() {
    if (!DD_CITY) return;
    DD_CITY.innerHTML = '';
    CITIES.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.slug; opt.textContent = c.name;
      DD_CITY.appendChild(opt);
    });
  }

  // ===== Cargar y pintar =====
  async function loadAndRender(slug) {
    const raw = await fetchCityJson(slug);
    const dat = normalizePayload(slug, raw);
    LAST = dat;

    TITLE.textContent = `Meteograma — ${dat.city}`;
    META.textContent  = `Lat ${(+dat.lat).toFixed(3)}, Lon ${(+dat.lon).toFixed(3)}`;
    RANGE_BADGE.textContent = fmtDateRange(dat.timestamps);
    LINK.href = `?${qsEncode({ model: MODEL_DIR, city: slug })}#meteograma`;

    renderChart(CANVAS.temp, {timestamps: dat.timestamps, values: dat.temp},   { unit:'°C',   type:'line', color:'#2563eb' });
    renderChart(CANVAS.ppn,  {timestamps: dat.timestamps, values: dat.precip}, { unit:'mm',   type:'bar',  color:'#60a5fa', lockMinMax:[0, Math.max(5, Math.max(...dat.precip, 0)*1.1)] });
    renderChart(CANVAS.wind, {timestamps: dat.timestamps, values: dat.wind},   { unit:'km/h', type:'line', color:'#10b981' });
    renderChart(CANVAS.rh,   {timestamps: dat.timestamps, values: dat.rh},     { unit:'%',    type:'line', color:'#f59e0b', lockMinMax:[0,100] });
  }

  function rerenderFromLast(){
    if (!LAST) return;
    renderChart(CANVAS.temp, {timestamps: LAST.timestamps, values: LAST.temp},   { unit:'°C',   type:'line', color:'#2563eb' });
    renderChart(CANVAS.ppn,  {timestamps: LAST.timestamps, values: LAST.precip}, { unit:'mm',   type:'bar',  color:'#60a5fa', lockMinMax:[0, Math.max(5, Math.max(...LAST.precip, 0)*1.1)] });
    renderChart(CANVAS.wind, {timestamps: LAST.timestamps, values: LAST.wind},   { unit:'km/h', type:'line', color:'#10b981' });
    renderChart(CANVAS.rh,   {timestamps: LAST.timestamps, values: LAST.rh},     { unit:'%',    type:'line', color:'#f59e0b', lockMinMax:[0,100] });
  }

  // ===== API pública & wiring =====
  window.Meteo = {
    open: async function (slug) {
      if (!CITIES.length) await loadCities();
      if (!slug) slug = (CITIES[0]?.slug || 'ciudad-de-mexico');
      if (DD_CITY) DD_CITY.value = slug;
      openPanel();
      await loadAndRender(slug);
    }
  };

  if (DD_CITY) {
    DD_CITY.addEventListener('change', async function () {
      await loadAndRender(this.value);
    });
  }

  // ===== Init =====
  document.addEventListener('DOMContentLoaded', async function () {
    await loadCities();
    fillCitiesSelect();

    const sp = new URLSearchParams(location.search);
    const slug = sp.get('city') || (CITIES[0]?.slug ?? 'ciudad-de-mexico');

    document.getElementById('openMeteograma')?.addEventListener('click', function(){
      window.Meteo.open(slug);
    });

    if (location.hash === '#meteograma') {
      if (DD_CITY) DD_CITY.value = slug;
      window.Meteo.open(slug);
    }

    // Redibujar al cambiar tamaño/zoom
    const host = document.getElementById('meteoPanel');
    if (host) {
      const ro = new ResizeObserver(() => rerenderFromLast());
      ro.observe(host);
    }
    window.addEventListener('resize', rerenderFromLast);
    window.addEventListener('orientationchange', rerenderFromLast);
  });
})();


