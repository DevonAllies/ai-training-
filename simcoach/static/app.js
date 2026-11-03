"use strict";

const $ = (s) => document.querySelector(s);
const state = { units: "metric", ref: null, refCorners: [], trace: null, lastSnap: null };

// ------------------------------------------------------------ helpers
async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" }, ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  let data = null;
  try { data = await r.json(); } catch { /* empty */ }
  if (!r.ok) throw new Error((data && data.detail) || `HTTP ${r.status}`);
  return data;
}
const fmtTime = (s) => {
  if (s === null || s === undefined || !(s > 0)) return "-:--.---";
  const m = Math.floor(s / 60), r = s - m * 60;
  return `${m}:${r.toFixed(3).padStart(6, "0")}`;
};
const fmtDelta = (d) => (d === null || d === undefined ? "--.--" : (d >= 0 ? "+" : "−") + Math.abs(d).toFixed(2));
const spd = (ms) => (state.units === "metric" ? ms * 3.6 : ms * 2.23694);
const spdUnit = () => (state.units === "metric" ? "km/h" : "mph");
const dist = (m) => (state.units === "metric" ? `${Math.round(m)} m` : `${Math.round(m * 3.281)} ft`);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const msg = (el, text, cls = "") => { el.textContent = text; el.className = "msg " + cls; };
const signed = (v, digits = 0, unit = "") =>
  v === null || v === undefined ? "–" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}${unit}`;

// ------------------------------------------------------------ tabs
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab-page").forEach((p) => p.classList.toggle("active", p.id === "tab-" + name));
  if (name === "laps") { loadLocalLaps(); ensureCarTrackLists(); }
  if (name === "analyze") fillAnalyzeSelects();
  if (name === "settings") loadSettings();
}

// ------------------------------------------------------------ live
function connectWS() {
  const ws = new WebSocket(`ws://${location.host}/ws/live`);
  ws.onmessage = (ev) => onSnap(JSON.parse(ev.data));
  ws.onclose = () => { $("#conn").textContent = "App offline"; $("#conn").classList.remove("on"); setTimeout(connectWS, 1500); };
}

async function refreshReference() {
  const r = await api("/api/live/reference");
  state.ref = r.lap || null;
  state.refCorners = r.corners || [];
}

function onSnap(s) {
  state.lastSnap = s;
  const conn = $("#conn");
  conn.textContent = s.status; conn.classList.toggle("on", !!s.connected);
  const sess = s.session || {};
  $("#sess-track").textContent = sess.track ? `${sess.track}${sess.track_config ? " – " + sess.track_config : ""}` : "No session";
  $("#sess-car").textContent = sess.car || "";
  if ((s.reference || "") !== ($("#ref-label").dataset.v || "")) {
    $("#ref-label").dataset.v = s.reference || "";
    $("#ref-label").textContent = s.reference || "none";
    refreshReference();
  }
  $("#ref-time").textContent = s.ref_lap_time ? fmtTime(s.ref_lap_time) : "";

  const d = s.delta;
  const del = $("#delta");
  del.textContent = fmtDelta(d);
  del.className = "delta " + (d === undefined ? "" : d > 0 ? "bad" : "good");
  const fill = $("#delta-fill");
  if (d !== undefined) {
    const pct = Math.min(50, (Math.abs(d) / 2) * 50);
    fill.style.width = pct + "%";
    fill.style.left = d > 0 ? "50%" : 50 - pct + "%";
    fill.style.background = d > 0 ? "var(--bad)" : "var(--good)";
  } else fill.style.width = 0;

  const tr = $("#trend");
  if (s.trend !== undefined && Math.abs(s.trend) > 0.03) {
    tr.textContent = s.trend > 0 ? `Losing time here (${fmtDelta(s.trend)}s)` : `Gaining time here (${fmtDelta(s.trend)}s)`;
    tr.className = "trend " + (s.trend > 0 ? "bad" : "good");
  } else { tr.innerHTML = "&nbsp;"; tr.className = "trend"; }

  $("#elapsed").textContent = fmtTime(s.elapsed);
  $("#predicted").textContent = fmtTime(s.predicted);
  $("#next-corner").textContent = s.next_corner ? `${s.next_corner} · ${dist(s.next_corner_m)}` : "–";

  $("#spd-me").textContent = s.speed !== undefined ? spd(s.speed).toFixed(0) : "0";
  $("#spd-ref").textContent = s.ref_speed !== undefined ? spd(s.ref_speed).toFixed(0) : "–";
  $("#gear").textContent = s.gear === undefined ? "N" : s.gear === -1 ? "R" : s.gear === 0 ? "N" : s.gear;
  $("#thr").style.width = ((s.throttle || 0) * 100) + "%";
  $("#brk").style.width = ((s.brake || 0) * 100) + "%";
  $("#thr-ref").style.left = `calc(${(s.ref_throttle || 0) * 100}% - 3px)`;
  $("#brk-ref").style.left = `calc(${(s.ref_brake || 0) * 100}% - 3px)`;
  $("#thr-ref").style.display = s.ref_throttle === undefined ? "none" : "";
  $("#brk-ref").style.display = s.ref_brake === undefined ? "none" : "";

  renderCallouts(s.callouts || []);
  renderSessionLaps(s.laps || []);
  if (s.trace) state.trace = s.trace;
  if ($("#tab-live").classList.contains("active")) drawLiveChart(s.pct);
}

