/* Buoy map: points, drift tracks and an interpolated (IDW) heat surface. */
"use strict";

const $ = (id) => document.getElementById(id);
const VIRIDIS = ["#440154", "#472d7b", "#3b528b", "#2c728e", "#21918c", "#28ae80", "#5ec962", "#addc30", "#fde725"];
const RANGES = { "24h": 1, "3d": 3, "7d": 7, "30d": 30 };
const REFRESH_MS = 60_000;

const S = {
  config: { title: "Buoy Network", interval_min: 30 },
  params: [], byKey: {},
  param: null, depth: null,
  range: "7d", mode: "all", scale: "fixed",
  reach: 1200,
  points: [], tracks: {}, nodes: [],
  vmin: 0, vmax: 1,
  fitted: false,
};

// ---------------------------------------------------------------- map setup
const map = L.map("map", { preferCanvas: true, zoomControl: true }).setView([44.47, -73.27], 12);
const base = {
  "Map": L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "© OpenStreetMap contributors" }),
  "Satellite": L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19, attribution: "Imagery © Esri" }),
};
base["Map"].addTo(map);
L.control.layers(base, null, { position: "topright" }).addTo(map);
L.control.scale({ imperial: true }).addTo(map);

const trackLayer = L.layerGroup().addTo(map);
const pointLayer = L.layerGroup().addTo(map);
let surfaceOverlay = null;

// ---------------------------------------------------------------- helpers
function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
const RAMP = VIRIDIS.map(hexToRgb);
function rampRgb(t) {
  t = Math.max(0, Math.min(1, t)) * (RAMP.length - 1);
  const i = Math.min(RAMP.length - 2, Math.floor(t)), f = t - i, a = RAMP[i], b = RAMP[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}
function colorFor(v) {
  const c = rampRgb((v - S.vmin) / (S.vmax - S.vmin || 1));
  return `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`;
}
function fmt(v, p) {
  if (v == null || isNaN(v)) return "–";
  const span = Math.abs((p && (p.vmax - p.vmin)) || Math.abs(v) || 1);
  const dp = span >= 200 ? 0 : span >= 20 ? 1 : 2;
  return v.toFixed(dp);
}
function unit(p) { return p && p.unit ? ` ${p.unit}` : ""; }
function when(ts) {
  return new Date(ts * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
function ago(ts) {
  const s = Date.now() / 1000 - ts;
  if (s < 90) return "just now";
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 172800) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function nodeName(id) { const n = S.nodes.find((x) => x.node_id === id); return (n && n.name) || id; }
function curParam() { return S.byKey[S.param]; }
function paramTitle() {
  const p = curParam(); if (!p) return "";
  return p.label + (S.depth != null ? ` @ ${S.depth} m` : "");
}

function timeWindow() {
  const now = Math.floor(Date.now() / 1000);
  if (S.range === "all") return {};
  if (S.range === "custom") {
    const f = $("from").value, t = $("to").value;
    return { start: f ? Math.floor(new Date(f) / 1000) : undefined, end: t ? Math.floor(new Date(t) / 1000) : undefined };
  }
  return { start: now - RANGES[S.range] * 86400 };
}
function qs(o) {
  return new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null)).toString();
}
async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}

// ---------------------------------------------------------------- controls
function buildParamSelect() {
  const sel = $("param");
  sel.innerHTML = "";
  const groups = {};
  for (const p of S.params) {
    if (!p.has_data || p.group === "Node" && p.key !== "battery_v") continue;
    (groups[p.group] ||= []).push(p);
  }
  for (const [g, list] of Object.entries(groups)) {
    const og = document.createElement("optgroup"); og.label = g;
    for (const p of list) og.append(new Option(p.label + (p.unit ? ` (${p.unit})` : ""), p.key));
    sel.append(og);
  }
  if (!S.param || !S.byKey[S.param]?.has_data) S.param = S.byKey.ph?.has_data ? "ph" : sel.value;
  sel.value = S.param;
  buildDepthSelect();
}
function buildDepthSelect() {
  const p = curParam(), sel = $("depth");
  const depths = p ? p.depths : [];
  $("depthRow").hidden = depths.length === 0;
  sel.innerHTML = "";
  if (p && p.surface) sel.append(new Option("Surface", ""));
  for (const d of depths) sel.append(new Option(`${d} m`, d));
  if (depths.length && (S.depth == null || !depths.includes(S.depth))) S.depth = p.surface ? null : depths[0];
  if (!depths.length) S.depth = null;
  sel.value = S.depth == null ? "" : S.depth;
}
function segment(id, key, cb) {
  $(id).addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    for (const x of $(id).children) x.classList.toggle("on", x === b);
    S[key] = b.dataset[Object.keys(b.dataset)[0]];
    cb();
  });
}

