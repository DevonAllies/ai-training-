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
  if (name === "sessions") loadSessions();
  if (name === "corners") initCorners();
  if (name === "race") refreshRace();
  if (name === "progress") { initProgress(); loadGoal(); loadGame(); }
  if (name === "race") loadRaceReports();
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
  $("#next-corner").title = s.next_corner_title || "";

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
  renderEvents(s.events || []);
  renderSectors(s.sectors || [], s.session && s.session.sectors ? s.session.sectors.length : 0, s.sector_targets);
  $("#sector-target").textContent = s.sector_target_label ? `· target: ${s.sector_target_label}` : "";
  renderSessionLaps(s.laps || []);
  renderGrades(s.scores);
  renderDrill(s.focus || {});
  renderConsistency(s.consistency || {});
  applyFeatures(s.features);
  const lapKey = (s.laps || []).length + ":" + ((s.laps || []).slice(-1)[0] || {}).lap_time;
  if (state.reportKey !== lapKey) { state.reportKey = lapKey; loadReport(); }
  fillDrillCorners();
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
    return `<li><span class="t ${cls}">${esc(c.title || c.name)} ${fmtDelta(c.time_lost)}s</span><br>${tips}</li>`;
  }).join("");
}

function renderEvents(list) {
  const ul = $("#events");
  const key = list.map((e) => e.corner + e.kind + e.t).join();
  if (ul.dataset.k === key) return;
  ul.dataset.k = key;
  if (!list.length) { ul.innerHTML = '<li class="muted">Drive through a corner to see feedback.</li>'; return; }
  ul.innerHTML = list.slice().reverse().map((e) =>
    `<li><span class="sev ${e.severity}"></span><span class="t">${esc(e.title || e.corner)}</span> ${esc(e.text)}</li>`).join("");
}

function renderSectors(done, n, targets) {
  const el = $("#live-sectors");
  const key = n + ":" + done.map((x) => x.time).join();
  if (el.dataset.k === key) return;
  el.dataset.k = key;
  if (!n) { el.innerHTML = '<span class="muted">This track has no sector information.</span>'; return; }
  let html = "";
  for (let i = 1; i <= n; i++) {
    const x = done.find((d) => d.sector === i);
    const tgt = targets && targets[i - 1] ? targets[i - 1].toFixed(3) : "";
    if (x) {
      const cls = x.delta == null ? "" : x.delta <= 0 ? "good" : "bad";
      html += `<div class="chip ${cls}"><small>S${i}</small>${x.time.toFixed(3)}<small>${x.delta == null ? "" : fmtDelta(x.delta)}</small></div>`;
    } else html += `<div class="chip"><small>S${i}</small>–<small>${tgt}</small></div>`;
  }
  el.innerHTML = html;
}

const GRADE_LABELS = [["braking", "Braking"], ["turn_in", "Turn-in"], ["trail_braking", "Trail braking"],
  ["min_speed", "Min speed"], ["throttle", "Throttle"], ["line", "Racing line"], ["car_control", "Car control"],
  ["technique", "Technique"], ["pace", "Pace"]];
const gradeColor = (v) => (v >= 85 ? "var(--good)" : v >= 65 ? "var(--ref)" : "var(--bad)");
function renderGrades(sc) {
  const el = $("#grades");
  const key = JSON.stringify(sc || null);
  if (el.dataset.k === key) return;
  el.dataset.k = key;
  if (!sc) return;
  el.innerHTML = GRADE_LABELS.filter(([k]) => sc[k] !== null && sc[k] !== undefined).map(([k, l]) =>
    `<div class="grade"><span>${l}</span><div class="gbar"><div style="width:${sc[k]}%;background:${gradeColor(sc[k])}"></div></div><b>${sc[k]}</b></div>`).join("");
}