function renderCallouts(list) {
  const ul = $("#callouts");
  const key = list.map((c) => c.name + c.time_lost).join();
  if (ul.dataset.k === key) return;
  ul.dataset.k = key;
  if (!list.length) { ul.innerHTML = '<li class="muted">Complete a corner to get feedback.</li>'; return; }
  ul.innerHTML = list.slice().reverse().map((c) => {
    const cls = c.time_lost > 0 ? "pos" : "neg";
    const tips = c.tips.length ? c.tips.map(esc).join("<br>") : "On pace.";
    return `<li><span class="t ${cls}">${esc(c.name)} ${fmtDelta(c.time_lost)}s</span><br>${tips}</li>`;
  }).join("");
}

function renderSessionLaps(laps) {
  const tb = $("#session-laps tbody");
  const key = laps.length + ":" + (laps[laps.length - 1] || {}).lap_time;
  if (tb.dataset.k === key) return;
  tb.dataset.k = key;
  tb.innerHTML = laps.slice().reverse().map((l, i) =>
    `<tr><td>${laps.length - i}</td><td>${fmtTime(l.lap_time)}</td>
     <td class="${l.gap > 0 ? "pos" : "neg"}">${l.gap !== undefined ? fmtDelta(l.gap) : ""}</td>
     <td>${l.valid ? "" : '<span class="muted">invalid</span>'}</td></tr>`).join("");
}

function drawLiveChart(pct) {
  const canvas = $("#live-chart");
  const ref = state.ref, tr = state.trace || {};
  const series = [];
  if (ref) series.push({ data: ref.speed.map(spd), color: Charts.css("--ref"), width: 1.5 });
  if (tr.speed) series.push({ data: tr.speed.map(spd), color: Charts.css("--me"), width: 2 });
  if (tr.delta) series.push({ data: tr.delta, color: "rgba(255,255,255,0.55)", width: 1, axis: "right" });
  Charts.line(canvas, series, {
    n: 1000, ymin: 0, ymax: ref ? Math.max(...ref.speed.map(spd)) * 1.08 : undefined,
    regions: state.refCorners.map((c) => ({ start: c.start, end: c.end, apex: c.apex, label: c.name })),
    cursor: pct,
  });
}

$("#btn-ref-best").addEventListener("click", async () => {
  try { await api("/api/live/reference", { method: "POST", body: { lap: "session_best" } }); }
  catch (e) { alert(e.message); }
});
$("#btn-analyze-last").addEventListener("click", async () => {
  showTab("analyze");
  await fillAnalyzeSelects();
  $("#a-mine").value = "last";
  if (state.lastSnap && state.lastSnap.reference) $("#a-ref").value = "live_ref";
  runCompare();
});

