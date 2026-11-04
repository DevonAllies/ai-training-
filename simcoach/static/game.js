// Training game rendering shared by /train, /widget/plan and the dashboard.
(function () {
  const SC = (window.SC = window.SC || {});
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  SC.esc = esc;
  SC.fmtT = (s) => {
    if (s == null || !isFinite(s)) return "–";
    const m = Math.floor(s / 60), r = s - m * 60;
    return m ? `${m}:${r.toFixed(3).padStart(6, "0")}` : r.toFixed(3);
  };
  SC.api = async (path, body) => {
    const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || r.statusText);
    return j;
  };

  const STEP_XP = 40, PLAN_XP = 150;

  // ---- level / combo / daily header
  SC.gameHeader = (g) => {
    if (!g) return "";
    const d = g.daily || {};
    return `<div class="g-level"><div class="g-badge">${g.level}</div><div class="grow" style="flex:1;min-width:0">
        <div class="g-title">${esc(g.title)} <span class="g-sub">· ${g.xp} XP${g.session_xp ? ` · +${g.session_xp} today` : ""}</span></div>
        <div class="g-bar"><i style="width:${g.pct}%"></i></div>
        <div class="g-sub">${g.into} / ${g.need} XP to level ${g.level + 1}</div></div></div>
      <div class="g-row">
        <div class="g-tile g-combo ${g.combo >= 3 ? "hot" : ""}"><div class="k">Combo</div><div class="v">${g.combo}${g.mult > 1 ? ` <small>x${g.mult}</small>` : ""}</div><div class="g-sub">best ${g.best_combo}</div></div>
        <div class="g-tile" style="flex:2 1 200px"><div class="k">Daily challenge ${d.done ? "✓" : `· +${d.xp} XP`}</div>
          <div style="font-weight:600;margin-top:2px">${esc(d.text)}</div>
          <div class="g-bar ${d.done ? "good" : "gold"}"><i style="width:${Math.round(100 * (d.count || 0) / (d.goal || 1))}%"></i></div>
          <div class="g-sub">${d.count || 0} / ${d.goal}</div></div>
      </div>`;
  };

  // ---- the practice plan as a quest path
  SC.questPath = (st, opts = {}) => {
    const plan = st.plan || [];
    if (!plan.length) return `<p class="g-sub">No plan yet. ${opts.noPlanHint || "Start “Practice plan” to build one from your last session."}</p>`;
    const f = st.focus || {}, c = st.consistency || {};
    const rows = plan.map((p, i) => {
      const last = i === plan.length - 1;
      let detail = "";
      if (p.status === "active") {
        if (p.drill && f.active) {
          const pips = Array.from({ length: f.needed || 3 }, (_, k) => `<i class="${k < (f.streak || 0) ? "ok" : ""}"></i>`).join("");
          const res = (f.results || []).slice(-8).map((r) => `<i class="${r.ok ? "ok" : "no"}" title="${esc(r.text)}"></i>`).join("");
          detail = `<div class="g-qmsg">${esc(f.message || f.how || "")}</div>
            <div class="g-pips" title="on target in a row">${pips}</div>${res ? `<div class="g-pips" title="last attempts">${res}</div>` : ""}`;
        } else if (p.consistency && c.active) {
          const pips = Array.from({ length: c.goal || 5 }, (_, k) => `<i class="${k < (c.streak || 0) ? "ok" : ""}"></i>`).join("");
          detail = `<div class="g-qmsg">${esc(c.message || "")}</div><div class="g-pips">${pips}</div>`;
        } else {
          detail = `<div class="g-qmsg">${esc(p.detail || p.why || "")}</div>`;
        }
      }
      const node = p.status === "done" ? "✓" : last ? "★" : i + 1;
      const btn = opts.controls && p.status !== "done" && p.status !== "active"
        ? `<button class="small" data-quest="${i}">${p.status === "skipped" ? "Retry" : "Start"}</button>` : "";
      const doneBtn = opts.controls && p.status === "active" && !p.drill && !p.consistency
        ? `<button class="small" data-quest-done="${i}">Done</button>` : "";
      return `<li class="${p.status} ${last ? "boss" : ""}"><div class="g-node">${node}</div><div class="g-qbody">
          <div style="display:flex;gap:8px;justify-content:space-between;align-items:baseline">
            <span class="g-qtitle">${esc(p.title)}</span><span class="g-qxp">${p.minutes ? p.minutes + " min · " : ""}+${STEP_XP}${last ? `+${PLAN_XP}` : ""} XP</span></div>
          ${detail}${btn || doneBtn ? `<div style="margin-top:6px;display:flex;gap:6px">${btn}${doneBtn}</div>` : ""}</div></li>`;
    }).join("");
    const done = plan.filter((p) => p.status === "done").length;
    return `<div class="g-sub" style="margin-top:12px">Quest ${Math.min(done + 1, plan.length)} of ${plan.length} · ${done} cleared</div>
      <div class="g-bar good"><i style="width:${Math.round((100 * done) / plan.length)}%"></i></div><ol class="g-quests">${rows}</ol>`;
  };

  SC.badges = (g) => !g ? "" : `<div class="g-badges">${g.badges.map((b) =>
    `<span class="${b.earned ? "on" : ""}" title="${esc(b.how)}${b.earned ? " · " + b.earned : ""}">${b.earned ? "★ " : ""}${esc(b.name)}</span>`).join("")}</div>`;

  SC.feed = (g) => !g || !g.feed.length ? "" : `<div class="g-feed">${g.feed.slice().reverse().slice(0, 5).map((e) =>
    `<div><span>${esc(e.text)}</span>${e.xp ? `<b>+${e.xp}</b>` : ""}</div>`).join("")}</div>`;

  // ---- pop-up toasts for new XP / level / badges
  let lastT = null;
  SC.toasts = (g) => {
    if (!g) return;
    const items = g.feed || [];
    if (lastT === null) { lastT = items.length ? items[items.length - 1].t : 0; return; }
    let box = document.querySelector(".g-toasts");
    if (!box) { box = document.createElement("div"); box.className = "g-toasts"; document.body.appendChild(box); }
    items.filter((e) => e.t > lastT).slice(-3).forEach((e) => {
      const el = document.createElement("div");
      el.className = "g-toast " + (e.kind || "");
      el.innerHTML = `${esc(e.text)}${e.xp ? `<b>+${e.xp} XP</b>` : ""}`;
      box.appendChild(el);
      setTimeout(() => el.remove(), 2700);
    });
    if (items.length) lastT = Math.max(lastT, items[items.length - 1].t);
  };

  // Clicks on quest buttons (event delegation; call once per container).
  SC.bindQuests = (root, after) => {
    root.addEventListener("click", async (ev) => {
      const s = ev.target.closest("[data-quest]"), d = ev.target.closest("[data-quest-done]");
      try {
        if (s) await SC.api("/api/training/select", { mode: "plan", step: +s.dataset.quest });
        else if (d) await SC.api(`/api/plan/${+d.dataset.questDone}/done`, {});
        else return;
        after && after();
      } catch (e) { after && after(e); }
    });
  };
})();