function renderDrill(f) {
  const el = $("#drill");
  const key = JSON.stringify(f);
  if (el.dataset.k === key) return;
  el.dataset.k = key;
  if (!f.active) {
    el.innerHTML = '<span class="muted">Off. The coach picks the corner where you lose most and moves on once you\'re on target ' +
      (f.needed || 3) + ' laps in a row.</span>' + (f.completed && f.completed.length ? `<div class="muted">Mastered: ${f.completed.map(esc).join(", ")}</div>` : "");
    return;
  }
  const dots = Array.from({ length: f.needed }, (_, i) => `<i class="${i < f.streak ? "on" : ""}"></i>`).join("");
  const ladder = f.kind === "brake_ladder" && (f.ladder_target != null || f.ladder_locked != null)
    ? `<div class="small-text"><b>Brake point target:</b> ${(f.ladder_locked ?? f.ladder_target).toFixed(0)} m vs reference${f.ladder_locked != null ? " (locked – hit it)" : " (5 m later each lap)"}</div>` : "";
  el.innerHTML = `<div><span class="big">${esc(f.title || f.name || "–")}</span> <span class="badge">${esc(f.drill || "")}</span><span class="streak">${dots}</span></div>
    <div class="muted small-text">${esc(f.how || "")}</div>
    <div style="margin-top:4px">${esc(f.message || "")}</div>${ladder}
    <ul class="drill-results">${(f.results || []).slice().reverse().map((x) => `<li><span class="sev ${x.ok ? "good" : "bad"}"></span>#${x.attempt}: ${esc(x.text)}</li>`).join("")}</ul>
    <div class="muted small-text">Attempts ${f.attempts}${f.last_loss !== null ? " · last " + fmtDelta(f.last_loss) + "s" : ""}</div>
    ${f.completed.length ? `<div class="muted small-text">Done: ${f.completed.map(esc).join(", ")}</div>` : ""}`;
}

function fillDrillCorners() {
  const sel = $("#drill-corner");
  const names = state.refCorners.map((c) => c.title || c.name).join();
  if (sel.dataset.k === names) return;
  sel.dataset.k = names;
  sel.innerHTML = '<option value="">or choose corner…</option>' + state.refCorners.map((c, i) => `<option value="${i}">${esc(c.title || c.name)}</option>`).join("");
}
$("#drill-auto").addEventListener("click", () => api("/api/coach/focus", { method: "POST", body: { action: "auto" } }));
$("#drill-stop").addEventListener("click", () => api("/api/coach/focus", { method: "POST", body: { action: "stop" } }));
$("#drill-corner").addEventListener("change", (e) => {
  if (e.target.value !== "") api("/api/coach/focus", { method: "POST", body: { action: "corner", corner: +e.target.value, kind: $("#drill-kind").value || null } });
});

async function loadReport() {
  let r;
  try { r = await api("/api/coach/report"); } catch { return; }
  const el = $("#report");
  if (!r.laps) { el.innerHTML = '<span class="muted">Appears after your first complete lap against a reference.</span>'; return; }
  const rows = r.corners.slice().sort((a, b) => b.avg_loss - a.avg_loss).map((c) => `
    <tr><td><b>${esc(c.title || c.name)}</b></td><td class="${c.avg_loss > 0.05 ? "pos" : c.avg_loss < -0.02 ? "neg" : ""}">${fmtDelta(c.avg_loss)}s</td>
      <td>${fmtDelta(c.best_loss)}s</td><td>±${c.spread.toFixed(2)}</td>
      <td>${c.main_issue ? esc(c.main_issue) + ` <span class="muted">(${c.main_issue_laps}/${c.laps})</span>` : '<span class="muted">–</span>'}</td></tr>`).join("");
  const trend = r.trend.map((t) => t.technique ?? 0);
  el.innerHTML = `<div class="report-grid"><div>
      <ul class="tips-list">${r.summary.map((t) => `<li>${esc(t)}</li>`).join("") || "<li>No significant time loss – great driving.</li>"}</ul>
      <p class="muted small-text">${r.laps} laps · best ${fmtTime(r.best_lap)} · average gap ${fmtDelta(r.avg_gap)}s ·
        time on the table vs reference ${r.potential.toFixed(2)}s, vs your own best corners ${r.own_potential.toFixed(2)}s</p>
      <div class="label">Technique grade per lap</div><canvas id="c-trend" height="90"></canvas></div>
    <div><table class="tbl"><thead><tr><th>Corner</th><th>Avg</th><th>Best</th><th>Spread</th><th>Most common issue</th></tr></thead>
      <tbody>${rows}</tbody></table></div></div>`;
  if (trend.length > 1) Charts.line($("#c-trend"), [{ data: trend, color: Charts.css("--me"), width: 2 }], { ymin: 0, ymax: 100 });
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

// ------------------------------------------------------------ optimal lap
async function buildOptimal(setRef) {
  msg($("#opt-msg"), "Building your optimal lap…");
  try {
    const r = await api("/api/optimal", { method: "POST", body: { include_teammates: $("#opt-team").checked, set_reference: setRef } });
    msg($("#opt-msg"), `${r.label}${setRef ? " – now your live reference." : " saved to your laps."}`, "ok");
    const gain = r.best_single_lap - r.lap_time;
    $("#opt-result").innerHTML = `<p>Optimal <b>${fmtTime(r.lap_time)}</b> vs your best single lap ${fmtTime(r.best_single_lap)}
      – <b class="neg">${gain.toFixed(3)}s</b> is already in you. Built from ${r.laps_used} of ${r.candidates} laps.</p>
      <table class="tbl"><thead><tr><th>Part of the lap</th><th>Time</th><th>Taken from</th></tr></thead><tbody>` +
      r.segments.map((s, i) => `<tr><td>${i + 1} (${(s.start / 10).toFixed(0)}–${(s.end / 10).toFixed(0)} %)</td><td>${s.duration.toFixed(3)}s</td><td>${esc(s.from)}</td></tr>`).join("") +
      "</tbody></table>";
    loadLocalLaps(); if (setRef) refreshReference();
  } catch (e) { msg($("#opt-msg"), e.message, "err"); }
}
$("#opt-build").addEventListener("click", () => buildOptimal(false));
$("#opt-build-ref").addEventListener("click", () => buildOptimal(true));

// ------------------------------------------------------------ race / endurance / fuel
let raceTimer = null;
const fmtL = (v, d = 2) => (v == null ? "–" : v.toFixed(d) + " L");
async function refreshRace() {
  clearTimeout(raceTimer);
  if (!$("#tab-race").classList.contains("active")) return;
  try {
    const r = await api("/api/race");
    const card = (label, val, sub = "") => `<div class="card stat"><div class="label">${label}</div><div class="big">${val}</div><div class="muted small-text">${sub}</div></div>`;
    const pw = r.pit_window ? `lap ${r.pit_window.open}–${r.pit_window.close}` : (r.stops_needed === 0 ? "no stop needed" : "–");
    $("#race-cards").innerHTML =
      card("Fuel", fmtL(r.fuel_level, 1), r.tank ? `tank ${r.tank.toFixed(0)} L` : "") +
      card("Fuel per lap", fmtL(r.fuel_per_lap, 3), r.laps_of_fuel != null ? `${r.laps_of_fuel.toFixed(1)} laps left in the tank` : "drive a lap") +
      card("Laps to go", r.laps_to_go != null ? r.laps_to_go.toFixed(0) : "–", r.fuel_to_finish != null ? `need ${r.fuel_to_finish.toFixed(1)} L more · ${r.stops_needed ?? "–"} stop(s)` : "") +
      card("Pit window", pw, `stint ${r.stint} · ${r.stint_laps} laps`) +
      card("Stint pace", fmtTime(r.stint_avg), r.dropoff != null ? `${r.dropoff > 0 ? "+" : ""}${r.dropoff.toFixed(3)} s/lap trend · ±${(r.consistency ?? 0).toFixed(2)}s` : "3+ laps for the trend");
    const laps = r.laps || [];
    const green = laps.filter((l) => l.valid && !l.pit);
    if (green.length > 1) Charts.line($("#c-stint"), [{ data: green.map((l) => l.lap_time), color: Charts.css("--me"), width: 2 }], { fmt: (v) => v.toFixed(1) });
    $("#stint-table tbody").innerHTML = laps.slice().reverse().map((l) => `<tr><td>${l.lap}</td><td>${l.stint}</td><td>${fmtTime(l.lap_time)}</td>
      <td>${l.fuel != null ? l.fuel.toFixed(3) + " L" : "–"}</td><td class="muted">${l.pit ? "pit" : l.valid ? "" : "invalid"}</td></tr>`).join("");
    renderFuelPlan(r.fuel_save);
  } catch (e) { /* not connected */ }
  raceTimer = setTimeout(refreshRace, 2000);
}

function renderFuelPlan(p) {
  const el = $("#fs-plan");
  if (!p) { el.innerHTML = '<span class="muted">Fuel saving is off.</span>'; return; }
  const x = p.extra_lap ? `<p>Tank lasts <b>${p.extra_lap.laps_now.toFixed(2)}</b> laps now – goal <b>${p.extra_lap.laps_goal}</b>: save ${fmtL(p.extra_lap.save_per_lap, 3)} per lap.</p>` : "";
  el.innerHTML = x + `<p><b>${p.reached ? "Plan" : "Best possible"}:</b> save ~${fmtL(p.total_saved_l, 3)} per lap for ~${p.total_lost_s.toFixed(2)} s per lap (estimate${p.coast_model.measured ? ", coast-down measured from your lap" : ", typical coast-down – drive with some lifts to measure yours"}).</p>
    <table class="tbl"><thead><tr><th>Corner</th><th>Lift before brake point</th><th>Fuel saved</th><th>Time cost</th></tr></thead><tbody>` +
    (p.plan || []).map((z) => `<tr><td><b>${esc(z.title || z.corner)}</b> <span class="muted">${z.speed_kmh} km/h</span></td><td>${dist(z.lift_m)}</td><td>${z.saved_l.toFixed(3)} L</td><td>${z.lost_s.toFixed(3)} s</td></tr>`).join("") +
    "</tbody></table><p class='muted small-text'>Lift off the throttle completely at the marked distance, coast, then brake a little later and lighter. The overlay shows LIFT.</p>";
}
async function fuelSave(body) {
  msg($("#fs-msg"), "Planning…");
  try { const r = await api("/api/fuelsave", { method: "POST", body }); msg($("#fs-msg"), r.active ? "Fuel saving active – watch for LIFT on the overlay." : "Fuel saving off.", "ok"); renderFuelPlan(r.active ? r : null); }
  catch (e) { msg($("#fs-msg"), e.message, "err"); }
}
$("#fs-extra").addEventListener("click", () => fuelSave({ mode: "extra_lap" }));
$("#fs-target-go").addEventListener("click", () => fuelSave({ mode: "target", save_per_lap: parseFloat($("#fs-target").value) || 0.1 }));
$("#fs-off").addEventListener("click", () => fuelSave({ mode: "off" }));

$("#ep-go").addEventListener("click", async () => {
  const num = (id) => { const v = $(id).value.trim(); return v ? (id === "#ep-lap" ? parseLapTime(v) : parseFloat(v)) : null; };
  msg($("#ep-msg"), "Planning…");
  try {
    const r = await api("/api/race/plan", { method: "POST", body: { race_minutes: num("#ep-min"), race_laps: num("#ep-laps"),
      avg_lap: num("#ep-lap"), fuel_per_lap: num("#ep-fpl"), tank: num("#ep-tank"), pit_loss_s: num("#ep-pit") || 60,
      fuel_now: num("#ep-fuelnow") } });
    msg($("#ep-msg"), "");
    const left = r.race_time_s ? `${Math.floor(r.race_time_s / 3600)}h ${String(Math.round((r.race_time_s % 3600) / 60)).padStart(2, "0")}m` : null;
    $("#ep-result").innerHTML = `<p>${r.from_now ? `<b>From now</b> (${fmtL(r.fuel_now, 1)} in the tank${left ? ", " + left + " to go" : ""}): ` : ""}<b>${r.total_laps}</b> laps · <b>${r.stops}</b> stop(s) · ${r.laps_per_tank} laps per tank at ${fmtL(r.fuel_per_lap, 3)}/lap</p>
      <p class="muted small-text">Fuel needed ${fmtL(r.fuel_needed, 1)} · margin at the flag ${fmtL(r.fuel_margin, 1)}</p>
      <p>Stints: ${r.stints.map((n, i) => `<span class="badge">${i === 0 && r.from_now ? "now" : i + 1}: ${n} laps</span>`).join("")}</p>
      ${r.fuel_per_stop.length ? `<p class="muted small-text">Fuel per stop: ${r.fuel_per_stop.map((f) => f + " L").join(", ")}</p>` : ""}
      <div class="label">What fuel saving buys you</div>` + (r.options.map((o) => `<div class="plan-step"><b>${esc(o.name)}</b>
        save ${fmtL(o.save_per_lap, 3)}/lap (${o.save_pct}%)${o.time_cost_per_lap_s != null ? ` · costs ~${o.time_cost_per_lap_s.toFixed(3)} s/lap (${o.time_cost_race_s.toFixed(0)} s over the race)` : ""}
        ${o.net_gain_s != null ? `<br><span class="${o.net_gain_s > 0 ? "neg" : "pos"}">Net ${o.net_gain_s > 0 ? "gain" : "loss"}: ${Math.abs(o.net_gain_s).toFixed(0)} s vs making the extra stop</span>` : ""}</div>`).join("") || '<span class="muted">No useful saving option.</span>');
  } catch (e) { msg($("#ep-msg"), e.message, "err"); }
});

// planner sources: live session / Garage 61 / imported export
async function planSources(scope) {
  const q = new URLSearchParams({ scope: scope || "me" });
  if ($("#f-car") && $("#f-car").value) q.set("car", $("#f-car").value);
  if ($("#f-track") && $("#f-track").value) q.set("track", $("#f-track").value);
  return api("/api/race/sources?" + q);
}
const setIf = (id, v, fmt) => { if (v != null && v !== "") $(id).value = fmt ? fmt(v) : v; };
$("#ep-src-live").addEventListener("click", async () => {
  const s = (await planSources()).live;
  if (!s) { msg($("#ep-src-msg"), "No live session – start iRacing and drive a lap or two.", "err"); return; }
  if (s.time_left_s) { $("#ep-min").value = Math.round(s.time_left_s / 60); $("#ep-laps").value = ""; }
  else if (s.laps_left) { $("#ep-laps").value = Math.round(s.laps_left); $("#ep-min").value = ""; }
  setIf("#ep-lap", s.lap_time, fmtTime); setIf("#ep-fpl", s.fuel_per_lap, (v) => v.toFixed(3));
  setIf("#ep-tank", s.tank, (v) => v.toFixed(1)); setIf("#ep-fuelnow", s.fuel_now, (v) => v.toFixed(1));
  msg($("#ep-src-msg"), `Live: ${s.time_left_s ? Math.round(s.time_left_s / 60) + " min left" : s.laps_left ? s.laps_left + " laps left" : "no race clock"}` +
    `, ${s.fuel_now ? s.fuel_now.toFixed(1) + " L in the tank" : "fuel unknown"}${s.lap_time ? "" : " – drive a few laps for pace and fuel/lap"}.`, "ok");
});
$("#ep-src-g61").addEventListener("click", async () => {
  msg($("#ep-src-msg"), "Asking Garage 61…");
  const g = (await planSources($("#ep-g61-scope").value)).garage61;
  if (!g || g.error) { msg($("#ep-src-msg"), g ? g.error : "Garage 61 not available", "err"); return; }
  if (!g.laps) { msg($("#ep-src-msg"), "Garage 61 has no laps for this car/track yet.", "err"); return; }
  setIf("#ep-lap", g.lap_time, fmtTime); setIf("#ep-fpl", g.fuel_per_lap, (v) => v.toFixed(3));
  msg($("#ep-src-msg"), `Garage 61 (${g.scope === "me" ? "your" : "your + teammates'"} laps): race pace ${fmtTime(g.lap_time)} from ${g.laps} clean laps within 3 % of the best (${fmtTime(g.best)})` +
    (g.fuel_per_lap ? `, fuel ${g.fuel_per_lap.toFixed(3)} L/lap from ${g.fuel_laps} laps.` : `. ${g.note}`), g.fuel_per_lap ? "ok" : "");
});
$("#ep-src-export").addEventListener("click", async () => {
  const e = (await planSources()).export;
  if (!e) { msg($("#ep-src-msg"), "No imported session for this track – import a Garage 61 export on the Sessions tab.", "err"); return; }
  setIf("#ep-lap", e.lap_time, fmtTime); setIf("#ep-fpl", e.fuel_per_lap, (v) => v.toFixed(3));
  msg($("#ep-src-msg"), `Imported session ${esc((e.date || "").slice(0, 10))} (${esc(e.car)}): race pace ${fmtTime(e.lap_time)} from ${e.laps} laps` +
    (e.fuel_per_lap ? `, fuel ${e.fuel_per_lap.toFixed(3)} L/lap.` : "."), "ok");
});

// ------------------------------------------------------------ progress
async function initProgress() {
  const combos = await api("/api/progress/combos").catch(() => []);
  const sel = $("#pg-combo"), keep = sel.value;
  sel.innerHTML = combos.length ? combos.map((c, i) => `<option value="${i}">${esc(c.track)} · ${esc(c.car)} (${c.sessions} sessions)</option>`).join("")
    : '<option value="">No sessions yet – drive with SimCoach running</option>';
  state.combos = combos;
  if (keep) sel.value = keep;
  loadProgress();
}
$("#pg-combo").addEventListener("change", loadProgress);
async function loadProgress() {
  const c = (state.combos || [])[+$("#pg-combo").value];
  const q = c ? new URLSearchParams({ track: c.track, car: c.car }) : "";
  const p = await api("/api/progress?" + q).catch(() => null);
  if (!p || !p.sessions.length) { $("#pg-grades").innerHTML = ""; return; }
  const best = p.sessions.map((s) => s.best), pb = p.sessions.map((s) => s.pb_so_far);
  $("#pg-chart-note").classList.toggle("hidden", p.sessions.length > 1);
  Charts.line($("#c-pb"), [{ data: best, color: Charts.css("--me"), width: 2 }, { data: pb, color: Charts.css("--good"), width: 1 }],
    { fmt: (v) => fmtTime(v).slice(0, 6) });
  const keys = ["braking", "turn_in", "min_speed", "throttle", "line", "car_control"];
  $("#pg-grades").innerHTML = `<thead><tr><th>Session</th><th>Best</th>${keys.map((k) => `<th>${(GRADE_LABELS.find((g) => g[0] === k) || [k, k])[1]}</th>`).join("")}</tr></thead><tbody>` +
    p.sessions.slice().reverse().map((s) => `<tr><td>${s.date.slice(0, 4)}-${s.date.slice(4, 6)}-${s.date.slice(6, 8)}</td><td>${fmtTime(s.best)}</td>` +
      keys.map((k) => `<td>${s.grades[k] ?? "–"}</td>`).join("") + "</tr>").join("") + "</tbody>";
  $("#pg-recurring").innerHTML = p.recurring.map((r) => `<li><b>${esc(r.corner)}</b>: ${esc(r.issue)} <span class="muted">(${r.sessions} sessions)</span></li>`).join("") || '<li class="muted">Nothing repeats yet.</li>';
  $("#pg-improved").innerHTML = p.improved.map((r) => `<li><b>${esc(r.corner)}</b>: <span class="${r.gain > 0 ? "neg" : "pos"}">${r.gain > 0 ? "−" : "+"}${Math.abs(r.gain).toFixed(2)}s</span> per lap</li>`).join("") || '<li class="muted">Needs 2+ sessions.</li>';
}
$("#pg-plan").addEventListener("click", async () => {
  const c = (state.combos || [])[+$("#pg-combo").value];
  const q = new URLSearchParams({ minutes: $("#pg-min").value, ...(c ? { track: c.track, car: c.car } : {}) });
  const r = await api("/api/practice_plan?" + q);
  state.planSource = r.source;
  renderPlan(r.plan, r.note);
});

function renderPlan(plan, note) {
  const el = $("#pg-plan-out");
  if (!plan || !plan.length) { el.innerHTML = `<span class="muted">${esc(note || "No data yet.")}</span>`; return; }
  const done = plan.filter((p) => p.status === "done").length;
  el.innerHTML = `<p class="muted small-text">${state.planSource ? "Based on " + esc(state.planSource) + " · " : ""}${done}/${plan.length} done</p>` +
    plan.map((p, i) => `<div class="plan-step ${p.status || ""}"><b>${p.status === "done" ? "✓ " : ""}${i + 1}. ${esc(p.title)} <span class="muted">· ${p.minutes} min</span></b>${esc(p.detail)}
      <div class="actions">${p.drill ? `<button class="small primary" data-start="${i}">${p.status === "active" ? "Restart drill" : "Start drill"}</button>` : ""}
        ${p.consistency ? `<button class="small primary" data-start="${i}">${p.status === "active" ? "Restart" : "Start consistency run"}</button>` : ""}
        ${p.action === "optimal" ? `<button class="small primary" data-optimal="${i}">Build optimal lap &amp; use it</button>` : ""}
        ${p.status !== "done" ? `<button class="small" data-done="${i}">Mark done</button>` : ""}</div></div>`).join("");
}
$("#pg-plan-out").addEventListener("click", async (ev) => {
  const b = ev.target.closest("button"); if (!b) return;
  try {
    if (b.dataset.start !== undefined) {
      const r = await api(`/api/plan/${b.dataset.start}/start`, { method: "POST" });
      renderPlan(r.plan); msg($("#s-msg"), "");
      alert(r.step.consistency ? "Consistency run started – the target is set from your pace after 3 laps. Watch the streak on the overlay."
        : `Drill started: ${r.focus.drill} on ${r.focus.title}. Head out – the overlay and voice will coach this corner.`);
    } else if (b.dataset.optimal !== undefined) {
      await api("/api/optimal", { method: "POST", body: { include_teammates: true, set_reference: true } });
      const r = await api(`/api/plan/${b.dataset.optimal}/start`, { method: "POST" }); renderPlan(r.plan);
    } else if (b.dataset.done !== undefined) {
      const r = await api(`/api/plan/${b.dataset.done}/done`, { method: "POST" }); renderPlan(r.plan);
    }
  } catch (e) { alert(e.message); }
});
setInterval(async () => {                       // keep ticks in sync when a drill completes on track
  if (!$("#tab-progress").classList.contains("active")) return;
  try { const r = await api("/api/plan"); if (r.plan.length) renderPlan(r.plan); } catch { /* offline */ }
  loadGame();
}, 4000);

// ------------------------------------------------------------ training game
async function loadGame() {
  const el = $("#game-out");
  if (!el || (state.features && state.features.game === false)) return;
  try {
    const g = await api("/api/game");
    const html = SC.gameHeader(g) + `<div class="label" style="margin-top:12px">Badges ${g.badge_count}/${g.badges.length}</div>` + SC.badges(g) + SC.feed(g);
    if (el.dataset.html !== html) { el.innerHTML = html; el.dataset.html = html; }
    SC.toasts(g);
  } catch { /* switched off */ }
}

// ------------------------------------------------------------ teammate lap files
const tm = { upload: null };
function parseLapTime(s) {
  s = (s || "").trim(); if (!s) return null;
  const m = s.match(/^(?:(\d+):)?(\d+(?:\.\d+)?)$/);
  return m ? (+(m[1] || 0)) * 60 + parseFloat(m[2]) : NaN;
}
async function uploadLapFile(f) {
  const lt = parseLapTime($("#tm-laptime").value);
  if (Number.isNaN(lt)) { msg($("#tm-msg"), "Lap time format: 1:29.307", "err"); return; }
  msg($("#tm-msg"), `Reading ${f.name} (${(f.size / 1e6).toFixed(1)} MB)…`);
  $("#tm-laps").classList.add("hidden");
  try {
    const q = new URLSearchParams({ filename: f.name }); if (lt) q.set("lap_time", lt);
    const r = await fetch("/api/laps/upload?" + q, { method: "POST", body: f });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Upload failed");
    tm.upload = d;
    if (!$("#tm-name").value && d.info.driver) $("#tm-name").value = d.info.driver;
    const where = [d.info.track, d.info.car].filter(Boolean).join(" · ");
    msg($("#tm-msg"), `${d.laps.length} lap${d.laps.length === 1 ? "" : "s"} found${where ? " – " + where : ""}. Fastest clean lap first.`, "ok");
    $("#tm-laps tbody").innerHTML = d.laps.map((l, i) => `
      <tr><td>${l.number ?? i + 1}</td><td>${fmtTime(l.lap_time)}${i === 0 ? ' <span class="muted">fastest</span>' : ""}</td>
        <td>${l.valid ? "yes" : '<span class="muted">no (off-track / pits)</span>'}</td>
        <td><button class="small primary" data-i="${l.index}" data-ref="1">Use as my reference</button>
            <button class="small" data-i="${l.index}">Save only</button></td></tr>`).join("");
    $("#tm-laps").classList.remove("hidden");
  } catch (e) { msg($("#tm-msg"), e.message, "err"); }
}
$("#tm-file").addEventListener("change", (e) => { if (e.target.files[0]) uploadLapFile(e.target.files[0]); e.target.value = ""; });
const drop = $("#tm-drop");
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) uploadLapFile(f); });
$("#tm-laps").addEventListener("click", async (ev) => {
  const b = ev.target.closest("button"); if (!b || !tm.upload) return;
  try {
    const r = await api("/api/laps/import", { method: "POST", body: {
      upload_id: tm.upload.upload_id, index: +b.dataset.i, driver: $("#tm-name").value.trim() || null,
      set_reference: !!b.dataset.ref } });
    msg($("#tm-msg"), b.dataset.ref ? `"${r.label}" is now your live reference. Go drive!` : `Saved "${r.label}" to your laps.`, "ok");
    loadLocalLaps(); refreshReference();
  } catch (e) { msg($("#tm-msg"), e.message, "err"); }
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
  const gEl = $("#a-grades"), sc = c.scores || {};
  gEl.innerHTML = GRADE_LABELS.filter(([k]) => sc[k] !== null && sc[k] !== undefined).map(([k, l]) =>
    `<div class="grade"><span>${l}</span><div class="gbar"><div style="width:${sc[k]}%;background:${gradeColor(sc[k])}"></div></div><b>${sc[k]}</b></div>`).join("");

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
  const hasLine = !!(c.line && me.lat && ref.lat);
  $("#line-none").classList.toggle("hidden", hasLine);
  $("#line-rebuilt").classList.toggle("hidden", !(hasLine && ((me.meta || {}).line === "reconstructed" || (ref.meta || {}).line === "reconstructed")));
  $("#c-line").classList.toggle("hidden", !hasLine);
  $("#c-lines").parentElement.parentElement.classList.toggle("hidden", !hasLine);
  state.lineZoom = null;
  const drawLines = () => {
    if (!hasLine) return;
    Charts.line($("#c-line"), [{ data: c.line, color: Charts.css("--me"), width: 1.5 }],
      { n: 1000, regions, zeroLine: true, fmt: (v) => v.toFixed(1) });
    const z = state.lineZoom;
    Charts.trackLines($("#c-lines"), [{ lat: ref.lat, lon: ref.lon, color: Charts.css("--ref"), width: z ? 3 : 2 },
      { lat: me.lat, lon: me.lon, color: Charts.css("--me"), width: z ? 3 : 1.5 }],
      { range: z, labels: r.corners.map((k) => ({ i: k.apex, text: k.name })), scaleM: z ? 20 : 500 });
  };
  const drawAll = () => { draw(); drawLines(); };
  state.redrawAnalysis = drawAll;
  drawAll();
  renderCarControl(c);

  $("#corner-table tbody").innerHTML = c.corners.map((k) => `
    <tr><td><b>${esc(k.title || k.name)}</b></td>
      <td class="${k.time_lost > 0.02 ? "pos" : k.time_lost < -0.02 ? "neg" : ""}">${fmtDelta(k.time_lost)}s
        <div class="muted small-text">entry ${fmtDelta(k.entry_lost)} / exit ${fmtDelta(k.exit_lost)}</div></td>
      <td>${k.brake_point_m === null ? "–" : signed(state.units === "metric" ? k.brake_point_m : k.brake_point_m * 3.281, 0, state.units === "metric" ? " m" : " ft")}</td>
      <td>${k.turn_in_m === null || k.turn_in_m === undefined ? "–" : signed(state.units === "metric" ? k.turn_in_m : k.turn_in_m * 3.281, 0, state.units === "metric" ? " m" : " ft")}</td>
      <td>${k.line_apex_m == null ? "–" : (Math.abs(k.line_apex_m) < 0.5 ? "on line" : signed(state.units === "metric" ? k.line_apex_m : k.line_apex_m * 3.281, 1, state.units === "metric" ? " m" : " ft") + (k.line_apex_m > 0 ? " wide" : " tight"))}</td>
      <td>${signed(state.units === "metric" ? k.min_speed_diff_kmh : k.min_speed_diff_kmh / 1.609, 1, " " + spdUnit())}</td>
      <td>${signed(state.units === "metric" ? k.exit_speed_diff_kmh : k.exit_speed_diff_kmh / 1.609, 1, " " + spdUnit())}</td>
      <td>${k.throttle_point_m === null ? "–" : signed(state.units === "metric" ? k.throttle_point_m : k.throttle_point_m * 3.281, 0, state.units === "metric" ? " m" : " ft")}</td>
      <td>${carBadges(k)}</td>
      <td class="tips">${k.tips.map((t) => `<div>${esc(t)}</div>`).join("") || '<span class="muted">On pace</span>'}</td></tr>`).join("");
  $("#corner-table tbody").querySelectorAll("tr").forEach((tr, i) => tr.addEventListener("click", () => {
    const k = r.corners[i]; state.lineZoom = [k.start - 15, k.end + 15];
    if (state.redrawAnalysis) state.redrawAnalysis();
    $("#line-card").scrollIntoView({ behavior: "smooth", block: "start" });
  }));
}

function carBadges(k) {
  const b = [];
  if (k.oversteer_m >= 4) b.push(`<span class="badge bad">oversteer ${Math.round(k.oversteer_m)} m</span>`);
  if (k.understeer > 1.3) b.push(`<span class="badge warn">understeer</span>`);
  if (k.wheelspin_m_diff >= 6) b.push(`<span class="badge bad">wheelspin</span>`);
  if (k.abs_m_diff >= 10) b.push(`<span class="badge warn">ABS +${Math.round(k.abs_m_diff)} m</span>`);
  if (k.corrections_diff >= 3) b.push(`<span class="badge warn">+${k.corrections_diff} corrections</span>`);
  if (k.gear_apex_diff) b.push(`<span class="badge">gear ${k.gear_apex} (ref ${k.gear_apex_ref})</span>`);
  return b.join("") || (k.understeer == null && k.oversteer_m == null ? '<span class="muted">–</span>' : '<span class="badge good">clean</span>');
}

function renderCarControl(c) {
  const rows = [];
  const count = (f) => c.corners.filter(f).map((k) => k.title || k.name);
  const os = count((k) => k.oversteer_m >= 4), us = count((k) => k.understeer > 1.3),
    ws = count((k) => k.wheelspin_m_diff >= 6), ab = count((k) => k.abs_m_diff >= 10),
    busy = count((k) => k.corrections_diff >= 3);
  if (os.length) rows.push(`<li><b>Oversteer / slides:</b> ${os.map(esc).join(", ")}</li>`);
  if (us.length) rows.push(`<li><b>Understeer:</b> ${us.map(esc).join(", ")}</li>`);
  if (ws.length) rows.push(`<li><b>Wheelspin on exit:</b> ${ws.map(esc).join(", ")}</li>`);
  if (ab.length) rows.push(`<li><b>Heavy on ABS:</b> ${ab.map(esc).join(", ")}</li>`);
  if (busy.length) rows.push(`<li><b>Busy steering:</b> ${busy.map(esc).join(", ")}</li>`);
  if (c.shifts) {
    const d = c.shifts.diff_rpm;
    rows.push(`<li><b>Upshifts:</b> ${c.shifts.me_rpm} rpm (reference ${c.shifts.ref_rpm}) – ` +
      (Math.abs(d) < 200 ? "same shift points." : d < 0 ? `you short-shift by ~${-d} rpm${d < -400 ? " (fine when saving fuel)" : ""}.` : `you hold gears ~${d} rpm longer.`) + "</li>");
  }
  const wide = c.corners.filter((k) => k.line_apex_m > 1.5).map((k) => `${k.title || k.name} (+${k.line_apex_m.toFixed(1)} m)`);
  if (wide.length) rows.push(`<li><b>Wide at the apex:</b> ${wide.map(esc).join(", ")}</li>`);
  $("#cc-summary").innerHTML = rows.length ? `<ul class="tips-list">${rows.join("")}</ul>`
    : '<span class="muted">No car-control problems found' + (c.corners.some((k) => k.understeer != null || k.oversteer_m != null) ? "." : " (these laps have no yaw/RPM/ABS channels).") + "</span>";
}
window.addEventListener("resize", () => { if (state.redrawAnalysis) state.redrawAnalysis(); });

// ------------------------------------------------------------ sessions (G61 exports)
async function loadSessions(selectId) {
  const list = await api("/api/sessions").catch(() => []);
  const sel = $("#ss-list");
  sel.innerHTML = list.length ? list.map((x) =>
    `<option value="${esc(x.id)}">${esc((x.date || "").slice(0, 10))} · ${esc(x.track)} · ${esc(x.car)}</option>`).join("")
    : '<option value="">No sessions imported yet</option>';
  if (selectId) sel.value = selectId;
  if (sel.value) showSession(sel.value); else $("#ss-view").innerHTML = "";
}
$("#ss-list").addEventListener("change", (e) => showSession(e.target.value));

async function showSession(id) {
  try {
    const a = await api("/api/sessions/" + encodeURIComponent(id));
    let html = `<div class="summary">
      <div class="card stat"><div class="label">Car</div><div class="big" style="font-size:16px">${esc(a.car)}</div></div>
      <div class="card stat"><div class="label">Track</div><div class="big" style="font-size:16px">${esc(a.track)}</div></div>
      <div class="card stat"><div class="label">Theoretical best (all sessions)</div><div class="big">${fmtTime(a.theoretical_best)}</div></div>
      <div class="card stat"><div class="label">Driver</div><div class="big" style="font-size:16px">${esc(a.driver)}</div></div></div>`;
    a.sessions.forEach((s) => {
      html += `<div class="card"><div class="label">${esc(s.name)} · ${s.laps} laps · ${s.clean_laps} clean · ${s.used_laps || 0} used for analysis</div>`;
      if (s.note) { html += `<p class="muted">${esc(s.note)}</p>`; }
      else {
        html += `<div class="summary">
          <div class="card stat"><div class="label">Best lap</div><div class="big">${fmtTime(s.best_lap.lap_time)}</div><div class="muted">lap ${s.best_lap.lap}</div></div>
          <div class="card stat"><div class="label">Theoretical best</div><div class="big">${fmtTime(s.theoretical_best)}</div><div class="muted">${fmtDelta(s.theoretical_best - s.best_lap.lap_time)}s</div></div>
          <div class="card stat"><div class="label">Average lap</div><div class="big">${fmtTime(s.average_lap)}</div><div class="muted">±${s.stdev.toFixed(2)}s</div></div>
          <div class="card stat"><div class="label">Focus on</div><div class="big">${s.focus_sectors.length ? s.focus_sectors.map((x) => "S" + x).join(", ") : "–"}</div></div></div>`;
        if (s.tips.length) html += `<ul class="tips-list">${s.tips.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`;
        html += `<div class="label" style="margin-top:12px">Sectors – time left vs your best</div><table class="tbl"><thead><tr><th>Sector</th><th>Best</th><th>Average</th><th>Avg loss</th><th>Best lap loss</th><th>Spread</th></tr></thead><tbody>` +
          s.sectors.map((x) => `<tr><td>S${x.sector}</td><td>${x.best.toFixed(3)} <span class="muted">(lap ${x.best_lap})</span></td><td>${x.avg.toFixed(3)}</td>
            <td class="${x.avg_loss > 0.25 ? "pos" : ""}">+${x.avg_loss.toFixed(3)}</td><td>+${x.best_lap_loss.toFixed(3)}</td><td>±${x.spread.toFixed(3)}</td></tr>`).join("") + "</tbody></table>";
      }
      const best = s.best_sectors || [];
      html += `<div class="label" style="margin-top:12px">Laps (purple = best sector)</div><table class="tbl"><thead><tr><th>Lap</th><th>Time</th>` +
        Array.from({ length: s.sector_count }, (_, i) => `<th>S${i + 1}</th>`).join("") + `<th></th></tr></thead><tbody>` +
        s.lap_list.map((l) => `<tr class="${l.used ? "" : "unused"}"><td>${l.lap}</td><td>${fmtTime(l.lap_time)}</td>` +
          l.sectors.map((x, i) => `<td class="${l.used && x != null && x === best[i] ? "best" : ""}">${x == null ? "–" : x.toFixed(3)}</td>`).join("") +
          `<td class="muted small-text">${[l.pit_in ? "in-lap" : "", l.pit_out ? "out-lap" : "", l.clean ? "" : "not clean"].filter(Boolean).join(", ")}</td></tr>`).join("") +
        "</tbody></table></div>";
    });
    $("#ss-view").innerHTML = html;
  } catch (e) { msg($("#ss-msg"), e.message, "err"); }
}

$("#ss-file").addEventListener("change", async (e) => {
  const f = e.target.files[0]; if (!f) return;
  msg($("#ss-msg"), "Importing " + f.name + "…");
  try {
    const r = await fetch("/api/sessions/import?filename=" + encodeURIComponent(f.name), { method: "POST", body: f });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Import failed");
    msg($("#ss-msg"), "Imported.", "ok");
    loadSessions(d.id);
  } catch (err) { msg($("#ss-msg"), err.message, "err"); }
  e.target.value = "";
});
$("#ss-targets").addEventListener("click", async () => {
  const id = $("#ss-list").value; if (!id) return;
  try {
    const r = await api("/api/live/sector_targets", { method: "POST", body: { session_id: id } });
    msg($("#ss-msg"), "Live sector targets set: " + r.targets.map((x) => x.toFixed(3)).join(" / "), "ok");
  } catch (e) { msg($("#ss-msg"), e.message, "err"); }
});
$("#ss-delete").addEventListener("click", async () => {
  const id = $("#ss-list").value; if (!id || !confirm("Delete this imported session?")) return;
  await api("/api/sessions/" + encodeURIComponent(id), { method: "DELETE" });
  loadSessions();
});

// ------------------------------------------------------------ corners (names & numbers)
const cn = { data: null };
async function initCorners() {
  const sel = $("#cn-ref"), keep = sel.value;
  sel.innerHTML = "";
  const st = await api("/api/status");
  if (st.live.reference) addOption(sel, "live_ref", `Live reference (${st.live.reference})`);
  if (st.demo) addOption(sel, "demo:ref", "Demo – reference lap");
  addOption(sel, "session_best", "Session best");
  (await api("/api/local/laps").catch(() => [])).forEach((l) => addOption(sel, "local:" + l.file, `${l.label} – ${l.track || ""}`));
  (state.g61Laps || []).filter((l) => l.can_view_telemetry !== false)
    .forEach((l) => addOption(sel, "g61:" + l.id, `G61: ${l.driver} ${fmtTime(l.lap_time)} – ${l.track || ""}`));
  if (keep) sel.value = keep;
  if (!cn.data && sel.value) loadCorners();
}
$("#cn-load").addEventListener("click", loadCorners);
$("#cn-ref").addEventListener("change", loadCorners);

async function loadCorners() {
  const key = $("#cn-ref").value;
  if (!key) { msg($("#cn-msg"), "Pick a lap first (a reference lap on the track you want to label).", "err"); return; }
  msg($("#cn-msg"), "Loading…");
  try {
    cn.data = await api("/api/corners?ref=" + encodeURIComponent(key));
    $("#cn-track").value = cn.data.map_track || cn.data.track || "";
    msg($("#cn-msg"), cn.data.map_track ? `Using the saved corner map for "${cn.data.map_track}".`
      : `${cn.data.corners.length} corners found. Enter turn numbers/names and save.`, cn.data.map_track ? "ok" : "");
    renderCornerTable(); drawCornerViews();
  } catch (e) { msg($("#cn-msg"), e.message, "err"); }
}

function renderCornerTable() {
  const L = cn.data.lap.track_length;
  $("#cn-table tbody").innerHTML = cn.data.corners.map((c, i) => `
    <tr data-i="${i}"><td><b>C${c.index + 1}</b></td>
      <td>${L ? dist(c.distance_m) : (c.pct * 100).toFixed(1) + "%"}</td>
      <td>${state.units === "metric" ? c.min_speed_kmh + " km/h" : Math.round(c.min_speed_kmh / 1.609) + " mph"}</td>
      <td><input type="text" class="cn-num" value="${esc(c.number)}" placeholder="e.g. 1"></td>
      <td><input type="text" class="cn-name" value="${esc(c.label_name)}" placeholder="e.g. Tertre Rouge"></td></tr>`).join("");
  $("#cn-table").querySelectorAll("tr[data-i]").forEach((tr) => {
    tr.addEventListener("focusin", () => { cn.hl = +tr.dataset.i; drawCornerViews(); });
  });
}

function cornerLabel(c, i) {
  const tr = $("#cn-table").querySelector(`tr[data-i="${i}"]`);
  const num = tr ? tr.querySelector(".cn-num").value.trim() : c.number;
  return num ? "T" + num : "C" + (c.index + 1);
}

function drawCornerViews() {
  const d = cn.data; if (!d) return;
  const lap = d.lap;
  const hl = cn.hl;
  const hasMap = !!(lap.lat && lap.lon);
  $("#cn-map").classList.toggle("hidden", !hasMap);
  $("#cn-nomap").classList.toggle("hidden", hasMap);
  if (hasMap) {
    Charts.trackMap($("#cn-map"), lap.lat, lap.lon, lap.speed.map(() => 0),
      { labels: d.corners.map((c, i) => ({ i: c.apex, text: cornerLabel(c, i) })), marker: hl !== undefined ? d.corners[hl].apex : undefined });
  }
  Charts.line($("#cn-speed"), [{ data: lap.speed.map(spd), color: Charts.css("--ref") }], {
    n: lap.speed.length, ymin: 0,
    regions: d.corners.map((c, i) => ({ start: c.start, end: c.end, apex: c.apex, label: cornerLabel(c, i) })),
    cursor: hl !== undefined ? d.corners[hl].apex / lap.speed.length : undefined,
  });
}
$("#cn-table").addEventListener("input", () => drawCornerViews());

function collectCorners() {
  return cn.data.corners.map((c, i) => {
    const tr = $("#cn-table").querySelector(`tr[data-i="${i}"]`);
    return { pct: c.pct, number: tr.querySelector(".cn-num").value.trim(), name: tr.querySelector(".cn-name").value.trim() };
  }).filter((c) => c.number || c.name);
}

$("#cn-save").addEventListener("click", async () => {
  if (!cn.data) return;
  const track = $("#cn-track").value.trim();
  if (!track) { msg($("#cn-msg"), "Enter the track name.", "err"); return; }
  try {
    const r = await api("/api/corners", { method: "POST", body: { track, corners: collectCorners() } });
    msg($("#cn-msg"), `Saved ${r.corners.length} named corners for "${r.track}". They're live in the overlay, voice and reports.`, "ok");
    refreshReference();
  } catch (e) { msg($("#cn-msg"), e.message, "err"); }
});
$("#cn-export").addEventListener("click", () => {
  const track = $("#cn-track").value.trim();
  if (track) window.location = "/api/corners/export?track=" + encodeURIComponent(track);
});
$("#cn-import").addEventListener("change", async (e) => {
  const f = e.target.files[0]; if (!f) return;
  try {
    const data = JSON.parse(await f.text());
    const body = { track: data.track || $("#cn-track").value.trim(), corners: data.corners || [] };
    const r = await api("/api/corners/import", { method: "POST", body });
    msg($("#cn-msg"), `Imported ${r.corners.length} corners for "${r.track}".`, "ok");
    if (cn.data) loadCorners();
  } catch (err) { msg($("#cn-msg"), "Import failed: " + err.message, "err"); }
  e.target.value = "";
});