// ------------------------------------------------------------ garage 61 laps
let carTrackLoaded = false;
async function ensureCarTrackLists() {
  if (carTrackLoaded) return;
  try {
    const [cars, tracks] = await Promise.all([api("/api/g61/cars"), api("/api/g61/tracks")]);
    $("#f-car").innerHTML = '<option value="">Any car</option>' +
      cars.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
    $("#f-track").innerHTML = '<option value="">Any track</option>' +
      tracks.map((t) => `<option value="${t.id}">${esc(t.name)}${t.variant ? " – " + esc(t.variant) : ""}</option>`).join("");
    carTrackLoaded = true;
    matchSession(true);
  } catch (e) { msg($("#laps-msg"), e.message, "err"); }
}

async function matchSession(quiet) {
  try {
    const m = await api("/api/g61/match");
    if (m.car) $("#f-car").value = m.car.id;
    if (m.track) $("#f-track").value = m.track.id;
    if (!quiet) msg($("#laps-msg"), m.car || m.track ? "Matched current iRacing session." : "No iRacing session to match.");
  } catch (e) { if (!quiet) msg($("#laps-msg"), e.message, "err"); }
}
$("#btn-match").addEventListener("click", () => matchSession(false));

$("#btn-search").addEventListener("click", searchLaps);
async function searchLaps() {
  const q = new URLSearchParams({ scope: $("#f-scope").value, group: $("#f-group").value });
  if ($("#f-car").value) q.set("car", $("#f-car").value);
  if ($("#f-track").value) q.set("track", $("#f-track").value);
  msg($("#laps-msg"), "Searching Garage 61…");
  try {
    const laps = await api("/api/g61/laps?" + q);
    state.g61Laps = laps;
    msg($("#laps-msg"), `${laps.length} laps found.`, "ok");
    const best = laps.length ? laps[0].lap_time : null;
    $("#g61-laps tbody").innerHTML = laps.map((l, i) => `
      <tr class="${l.is_me ? "me" : ""}">
        <td>${i + 1}</td><td>${esc(l.driver)}</td>
        <td>${fmtTime(l.lap_time)} <span class="muted">${i && best ? "+" + (l.lap_time - best).toFixed(3) : ""}</span></td>
        <td>${esc(l.car)}</td><td>${esc(l.track)}</td>
        <td>${l.date ? new Date(l.date).toLocaleDateString() : ""}</td>
        <td>${l.can_view_telemetry === false ? '<span class="muted">no telemetry access</span>' : `
          <button class="small" data-act="ref" data-id="${esc(l.id)}">Set as live reference</button>
          <button class="small" data-act="cmp" data-id="${esc(l.id)}">Compare</button>`}</td>
      </tr>`).join("");
  } catch (e) { msg($("#laps-msg"), e.message, "err"); }
}

$("#g61-laps").addEventListener("click", async (ev) => {
  const b = ev.target.closest("button"); if (!b) return;
  const key = "g61:" + b.dataset.id;
  if (b.dataset.act === "ref") {
    msg($("#laps-msg"), "Downloading telemetry…");
    try {
      const r = await api("/api/live/reference", { method: "POST", body: { lap: key } });
      msg($("#laps-msg"), `Live reference set: ${r.reference}`, "ok");
    } catch (e) { msg($("#laps-msg"), e.message, "err"); }
  } else {
    showTab("analyze"); await fillAnalyzeSelects();
    addOption($("#a-ref"), key, b.closest("tr").children[1].textContent + " " + b.closest("tr").children[2].textContent.split(" ")[0]);
    $("#a-ref").value = key;
  }
});

async function loadLocalLaps() {
  try {
    const laps = await api("/api/local/laps");
    state.localLaps = laps;
    $("#local-laps tbody").innerHTML = laps.length ? laps.map((l) => `
      <tr><td>${esc(l.label)}</td><td>${fmtTime(l.lap_time)}</td><td>${esc(l.car)}</td><td>${esc(l.track)}</td>
      <td>${l.date ? new Date(l.date).toLocaleString() : ""}</td>
      <td><button class="small" data-act="ref" data-f="${esc(l.file)}">Set as live reference</button>
          <button class="small" data-act="del" data-f="${esc(l.file)}">Delete</button></td></tr>`).join("")
      : '<tr><td colspan="6" class="muted">No laps recorded yet. Drive with SimCoach running.</td></tr>';
  } catch (e) { /* ignore */ }
}
$("#local-laps").addEventListener("click", async (ev) => {
  const b = ev.target.closest("button"); if (!b) return;
  if (b.dataset.act === "del") {
    if (!confirm("Delete this lap?")) return;
    await api("/api/local/laps/" + encodeURIComponent(b.dataset.f), { method: "DELETE" });
    loadLocalLaps();
  } else {
    await api("/api/live/reference", { method: "POST", body: { lap: "local:" + b.dataset.f } });
  }
});