$("param").addEventListener("change", (e) => { map.closePopup(); S.param = e.target.value; S.depth = null; buildDepthSelect(); load(); });
$("depth").addEventListener("change", (e) => { map.closePopup(); S.depth = e.target.value === "" ? null : +e.target.value; load(); });
segment("range", "range", () => { $("customRow").hidden = S.range !== "custom"; load(); });
segment("mode", "mode", () => load());
segment("scale", "scale", () => render());
$("from").addEventListener("change", load);
$("to").addEventListener("change", load);
for (const id of ["lySurface", "lyPoints", "lyTracks", "lyLabels"]) $(id).addEventListener("change", render);
$("reach").addEventListener("input", (e) => {
  S.reach = +e.target.value;
  $("reachVal").textContent = S.reach >= 1000 ? `${(S.reach / 1000).toFixed(1)} km` : `${S.reach} m`;
  drawSurface();
});
$("panelToggle").addEventListener("click", () => { document.body.classList.toggle("collapsed"); setTimeout(() => map.invalidateSize(), 50); });

// ---------------------------------------------------------------- data
async function load() {
  if (!S.param) return;
  $("status").textContent = "Loading…";
  const w = timeWindow();
  try {
    const [points, tracks, nodes] = await Promise.all([
      getJSON(`/api/points?${qs({ param: S.param, depth: S.depth, latest: S.mode === "latest", ...w })}`),
      getJSON(`/api/tracks?${qs(w)}`),
      getJSON("/api/nodes"),
    ]);
    S.points = points; S.tracks = tracks; S.nodes = nodes;
    $("export").href = `/api/export.csv?${qs(w)}`;
    $("status").textContent = `Updated ${new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
    render();
    if (!S.fitted) fitAll();
  } catch (err) {
    console.error(err);
    $("status").textContent = "Can't reach the server — retrying…";
  }
}
function fitAll() {
  const ll = S.points.map((p) => [p[2], p[3]]);
  for (const t of Object.values(S.tracks)) for (const p of t) ll.push([p[1], p[2]]);
  if (ll.length) { map.fitBounds(L.latLngBounds(ll).pad(0.15)); S.fitted = true; }
}

// ---------------------------------------------------------------- rendering
function computeScale() {
  const p = curParam();
  if (S.scale === "fixed" && p) { S.vmin = p.vmin; S.vmax = p.vmax; return; }
  const v = S.points.map((x) => x[4]).sort((a, b) => a - b);
  if (!v.length) { S.vmin = p?.vmin ?? 0; S.vmax = p?.vmax ?? 1; return; }
  S.vmin = v[Math.floor(v.length * 0.02)]; S.vmax = v[Math.min(v.length - 1, Math.floor(v.length * 0.98))];
  if (S.vmax - S.vmin < 1e-6) { S.vmin -= 0.5; S.vmax += 0.5; }
}

function latestByNode() {
  const m = {};
  for (const p of S.points) if (!m[p[0]] || p[1] > m[p[0]][1]) m[p[0]] = p;
  return m;
}

// Wind direction is an angle (359° and 1° are neighbours), so it can't be averaged
// into a color surface. It is shown as arrows on each buoy instead.
function isDirection() { return S.param === "wind_dir"; }
function windArrow(deg) {
  // wind_dir is where the wind comes FROM; the arrow points where it blows TO
  return L.divIcon({ className: "wind-arrow", iconSize: [30, 30], iconAnchor: [15, 15],
    html: `<svg viewBox="0 0 30 30" width="30" height="30" style="transform:rotate(${(deg + 180) % 360}deg)">
      <circle cx="15" cy="15" r="13" fill="#fff" stroke="#17212b" stroke-width="2"/>
      <path d="M15 4 L21 17 L15 14 L9 17 Z" fill="#0f6e8c"/><rect x="13.6" y="14" width="2.8" height="11" fill="#0f6e8c"/></svg>` });
}

function render() {
  computeScale();
  const p = curParam(), dir = isDirection();
  // legend
  $("ramp").hidden = dir; document.querySelector(".ramp-labels").hidden = dir; $("scale").hidden = dir;
  $("legendTitle").textContent = paramTitle() + (p && p.unit ? ` (${p.unit})` : "");
  $("ramp").style.background = `linear-gradient(90deg, ${VIRIDIS.join(",")})`;
  $("lmin").textContent = fmt(S.vmin, p); $("lmax").textContent = fmt(S.vmax, p);
  $("lmid").textContent = fmt((S.vmin + S.vmax) / 2, p);
  const nb = new Set(S.points.map((x) => x[0])).size;
  $("summary").textContent = S.points.length
    ? `${S.points.length.toLocaleString()} readings from ${nb} buoy${nb === 1 ? "" : "s"}`
    : "No readings in this period.";
  if (dir && S.points.length) $("summary").textContent += ". Arrows point the way the wind is blowing.";

  // tracks
  trackLayer.clearLayers();
  if ($("lyTracks").checked) {
    for (const t of Object.values(S.tracks)) {
      if (t.length < 2) continue;
      L.polyline(t.map((x) => [x[1], x[2]]), { color: "#1d2833", weight: 1.6, opacity: 0.5, interactive: false }).addTo(trackLayer);
    }
  }

  // points
  pointLayer.clearLayers();
  const latest = latestByNode();
  if ($("lyPoints").checked && S.mode === "all") {
    for (const pt of S.points) {
      if (latest[pt[0]] === pt) continue;
      L.circleMarker([pt[2], pt[3]], { radius: 4, weight: 0.6, color: "#fff", fillColor: dir ? "#8a96a3" : colorFor(pt[4]), fillOpacity: 0.9 })
        .on("click", () => openPopup(pt)).addTo(pointLayer);
    }
  }
  for (const pt of Object.values(latest)) {
    const m = (dir
      ? L.marker([pt[2], pt[3]], { icon: windArrow(pt[4]) })
      : L.circleMarker([pt[2], pt[3]], { radius: 9, weight: 2.5, color: "#17212b", fillColor: colorFor(pt[4]), fillOpacity: 1 }))
      .on("click", () => openPopup(pt)).addTo(pointLayer);
    if ($("lyLabels").checked) {
      m.bindTooltip(esc(nodeName(pt[0])), { permanent: true, direction: "right", offset: [dir ? 16 : 10, 0], className: "buoy-label" });
    }
  }

  renderNodes(latest);
  drawSurface();
}

function renderNodes(latest) {
  const p = curParam(), ul = $("nodes"), iv = S.config.interval_min * 60;
  ul.innerHTML = "";
  for (const n of S.nodes) {
    const age = n.last_ts ? Date.now() / 1000 - n.last_ts : Infinity;
    const cls = age < iv * 2.5 ? "ok" : age < 6 * 3600 ? "warn" : "bad";
    const pt = latest[n.node_id];
    const expected = Math.round(86400 / iv);
    const li = document.createElement("li");
    li.innerHTML = `<span class="dot ${cls}" title="${cls === "ok" ? "Reporting" : cls === "warn" ? "Late" : "Not reporting"}"></span>
      <span class="nname">${esc(n.name || n.node_id)}</span>
      <span class="nval">${pt ? fmt(pt[4], p) : "–"}</span>
      <span class="nmeta">${n.last_ts ? ago(n.last_ts) : "never"}${n.battery_v != null ? ` · ${n.battery_v.toFixed(2)} V` : ""} · ${n.pkts_24h}/${expected} packets today</span>`;
    li.addEventListener("click", () => {
      if (pt) { map.flyTo([pt[2], pt[3]], Math.max(map.getZoom(), 14), { duration: 0.6 }); openPopup(pt); }
      else if (n.lat != null) map.flyTo([n.lat, n.lon], 14);
    });
    ul.append(li);
  }
}

// ---------------------------------------------------------------- popup
function sparkline(series) {
  if (series.length < 2) return "";
  const W = 250, H = 54, xs = series.map((d) => d[0]), ys = series.map((d) => d[1]);
  const x0 = xs[0], x1 = xs[xs.length - 1];
  let y0 = Math.min(...ys), y1 = Math.max(...ys); if (y1 - y0 < 1e-9) { y0 -= 1; y1 += 1; }
  const X = (x) => ((x - x0) / (x1 - x0 || 1)) * (W - 4) + 2, Y = (y) => H - 3 - ((y - y0) / (y1 - y0)) * (H - 6);
  const d = series.map((s, i) => `${i ? "L" : "M"}${X(s[0]).toFixed(1)},${Y(s[1]).toFixed(1)}`).join("");
  return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><path d="${d}" fill="none" stroke="#0f6e8c" stroke-width="1.6"/></svg>
    <div class="spark-cap"><span>min ${fmt(y0, curParam())}</span><span>${paramTitle()} over period</span><span>max ${fmt(y1, curParam())}</span></div>`;
}

async function openPopup(pt) {
  const [nid, ts, lat, lon, val] = pt, p = curParam();
  const pop = L.popup({ maxWidth: 300, maxHeight: 380, autoPanPadding: [20, 20] }).setLatLng([lat, lon])
    .setContent(`<div class="pop"><h3>${esc(nodeName(nid))}</h3><div class="when">${when(ts)}</div>
      <div class="big">${fmt(val, p)}<small>${unit(p)} ${esc(paramTitle())}</small></div><div class="muted">Loading…</div></div>`)
    .openOn(map);
  try {
    const [pk, series] = await Promise.all([
      getJSON(`/api/packet?${qs({ node_id: nid, ts })}`),
      getJSON(`/api/series?${qs({ node_id: nid, param: S.param, depth: S.depth, ...timeWindow() })}`),
    ]);
    let rows = "", lastGroup = "";
    const order = Object.fromEntries(S.params.map((q, i) => [q.key, i]));
    pk.values.sort((a, b) => (order[a[0]] ?? 999) - (order[b[0]] ?? 999) || (a[1] ?? -1) - (b[1] ?? -1));
    for (const [key, depth, v] of pk.values) {
      const q = S.byKey[key]; if (!q) continue;
      if (q.group !== lastGroup) { rows += `<tr class="grp"><td colspan="2">${esc(q.group)}</td></tr>`; lastGroup = q.group; }
      rows += `<tr><td>${esc(q.label)}${depth != null ? ` @ ${depth} m` : ""}</td><td>${fmt(v, q)}${unit(q)}</td></tr>`;
    }
    pop.setContent(`<div class="pop"><h3>${esc(nodeName(nid))}</h3>
      <div class="when">${when(ts)} · ${lat.toFixed(5)}, ${lon.toFixed(5)}</div>
      <div class="big">${fmt(val, p)}<small>${unit(p)} ${esc(paramTitle())}</small></div>
      ${sparkline(series)}<table>${rows}</table></div>`);
  } catch (e) { console.error(e); }
}

// ---------------------------------------------------------------- heat surface (IDW)
/* Inverse-distance-weighted surface: every screen cell gets a weighted average of the
   readings within "reach", weighted by 1/distance². Cells farther than reach from any
   reading stay transparent, so we never paint values far from real measurements. */
function drawSurface() {
  if (surfaceOverlay) { map.removeLayer(surfaceOverlay); surfaceOverlay = null; }
  if (!$("lySurface").checked || !S.points.length || isDirection()) return;

  const R = S.reach, lat0 = map.getCenter().lat;
  const KX = 111320 * Math.cos(lat0 * Math.PI / 180), KY = 110540;

  // 1. average readings into small bins (so 300 readings from one parked buoy don't dominate)
  const binM = Math.max(25, R / 10), bins = new Map();
  for (const p of S.points) {
    const x = p[3] * KX, y = p[2] * KY, k = `${Math.round(x / binM)},${Math.round(y / binM)}`;
    const b = bins.get(k) || bins.set(k, { x: 0, y: 0, v: 0, n: 0 }).get(k);
    b.x += x; b.y += y; b.v += p[4]; b.n++;
  }
  // 2. spatial hash for neighbour lookup
  const grid = new Map();
  for (const b of bins.values()) {
    b.x /= b.n; b.y /= b.n; b.v /= b.n;
    const k = `${Math.floor(b.x / R)},${Math.floor(b.y / R)}`;
    (grid.get(k) || grid.set(k, []).get(k)).push(b);
  }
  // 3. evaluate on a coarse screen grid, then let the browser smooth it when scaling
  const size = map.getSize(), STEP = 4;
  const W = Math.ceil(size.x / STEP), H = Math.ceil(size.y / STEP);
  const xs = new Float64Array(W), ys = new Float64Array(H);
  for (let i = 0; i < W; i++) xs[i] = map.containerPointToLatLng([i * STEP + STEP / 2, 0]).lng * KX;
  for (let j = 0; j < H; j++) ys[j] = map.containerPointToLatLng([0, j * STEP + STEP / 2]).lat * KY;

  const cv = document.createElement("canvas"); cv.width = W; cv.height = H;
  const ctx = cv.getContext("2d"), img = ctx.createImageData(W, H), px = img.data;
  const R2 = R * R, EPS2 = 15 * 15, span = (S.vmax - S.vmin) || 1;
  let drew = false;
  for (let j = 0; j < H; j++) {
    const y = ys[j], gy = Math.floor(y / R);
    for (let i = 0; i < W; i++) {
      const x = xs[i], gx = Math.floor(x / R);
      let sw = 0, swv = 0, dmin = Infinity;
      for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) {
        const cell = grid.get(`${gx + a},${gy + b}`); if (!cell) continue;
        for (const q of cell) {
          const dx = q.x - x, dy = q.y - y, d2 = dx * dx + dy * dy;
          if (d2 > R2) continue;
          if (d2 < dmin) dmin = d2;
          const w = 1 / (d2 + EPS2); sw += w; swv += w * q.v;
        }
      }
      if (!sw) continue;
      const c = rampRgb((swv / sw - S.vmin) / span), o = (j * W + i) * 4;
      const fade = 1 - Math.sqrt(dmin) / R;
      px[o] = c[0]; px[o + 1] = c[1]; px[o + 2] = c[2]; px[o + 3] = 255 * 0.62 * Math.min(1, fade * 2.2);
      drew = true;
    }
  }
  if (!drew) return;
  ctx.putImageData(img, 0, 0);
  const b = map.getBounds();
  surfaceOverlay = L.imageOverlay(cv.toDataURL(), b, { opacity: 1, interactive: false }).addTo(map);
  surfaceOverlay.bringToBack();
}
map.on("moveend", () => { if (surfaceOverlay || $("lySurface").checked) drawSurface(); });

// ---------------------------------------------------------------- start
(async function init() {
  try {
    S.config = await getJSON("/api/config");
    document.title = S.config.title; $("title").textContent = S.config.title;
    S.params = await getJSON("/api/params");
    S.byKey = Object.fromEntries(S.params.map((p) => [p.key, p]));
    buildParamSelect();
    if (!S.params.some((p) => p.has_data)) { $("status").textContent = "No data yet — waiting for the first buoy packet."; }
    await load();
  } catch (e) {
    console.error(e); $("status").textContent = "Can't reach the server.";
  }
  setInterval(async () => {
    try {
      const fresh = await getJSON("/api/params");
      if (fresh.filter((p) => p.has_data).length !== S.params.filter((p) => p.has_data).length) {
        S.params = fresh; S.byKey = Object.fromEntries(fresh.map((p) => [p.key, p])); buildParamSelect();
      }
    } catch (_) { /* ignore */ }
    if (!map._popup || !map.hasLayer(map._popup)) load();
  }, REFRESH_MS);
})();