// ------------------------------------------------------------ settings
async function loadSettings() {
  const c = await api("/api/config");
  $("#s-token").value = "";
  $("#s-token-hint").textContent = c.has_token ? `Saved token: ${c.token_hint || "set"}` : "No token saved yet.";
  $("#s-units").value = c.units;
  $("#s-following").checked = c.include_following;
  $("#s-record").checked = c.record_laps;
  $("#s-extra").value = (c.extra_drivers || []).join(", ");
  $("#s-overlay").value = c.overlay_mode || "practice";
  $("#s-opacity").value = c.overlay_opacity || 0.85;
  $("#s-voice").value = c.voice_mode || "full";
  $("#s-update").value = c.update_mode || "auto";
  $("#s-lan").checked = !!c.lan_access;
  $("#s-race-mode").checked = c.race_mode !== false;
  loadFeatureToggles();
  refreshLan();
  refreshUpdate();
  $("#s-autostart").checked = !!c.start_with_windows;
  $("#s-autostart-row").classList.toggle("hidden", !c.autostart_supported);
  $("#s-voice-native").checked = c.voice_native !== false;
  $("#s-voice-practice").checked = c.voice_practice_only !== false;
  $("#s-focus-target").value = (c.focus_target ?? 0.05).toFixed(2);
}
$("#btn-save").addEventListener("click", async () => {
  const body = {
    units: $("#s-units").value, include_following: $("#s-following").checked,
    record_laps: $("#s-record").checked, extra_drivers: $("#s-extra").value.split(","),
    overlay_mode: $("#s-overlay").value, overlay_opacity: parseFloat($("#s-opacity").value),
    voice_mode: $("#s-voice").value, voice_native: $("#s-voice-native").checked,
    voice_practice_only: $("#s-voice-practice").checked,
    update_mode: $("#s-update").value,
    lan_access: $("#s-lan").checked,
    race_mode: $("#s-race-mode").checked,
    ...(document.querySelector("#s-autostart-row").classList.contains("hidden") ? {} : { start_with_windows: $("#s-autostart").checked }),
    focus_target: parseFloat($("#s-focus-target").value) || 0.05,
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
$("#btn-voice-test").addEventListener("click", async () => {
  try { const r = await api("/api/voice/test", { method: "POST" });
    msg($("#s-msg"), r.backend === "unavailable" ? "Windows voice not available – use the browser overlay with ?voice=1." : "Speaking…", "ok"); }
  catch (e) { msg($("#s-msg"), e.message, "err"); }
});
// ------------------------------------------------------------ tablet / phone (LAN + QR)
async function refreshLan() {
  let l; try { l = await api("/api/lan"); } catch { return; }
  $("#lan-box").classList.toggle("hidden", !(l.enabled || l.active));
  $("#lan-restart").classList.toggle("hidden", !l.needs_restart || l.viewer_is_remote);
  $("#lan-ready").classList.toggle("hidden", !l.active || !l.urls.length);
  if (l.active && l.urls.length) {
    const sel = $("#lan-url"), keep = sel.value;
    sel.innerHTML = l.urls.map((u) => `<option>${esc(u)}</option>`).join("");
    if (keep && l.urls.includes(keep)) sel.value = keep;
    setQr();
  }
  if (l.viewer_is_remote) { $("#s-lan").disabled = true; $("#btn-save").disabled = true; }
}
function setQr() {
  const u = $("#lan-url").value + ($("#lan-target").value || "");
  $("#lan-qr").src = "/api/lan/qr.svg?url=" + encodeURIComponent(u);
}
$("#lan-url").addEventListener("change", setQr);
$("#lan-target").addEventListener("change", setQr);
$("#s-lan").addEventListener("change", async () => {
  try { await api("/api/config", { method: "POST", body: { lan_access: $("#s-lan").checked } }); } catch (e) { msg($("#s-msg"), e.message, "err"); }
  refreshLan();
});
$("#btn-restart").addEventListener("click", async () => {
  $("#btn-restart").disabled = true; $("#lan-restart").firstChild.textContent = "Restarting… ";
  try { await api("/api/restart", { method: "POST" }); } catch { /* closing */ }
  for (let i = 0; i < 40; i++) {
    await new Promise((r) => setTimeout(r, 1000));
    try { const l = await api("/api/lan"); if (!l.needs_restart) { showTab("settings"); return; } } catch { /* restarting */ }
  }
  msg($("#s-msg"), "Couldn't restart automatically – quit SimCoach from the tray and start it again.", "err");
});

// ------------------------------------------------------------ weekly goal & streak
const fmtGoal = (v, t) => t === "minutes" ? (v >= 60 ? `${Math.floor(v / 60)}h ${String(Math.round(v % 60)).padStart(2, "0")}m` : `${Math.round(v)} min`) : `${Math.round(v)} ${t}`;
async function loadGoal() {
  if (state.features && state.features.goals === false) return;
  let g; try { g = await api("/api/goals"); } catch { return; }
  state.goal = g;
  $("#wg-chip").textContent = `Week ${fmtGoal(g.this_week, g.goal_type)} / ${fmtGoal(g.goal_value, g.goal_type)}` + (g.streak ? ` · streak ${g.streak}` : "");
  $("#wg-chip").className = "badge " + (g.met ? "good" : "");
  const st = $("#wg-status"); if (!st) return;
  st.innerHTML = `<div><span class="wg-big">${fmtGoal(g.this_week, g.goal_type)}</span> <span class="muted">of ${fmtGoal(g.goal_value, g.goal_type)} this week</span></div>
    <div class="wg-bar"><div style="width:${Math.round(g.progress * 100)}%"></div></div>
    <div>${g.met ? "<b class='neg'>Goal met this week ✓</b>" : `${fmtGoal(g.remaining, g.goal_type)} to go · ${g.days_left} day${g.days_left === 1 ? "" : "s"} left`}</div>
    <div style="margin-top:6px"><span class="streak-flame">Streak: ${g.streak} week${g.streak === 1 ? "" : "s"}</span> <span class="muted">· best ${g.best_streak}</span></div>`;
  if (document.activeElement !== $("#wg-value")) { $("#wg-value").value = g.goal_value; $("#wg-type").value = g.goal_type; }
  const vals = g.weeks.map((w) => w.value);
  Charts.line($("#wg-chart"), [{ data: vals, color: Charts.css("--me"), width: 2 },
    { data: g.weeks.map(() => g.goal_value), color: Charts.css("--good"), width: 1 }],
    { ymin: 0, ymax: Math.max(g.goal_value, ...vals) * 1.15, fmt: (v) => g.goal_type === "minutes" ? (v / 60).toFixed(1) + "h" : v.toFixed(0) });
}
$("#wg-save").addEventListener("click", async () => {
  const v = parseFloat($("#wg-value").value);
  if (!(v > 0)) { alert("Enter a goal, e.g. 180 (minutes), 3 (sessions) or 60 (laps)"); return; }
  try { await api("/api/config", { method: "POST", body: { goal_type: $("#wg-type").value, goal_value: v } }); loadGoal(); }
  catch (e) { alert(e.message); }
});
$("#wg-type").addEventListener("change", (e) => { $("#wg-value").value = { minutes: 180, sessions: 3, laps: 60 }[e.target.value]; });
setInterval(loadGoal, 60000);

// ------------------------------------------------------------ training features on/off
function applyFeatures(f) {
  if (!f) return;
  const key = JSON.stringify(f);
  if (state.featKey === key) return;
  state.featKey = key; state.features = f;
  document.querySelectorAll("[data-feature]").forEach((el) => el.classList.toggle("feature-off", f[el.dataset.feature] === false));
  const active = document.querySelector(".tab.active");
  if (active && active.classList.contains("feature-off")) showTab("live");
}
async function loadFeatureToggles() {
  const r = await api("/api/features").catch(() => null); if (!r) return;
  $("#s-features").innerHTML = Object.entries(r.labels).map(([k, l]) =>
    `<label class="check"><input type="checkbox" data-feat="${k}" ${r.features[k] !== false ? "checked" : ""}> ${esc(l)}</label>`).join("");
}
$("#s-features").addEventListener("change", async (e) => {
  const k = e.target.dataset.feat; if (!k) return;
  try { const c = await api("/api/config", { method: "POST", body: { features: { [k]: e.target.checked } } }); applyFeatures(c.features); }
  catch (err) { msg($("#s-msg"), err.message, "err"); }
});

// ------------------------------------------------------------ consistency trainer
function renderConsistency(c) {
  const el = $("#ct-status");
  const key = JSON.stringify(c);
  if (el.dataset.k === key) return;
  el.dataset.k = key;
  if (!c.active) {
    el.innerHTML = '<span class="muted">Off. Leave the target empty and the trainer sets it from your pace after 3 laps.</span>' +
      (c.laps ? `<div class="muted small-text">Last run: ${c.inside}/${c.laps} laps inside, best streak ${c.best_streak}${c.score != null ? ", score " + c.score : ""}</div>` : "");
    return;
  }
  el.innerHTML = `<div><span class="ct-big">${c.streak}</span><span class="muted"> / ${c.goal} in a row</span>
      ${c.score != null ? `<span class="badge ${c.score >= 80 ? "good" : c.score >= 60 ? "warn" : "bad"}" style="margin-left:10px">score ${c.score}</span>` : ""}</div>
    <div>${c.target ? `Target <b>${fmtTime(c.target)}</b> ±${c.window.toFixed(2)}s` : "Setting the target from your next laps…"}
      · best streak ${c.best_streak} · ${c.inside}/${c.laps} inside${c.stdev != null ? ` · ±${c.stdev.toFixed(2)}s spread` : ""}</div>
    <div style="margin-top:4px">${esc(c.message || "")}</div>
    <ul class="ct-laps">${(c.recent || []).slice().reverse().map((l) => l.inside == null ? `<li class="muted">${fmtTime(l.lap_time)} (setting target)</li>` :
      `<li><span class="sev ${l.inside ? "good" : "bad"}"></span>${fmtTime(l.lap_time)} <b class="${l.inside ? "neg" : "pos"}">${fmtDelta(l.delta)}</b> ${l.why ? "– " + esc(l.why) : ""}</li>`).join("")}</ul>`;
  drawConsistencyMap();
}
async function drawConsistencyMap() {
  const ref = state.ref; if (!ref || !ref.lat) return;
  let r; try { r = await api("/api/coach/report"); } catch { return; }
  if (!r.corners || !r.corners.length) return;
  // colour relative to your typical corner: green = steadier than usual, red = varies more
  const spreads = r.corners.map((c) => c.spread || 0).sort((x, y) => x - y);
  const median = spreads[Math.floor(spreads.length / 2)] || 0;
  const vals = new Array(ref.lat.length).fill(0);
  r.corners.forEach((c) => { const k = state.refCorners[c.index]; if (!k) return; for (let i = k.start; i <= k.end; i++) vals[i] = (c.spread || 0) - median; });
  Charts.trackMap($("#ct-map"), ref.lat, ref.lon, vals, { labels: state.refCorners.map((k) => ({ i: k.apex, text: k.name })) });
}
$("#ct-start").addEventListener("click", async () => {
  const t = parseLapTime($("#ct-target").value);
  if (Number.isNaN(t)) { alert("Target format: 1:29.500 (or leave empty)"); return; }
  try { await api("/api/consistency/start", { method: "POST", body: { target: t, window: parseFloat($("#ct-window").value), goal: parseInt($("#ct-goal").value, 10) } }); }
  catch (e) { alert(e.message); }
});
$("#ct-stop").addEventListener("click", () => api("/api/consistency/stop", { method: "POST" }));

// ------------------------------------------------------------ demo mode
$("#demo-exit").addEventListener("click", async () => {
  $("#demo-exit").disabled = true;
  $("#demo-banner span").textContent = "Restarting SimCoach in live mode…";
  try { await api("/api/exit_demo", { method: "POST" }); } catch { /* the old instance may close mid-request */ }
  for (let i = 0; i < 60; i++) {                       // wait for the live instance, then reload
    await new Promise((r) => setTimeout(r, 1000));
    try { const st = await api("/api/status"); if (!st.demo) { location.reload(); return; } } catch { /* restarting */ }
  }
  $("#demo-banner span").textContent = "Couldn't restart automatically – quit SimCoach from the tray and start it again.";
});

// ------------------------------------------------------------ updates
function describeUpdate(u) {
  const when = u.checked_at ? " · checked " + new Date(u.checked_at * 1000).toLocaleTimeString() : "";
  switch (u.status) {
    case "up_to_date": return `You're on the latest version (v${u.current})${when}` + (u.error ? ` – ${u.error}` : "");
    case "checking": return "Checking for updates…";
    case "available": return `Version ${u.latest} is available.`;
    case "downloading": return `Downloading ${u.latest}… ${Math.round((u.progress || 0) * 100)}%`;
    case "ready": return `Version ${u.latest} is downloaded and verified.` + (u.can_install ? "" : " (Install manually – automatic install only works in the installed app.)");
    case "installing": return `Installing ${u.latest} – SimCoach will restart in a moment…`;
    case "error": return `Update problem: ${u.error}`;
    case "disabled": return "Updates are disabled in this mode.";
    default: return `v${u.current}`;
  }
}
let updateDismissed = null;
async function refreshUpdate() {
  let u; try { u = await api("/api/update"); } catch { return; }
  $("#update-status").textContent = describeUpdate(u);
  const show = (u.status === "ready" || u.status === "installing") && updateDismissed !== u.latest;
  $("#update-banner").classList.toggle("hidden", !show);
  if (show) {
    $("#update-text").textContent = u.status === "installing" ? describeUpdate(u)
      : `SimCoach ${u.latest} is ready to install (you have ${u.current}).`;
    $("#update-install").classList.toggle("hidden", u.status !== "ready" || !u.can_install);
  }
}
$("#update-install").addEventListener("click", async () => {
  try { await api("/api/update/install", { method: "POST" }); refreshUpdate(); } catch (e) { alert(e.message); }
});
$("#update-later").addEventListener("click", async () => {
  const u = await api("/api/update"); updateDismissed = u.latest; $("#update-banner").classList.add("hidden");
});
$("#btn-update-check").addEventListener("click", async () => {
  $("#update-status").textContent = "Checking for updates…";
  try { const u = await api("/api/update/check", { method: "POST" }); $("#update-status").textContent = describeUpdate(u); refreshUpdate(); }
  catch (e) { $("#update-status").textContent = e.message; }
});
setInterval(refreshUpdate, 30000);

function applyUnits() { document.querySelectorAll('[data-unit="speed"]').forEach((e) => (e.textContent = spdUnit())); }

// ------------------------------------------------------------ boot
(async function boot() {
  try {
    const st = await api("/api/status");
    state.units = st.config.units; applyUnits();
    $("#ver").textContent = "v" + st.version;
    $("#demo-banner").classList.toggle("hidden", !st.demo);
    if (!st.config.has_token && !st.demo) showTab("settings");
  } catch { /* server not up yet */ }
  await refreshReference().catch(() => {});
  refreshUpdate();
  loadGoal();
  connectWS();
})();

// ------------------------------------------------------------ race reports
async function loadRaceReports() {
  const sel = $("#rr-list"); if (!sel) return;
  const list = await api("/api/race_reports").catch(() => []);
  sel.innerHTML = `<option value="">Latest race</option>` + list.map((r) =>
    `<option value="${esc(r.id)}">${esc((r.date || "").replace("T", " "))} · ${esc(r.track || "")}${r.finish ? " · P" + r.finish.pos : ""}</option>`).join("");
}
$("#rr-list") && $("#rr-list").addEventListener("change", (e) => {
  $("#rr-open").href = "/race-report" + (e.target.value ? "?id=" + encodeURIComponent(e.target.value) : "");
});