// ------------------------------------------------------------ analyse
function addOption(sel, value, label) {
  if ([...sel.options].some((o) => o.value === value)) return;
  const o = document.createElement("option"); o.value = value; o.textContent = label; sel.appendChild(o);
}
async function fillAnalyzeSelects() {
  const mine = $("#a-mine"), ref = $("#a-ref");
  const keepM = mine.value, keepR = ref.value;
  mine.innerHTML = ""; ref.innerHTML = "";
  const st = await api("/api/status");
  const local = await api("/api/local/laps").catch(() => []);
  addOption(mine, "last", "Last lap (this session)");
  addOption(mine, "session_best", "Session best");
  if (st.demo) { addOption(mine, "demo:you", "Demo – your lap"); }
  if (st.live.reference) addOption(ref, "live_ref", `Live reference (${st.live.reference})`);
  if (st.demo) addOption(ref, "demo:ref", "Demo – reference lap");
  addOption(ref, "session_best", "Session best");
  local.forEach((l) => {
    addOption(mine, "local:" + l.file, `${l.label} – ${l.track || ""}`);
    addOption(ref, "local:" + l.file, `${l.label} – ${l.track || ""}`);
  });
  (state.g61Laps || []).filter((l) => l.can_view_telemetry !== false).forEach((l) => {
    addOption(ref, "g61:" + l.id, `G61: ${l.driver} ${fmtTime(l.lap_time)}`);
    if (l.is_me) addOption(mine, "g61:" + l.id, `G61: ${l.driver} ${fmtTime(l.lap_time)}`);
  });
  if (keepM) mine.value = keepM;
  if (keepR) ref.value = keepR;
}

$("#btn-compare").addEventListener("click", runCompare);
async function runCompare() {
  const mine = $("#a-mine").value, ref = $("#a-ref").value;
  if (!mine || !ref) { msg($("#a-msg"), "Pick two laps.", "err"); return; }
  msg($("#a-msg"), "Comparing…");
  try {
    let r;
    r = await api(`/api/compare?mine=${encodeURIComponent(mine)}&ref=${encodeURIComponent(ref)}`);
    msg($("#a-msg"), "");
    renderComparison(r);
  } catch (e) { msg($("#a-msg"), e.message, "err"); }
}

function renderComparison(r) {
  $("#a-result").classList.remove("hidden");
  const c = r.comparison;
  $("#a-me").textContent = fmtTime(c.lap_time_me);
  $("#a-reftime").textContent = fmtTime(c.lap_time_ref);
  $("#a-gap").textContent = fmtDelta(c.gap) + "s";
  $("#a-gap").className = "big " + (c.gap > 0 ? "pos" : "neg");
  $("#a-focus").textContent = c.focus.length ? c.focus.join(", ") : "Nothing major";

  const regions = r.corners.map((k) => ({ start: k.start, end: k.end, apex: k.apex, label: k.name }));
  const me = r.me, ref = r.ref;
  const draw = () => {
    Charts.line($("#c-delta"), [
      { data: c.delta, fill: "rgba(255,90,95,0.18)" },
      { data: c.delta, color: "#fff", width: 1.5 }], { n: 1000, regions, zeroLine: true, fmt: (v) => v.toFixed(2) });
    Charts.line($("#c-speed"), [
      { data: ref.speed.map(spd), color: Charts.css("--ref") },
      { data: me.speed.map(spd), color: Charts.css("--me") }], { n: 1000, ymin: 0, regions });
    Charts.line($("#c-pedals"), [
      { data: ref.throttle.map((v) => v * 100), color: Charts.css("--ref") },
      { data: me.throttle.map((v) => v * 100), color: Charts.css("--me") },
      { data: ref.brake.map((v) => -v * 100), color: Charts.css("--ref") },
      { data: me.brake.map((v) => -v * 100), color: Charts.css("--me") }],
      { n: 1000, ymin: -105, ymax: 105, regions, fmt: (v) => Math.abs(v).toFixed(0) + "%" });
    const lat = ref.lat || me.lat, lon = ref.lon || me.lon;
    $("#map-none").classList.toggle("hidden", !!lat);
    $("#c-map").classList.toggle("hidden", !lat);
    if (lat) {
      const step = c.delta.map((v, i) => (i ? v - c.delta[i - 1] : 0));
      const sm = step.map((_, i) => { let s = 0, n = 0; for (let k = -6; k <= 6; k++) { const j = i + k; if (j >= 0 && j < step.length) { s += step[j]; n++; } } return s / n; });
      Charts.trackMap($("#c-map"), lat, lon, sm, { labels: r.corners.map((k) => ({ i: k.apex, text: k.name })) });
    }
  };
  state.redrawAnalysis = draw;
  draw();

  $("#corner-table tbody").innerHTML = c.corners.map((k) => `
    <tr><td><b>${esc(k.name)}</b></td>
      <td class="${k.time_lost > 0.02 ? "pos" : k.time_lost < -0.02 ? "neg" : ""}">${fmtDelta(k.time_lost)}s
        <div class="muted small-text">entry ${fmtDelta(k.entry_lost)} / exit ${fmtDelta(k.exit_lost)}</div></td>
      <td>${k.brake_point_m === null ? "–" : signed(state.units === "metric" ? k.brake_point_m : k.brake_point_m * 3.281, 0, state.units === "metric" ? " m" : " ft")}</td>
      <td>${signed(state.units === "metric" ? k.min_speed_diff_kmh : k.min_speed_diff_kmh / 1.609, 1, " " + spdUnit())}</td>
      <td>${signed(state.units === "metric" ? k.exit_speed_diff_kmh : k.exit_speed_diff_kmh / 1.609, 1, " " + spdUnit())}</td>
      <td>${k.throttle_point_m === null ? "–" : signed(state.units === "metric" ? k.throttle_point_m : k.throttle_point_m * 3.281, 0, state.units === "metric" ? " m" : " ft")}</td>
      <td class="tips">${k.tips.map((t) => `<div>${esc(t)}</div>`).join("") || '<span class="muted">On pace</span>'}</td></tr>`).join("");
}
window.addEventListener("resize", () => { if (state.redrawAnalysis) state.redrawAnalysis(); });

// ------------------------------------------------------------ settings
async function loadSettings() {
  const c = await api("/api/config");
  $("#s-token").value = "";
  $("#s-token-hint").textContent = c.has_token ? `Saved token: ${c.token_hint || "set"}` : "No token saved yet.";
  $("#s-units").value = c.units;
  $("#s-following").checked = c.include_following;
  $("#s-record").checked = c.record_laps;
  $("#s-extra").value = (c.extra_drivers || []).join(", ");
}
$("#btn-save").addEventListener("click", async () => {
  const body = {
    units: $("#s-units").value, include_following: $("#s-following").checked,
    record_laps: $("#s-record").checked, extra_drivers: $("#s-extra").value.split(","),
  };
  if ($("#s-token").value.trim()) body.garage61_token = $("#s-token").value.trim();
  try {
    const c = await api("/api/config", { method: "POST", body });
    state.units = c.units; applyUnits(); carTrackLoaded = false;
    msg($("#s-msg"), "Saved.", "ok"); loadSettings();
  } catch (e) { msg($("#s-msg"), e.message, "err"); }
});
$("#btn-test").addEventListener("click", async () => {
  msg($("#s-msg"), "Contacting Garage 61…");
  try {
    const me = await api("/api/g61/me");
    msg($("#s-msg"), `Connected as ${[me.firstName, me.lastName].filter(Boolean).join(" ") || me.slug || "your account"}.`, "ok");
  } catch (e) { msg($("#s-msg"), e.message, "err"); }
});
function applyUnits() { document.querySelectorAll('[data-unit="speed"]').forEach((e) => (e.textContent = spdUnit())); }

// ------------------------------------------------------------ boot
(async function boot() {
  try {
    const st = await api("/api/status");
    state.units = st.config.units; applyUnits();
    if (!st.config.has_token && !st.demo) showTab("settings");
  } catch { /* server not up yet */ }
  await refreshReference().catch(() => {});
  connectWS();
})();
