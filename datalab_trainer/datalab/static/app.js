/* DataLab Trainer front end: a small single-page app, no frameworks, works offline. */
(function () {
  "use strict";
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
  const esc = Markdown.esc;
  const main = $("#main");
  const LANG = { sql: "SQL", python: "Python", r: "R" };
  const svg = (d) => `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  const STAGE_ICON = {
    import: svg('<path d="M12 3v12M7 10l5 5 5-5M4 19h16"/>'),
    clean: svg('<path d="M3 21l9-9M14 4l6 6-5 5-6-6z"/>'),
    eda: svg('<path d="M4 20V4M4 20h16M8 16v-5M12 16V8M16 16v-3"/>'),
    model: svg('<path d="M4 18c4 0 4-12 8-12s4 12 8 12"/><circle cx="12" cy="6" r="1"/>'),
    explain: svg('<path d="M12 3l2.5 5.5L20 9l-4 4 1 6-5-3-5 3 1-6-4-4 5.5-.5z"/>'),
    report: svg('<path d="M6 3h9l4 4v14H6z"/><path d="M9 12h7M9 16h7M9 8h3"/>'),
    basics: svg('<path d="M4 5h6a2 2 0 0 1 2 2v12a2 2 0 0 0-2-2H4zM20 5h-6a2 2 0 0 0-2 2v12a2 2 0 0 1 2-2h6z"/>'),
    visualise: svg('<circle cx="12" cy="12" r="8"/><path d="M12 4v8l6 5"/>'),
    stats: svg('<path d="M3 20c3 0 4-14 9-14s6 14 9 14"/><path d="M12 6v14"/>'),
    forecast: svg('<path d="M3 17l5-5 4 3 4-6"/><path d="M16 9l5-4" stroke-dasharray="2 2"/><path d="M3 21h18"/>'),
  };
  let overview = null;

  // ------------------------------------------------------------------ helpers
  async function api(path, body) {
    const opt = body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json", "X-DataLab": "1" }, body: JSON.stringify(body),
    };
    const r = await fetch(path, opt);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || r.statusText);
    return data;
  }
  function toast(msg, kind = "") {
    const t = $("#toast");
    t.textContent = msg;
    t.className = "show " + kind;
    clearTimeout(t._h);
    t._h = setTimeout(() => (t.className = ""), 2600);
  }
  const store = {
    get(k, d) { try { const v = localStorage.getItem("dl-" + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("dl-" + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  function debounce(fn, ms) { let h; return (...a) => { clearTimeout(h); h = setTimeout(() => fn(...a), ms); }; }
  function h(html) { const d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstElementChild; }

  async function refreshOverview() {
    overview = await api("/api/overview");
    renderNav();
    return overview;
  }
  function stageStats(sid) {
    const ex = overview.exercises.filter(e => e.stage === sid);
    return { done: ex.filter(e => e.passed).length, total: ex.length };
  }

  // ------------------------------------------------------------------ markdown enhancements
  function enhance(el) {
    const pref = store.get("lang", "python");
    $$(".langtabs", el).forEach(box => {
      const show = (lang) => {
        const has = $$(".pane", box).some(p => p.dataset.lang === lang);
        const l = has ? lang : $(".pane", box).dataset.lang;
        $$(".pane", box).forEach(p => p.hidden = p.dataset.lang !== l);
        $$(".tab", box).forEach(t => t.classList.toggle("on", t.dataset.lang === l));
      };
      show(pref);
      $$(".tab", box).forEach(t => t.addEventListener("click", () => {
        store.set("lang", t.dataset.lang);
        $$(".langtabs", el).forEach(b => b._show && b._show(t.dataset.lang));
      }));
      box._show = show;
    });
    $$("button.copy", el).forEach(b => b.addEventListener("click", () => {
      const wrap = b.closest(".langtabs, .codewrap");
      const pre = wrap.classList.contains("langtabs") ? $(".pane:not([hidden]) code", wrap) : $("code", wrap);
      navigator.clipboard && navigator.clipboard.writeText(pre.textContent).then(() => toast("Copied"));
    }));
  }
  function md(text) { const d = document.createElement("div"); d.className = "md"; d.innerHTML = Markdown.render(text); enhance(d); return d; }

  // ------------------------------------------------------------------ navigation
  function renderNav() {
    $("#navStages").innerHTML = overview.stages.map(s => {
      const st = stageStats(s.id);
      const pct = st.total ? Math.round(100 * st.done / st.total) : 0;
      return `<a href="#/stage/${s.id}" data-nav="stage-${s.id}"><span class="num">${s.order}</span>${esc(s.title)}
        <span class="mini"><span style="width:${pct}%"></span></span></a>`;
    }).join("");
    markNav();
  }
  function markNav() {
    const key = currentNavKey();
    $$("#side a[data-nav]").forEach(a => a.classList.toggle("active", a.dataset.nav === key));
  }
  function currentNavKey() {
    const r = location.hash.replace(/^#\/?/, "").split("/");
    if (!r[0]) return "home";
    if (r[0] === "stage") return "stage-" + r[1];
    if (r[0] === "ex") { const e = overview && overview.exercises.find(x => x.id === r[1]); return e ? "stage-" + e.stage : ""; }
    return r[0];
  }
  $("#menuToggle").addEventListener("click", () => $("#side").classList.toggle("open"));

  async function route() {
    $("#side").classList.remove("open");
    const r = location.hash.replace(/^#\/?/, "").split("/");
    if (!overview) await refreshOverview();
    markNav();
    window.scrollTo(0, 0);
    try {
      if (!r[0]) return home();
      if (r[0] === "stage") return stage(r[1], r[2] || "lesson");
      if (r[0] === "ex") return exercise(r[1]);
      if (r[0] === "playground") return playground(r[1]);
      if (r[0] === "data") return datasets(r[1]);
      if (r[0] === "project") return project();
      if (r[0] === "report") return report();
      if (r[0] === "setup") return setup();
      main.innerHTML = `<div class="page"><h1>Not found</h1></div>`;
    } catch (e) {
      main.innerHTML = `<div class="page"><h1>Something went wrong</h1><pre class="err">${esc(String(e))}</pre></div>`;
    }
  }
  window.addEventListener("hashchange", route);

  // ------------------------------------------------------------------ dashboard
  function nextExercise() {
    // Skip the optional Module 0 for learners who have already started the main modules
    const started = overview.exercises.some(e => e.passed && e.stage !== "basics");
    const pool = overview.exercises.filter(e => !(started && e.stage === "basics"));
    return pool.find(e => !e.passed && e.level === 1) || pool.find(e => !e.passed) || overview.exercises.find(e => !e.passed);
  }
  function home() {
    const total = overview.exercises.length;
    const done = overview.exercises.filter(e => e.passed).length;
    const nx = nextExercise();
    const pipeline = overview.stages.map(s => {
      const st = stageStats(s.id);
      const q = overview.quiz[s.id];
      return `<a class="stagecard" href="#/stage/${s.id}">
        <div class="si">${STAGE_ICON[s.id] || "•"}</div>
        <div class="sn">Module ${s.order}</div><div class="st">${esc(s.title)}</div>
        <div class="ss">${esc(s.summary)}</div>
        <div class="bar"><span style="width:${st.total ? 100 * st.done / st.total : 0}%"></span></div>
        <div class="sm">${st.done}/${st.total} exercises${q ? ` · quiz ${q.best}/${q.total}` : ""}</div></a>`;
    }).join("");
    const langs = ["sql", "python", "r"];
    const matrix = `<table class="matrix"><thead><tr><th></th>${langs.map(l => `<th>${LANG[l]}</th>`).join("")}</tr></thead><tbody>` +
      overview.stages.map(s => `<tr><th><a href="#/stage/${s.id}/exercises">${esc(s.title)}</a></th>` + langs.map(l => {
        const ex = overview.exercises.filter(e => e.stage === s.id && e.lang === l);
        const d = ex.filter(e => e.passed).length;
        const cls = d === ex.length && ex.length ? "full" : d ? "part" : "";
        return `<td class="${cls}"><a href="#/stage/${s.id}/exercises?lang=${l}">${d}/${ex.length}</a></td>`;
      }).join("") + "</tr>").join("") + "</tbody></table>";
    main.innerHTML = `<div class="page wide">
      <header class="hero">
        <div>
          <h1>Learn data analysis &amp; data science, end to end</h1>
          <p class="lead">Work through a real analysis for <b>Ridgeway Retail</b>, from raw files to a finished report,
          in <b>SQL</b>, <b>Python</b> and <b>R</b>. Every exercise runs on your computer and is checked automatically.</p>
          <div class="actions">
            ${nx ? `<a class="btn primary" href="#/ex/${nx.id}">${done ? "Continue" : "Start"}: ${esc(nx.title)} →</a>` : `<span class="pill ok">All exercises complete 🎉</span>`}
            <a class="btn" href="#/project">Capstone project</a>
          </div>
        </div>
        <div class="ring" style="--p:${total ? 100 * done / total : 0}">
          <div><b>${done}</b><span>of ${total}</span><small>exercises</small></div>
        </div>
      </header>
      <h2>The modules</h2>
      <p class="muted">Module 0 is optional if you already know some SQL, Python or R. Modules 1-9 follow a real analysis from raw data to report.</p>
      <div class="pipeline">${pipeline}</div>
      <div class="cols">
        <section class="card"><h2>Progress by language</h2>${matrix}
          <p class="muted">Each module has exercises in all three languages. Do one language first, then come back and
          compare how the others solve the same problem.</p></section>
        <section class="card"><h2>How it works</h2>
          <ol class="steps">
            <li><b>Read the lesson</b> for a module. Code samples switch between SQL, Python and R.</li>
            <li><b>Do the exercises.</b> <kbd>Ctrl</kbd>+<kbd>Enter</kbd> runs your code, <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Enter</kbd> checks it.</li>
            <li><b>Take the quiz</b> to test the concepts.</li>
            <li><b>Do the capstone</b> on a new dataset, then write it up in the <a href="#/report">Report Builder</a>.</li>
          </ol>
          <p class="muted">Charts you make are saved automatically and can be inserted into your report.
          Check the <a href="#/setup">Setup page</a> to confirm Python and R are ready.</p>
        </section>
      </div></div>`;
  }

  // ------------------------------------------------------------------ stage
  async function stage(sid, tab) {
    const [tabName, qs] = tab.split("?");
    const langFilter = new URLSearchParams(qs || "").get("lang");
    const s = await api("/api/stage/" + sid);
    const st = stageStats(sid);
    const idx = overview.stages.findIndex(x => x.id === sid);
    const prev = overview.stages[idx - 1], next = overview.stages[idx + 1];
    main.innerHTML = `<div class="page">
      <div class="crumbs"><a href="#/">Dashboard</a> › Module ${overview.stages[idx].order}</div>
      <h1 class="stagetitle"><span class="si">${STAGE_ICON[sid]}</span>${esc(s.title)}</h1>
      <p class="lead">${esc(s.summary)}</p>
      <div class="subtabs">
        <a href="#/stage/${sid}" class="${tabName === "lesson" ? "on" : ""}">Lesson</a>
        <a href="#/stage/${sid}/exercises" class="${tabName === "exercises" ? "on" : ""}">Exercises <span class="count">${st.done}/${st.total}</span></a>
        <a href="#/stage/${sid}/quiz" class="${tabName === "quiz" ? "on" : ""}">Quiz</a>
      </div>
      <div id="stagebody"></div>
      <div class="pager">
        ${prev ? `<a class="btn" href="#/stage/${prev.id}">← ${esc(prev.title)}</a>` : "<span></span>"}
        ${next ? `<a class="btn" href="#/stage/${next.id}">${esc(next.title)} →</a>` : `<a class="btn" href="#/project">Capstone project →</a>`}
      </div></div>`;
    const body = $("#stagebody");
    if (tabName === "lesson") {
      body.appendChild(md(s.lesson));
      body.appendChild(h(`<div class="callout">Ready? <a class="btn primary" href="#/stage/${sid}/exercises">Go to the exercises →</a></div>`));
    } else if (tabName === "exercises") {
      body.appendChild(exerciseList(sid, langFilter));
    } else {
      body.appendChild(quiz(sid, s.quiz));
    }
  }

  function exerciseList(sid, langFilter) {
    const wrap = h(`<div class="exlist"></div>`);
    ["sql", "python", "r"].forEach(l => {
      if (langFilter && langFilter !== l) return;
      const ex = overview.exercises.filter(e => e.stage === sid && e.lang === l);
      if (!ex.length) return;
      wrap.appendChild(h(`<section class="exgroup"><h3><span class="lang ${l}">${LANG[l]}</span></h3>
        ${ex.map(e => `<a class="exrow ${e.passed ? "done" : ""}" href="#/ex/${e.id}">
          <span class="tick">${e.passed ? "✓" : "○"}</span>
          <span class="t">${esc(e.title)}</span>
          ${e.level > 1 ? '<span class="pill">stretch</span>' : ""}
          ${e.needs.length ? `<span class="pill warn">needs ${esc(e.needs.join(", "))}</span>` : ""}
          ${e.revealed && !e.passed ? '<span class="pill">solution viewed</span>' : ""}
        </a>`).join("")}</section>`));
    });
    if (langFilter) wrap.appendChild(h(`<p><a href="#/stage/${sid}/exercises">Show all languages</a></p>`));
    return wrap;
  }

  function quiz(sid, questions) {
    const wrap = h(`<form class="quiz"></form>`);
    const prev = overview.quiz[sid];
    if (prev) wrap.appendChild(h(`<p class="muted">Best score so far: ${prev.best}/${prev.total}</p>`));
    questions.forEach((q, i) => {
      wrap.appendChild(h(`<fieldset class="q" data-i="${i}"><legend>${i + 1}. ${Markdown.inline(q.text)}</legend>
        ${q.options.map((o, k) => `<label><input type="radio" name="q${i}" value="${k}"> ${Markdown.inline(o)}</label>`).join("")}
        <div class="explain" hidden></div></fieldset>`));
    });
    wrap.appendChild(h(`<div class="actions"><button class="btn primary" type="submit">Check answers</button><span class="score"></span></div>`));
    wrap.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const answers = questions.map((_, i) => { const c = $(`input[name=q${i}]:checked`, wrap); return c ? +c.value : null; });
      const res = await api("/api/quiz/" + sid, { answers });
      res.results.forEach((r, i) => {
        const fs = $(`fieldset[data-i="${i}"]`, wrap);
        fs.classList.toggle("right", r.correct);
        fs.classList.toggle("wrong", !r.correct);
        $$("label", fs).forEach((lab, k) => lab.classList.toggle("answer", k === r.answer));
        const ex = $(".explain", fs);
        ex.hidden = false;
        ex.innerHTML = (r.correct ? "<b>Correct.</b> " : "<b>Not quite.</b> ") + Markdown.inline(r.explain || "");
      });
      $(".score", wrap).textContent = `Score: ${res.score}/${res.total}`;
      await refreshOverview();
    });
    return wrap;
  }

  // ------------------------------------------------------------------ output rendering
  function tableHTML(t, maxRows = 500) {
    if (!t || !t.columns || !t.columns.length) return "";
    const fmt = v => v === null ? '<span class="null">NULL</span>' : esc(typeof v === "number" ? (Number.isInteger(v) ? String(v) : String(+v.toPrecision(10))) : String(v));
    const rows = t.rows.slice(0, maxRows).map(r => "<tr>" + r.map(v => `<td class="${typeof v === "number" ? "n" : ""}">${fmt(v)}</td>`).join("") + "</tr>").join("");
    const note = t.truncated ? `<div class="muted small">Showing ${t.rows.length} of ${t.total} rows.</div>` : `<div class="muted small">${t.total} row${t.total === 1 ? "" : "s"}</div>`;
    return `<div class="tablewrap result"><table><thead><tr>${t.columns.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>${note}`;
  }
  function renderResult(el, res) {
    let html = "";
    if (res.check) {
      html += `<div class="check ${res.check.passed ? "pass" : "fail"}"><b>${res.check.passed ? "✓ Passed" : "✗ Not yet"}</b> ${esc(res.check.message || "")}</div>`;
    }
    html += tableHTML(res.table);
    if (res.stdout) html += `<pre class="out">${esc(res.stdout)}</pre>`;
    if (res.stderr) html += `<pre class="${res.ok ? "warnout" : "err"}">${esc(res.stderr)}</pre>`;
    if (res.images && res.images.length) {
      html += `<div class="figs">${res.images.map(n => `<figure><img src="/figures/${encodeURIComponent(n)}" alt="Chart"><figcaption>${esc(n)} · saved for the Report Builder</figcaption></figure>`).join("")}</div>`;
    }
    if (!html) html = `<div class="muted">Ran without output${res.ok ? "" : " (error)"}.</div>`;
    html += `<div class="muted small elapsed">${res.elapsed != null ? res.elapsed + " s" : ""}</div>`;
    el.innerHTML = html;
  }

  // ------------------------------------------------------------------ exercise
  async function exercise(id) {
    const ex = await api("/api/exercise/" + id);
    const st = overview.stages.find(s => s.id === ex.stage);
    let hintsShown = 0;
    main.innerHTML = `<div class="page exercise">
      <div class="crumbs"><a href="#/">Dashboard</a> › <a href="#/stage/${ex.stage}/exercises">${esc(st.title)}</a> › ${LANG[ex.lang]}</div>
      <div class="exgrid">
        <section class="taskpane">
          <h1>${esc(ex.title)}</h1>
          <div class="badges"><span class="lang ${ex.lang}">${LANG[ex.lang]}</span>
            <span class="pill">${ex.level > 1 ? "stretch" : "core"}</span>
            ${ex.needs.length ? `<span class="pill warn">needs ${esc(ex.needs.join(", "))}</span>` : ""}
            <span class="pill ok" id="passedPill" ${ex.passed ? "" : "hidden"}>✓ passed</span></div>
          <div id="task"></div>
          <div class="hints">
            <div id="hintList"></div>
            ${ex.hints.length ? `<button class="btn small" id="hintBtn">Show a hint (0/${ex.hints.length})</button>` : ""}
            <button class="btn small ghost" id="solBtn">Show solution</button>
          </div>
          <div id="solution"></div>
          <div class="datahint muted small">Your code runs in your workspace folder, so paths like <code>data/customers.csv</code> work.
            ${ex.lang === "sql" ? "Every CSV is also a view: <code>customers</code>, <code>customers_raw</code>, <code>orders</code>, <code>store_sales</code>, <code>rentals_raw</code>, <code>products</code>." : ""}</div>
        </section>
        <section class="codepane">
          <div class="toolbar">
            <button class="btn primary" id="runBtn" title="Ctrl+Enter">▶ Run</button>
            <button class="btn ok" id="checkBtn" title="Ctrl+Shift+Enter">✓ Check</button>
            <button class="btn ghost" id="resetBtn" title="Replace your code with the starter code">Reset</button>
            <span class="saved muted small" id="saved"></span>
            <span class="spacer"></span>
            ${ex.prev ? `<a class="btn ghost" href="#/ex/${ex.prev}" title="Previous exercise">←</a>` : ""}
            ${ex.next ? `<a class="btn ghost" href="#/ex/${ex.next}" title="Next exercise">→</a>` : ""}
          </div>
          <div id="editor"></div>
          <div id="output" class="output"><div class="muted">Press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> to run, <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Enter</kbd> to check.</div></div>
        </section>
      </div></div>`;
    $("#task").appendChild(md(ex.task));
    const saveCode = debounce(async (code) => {
      await api("/api/save", { exercise: id, code }).catch(() => {});
      const sv = $("#saved"); if (sv) sv.textContent = "saved";
    }, 1200);
    const ed = Editor.create($("#editor"), {
      value: ex.saved_code != null ? ex.saved_code : ex.starter, lang: ex.lang,
      onRun: () => run(false), onCheck: () => run(true),
      onChange: (v) => { const sv = $("#saved"); if (sv) sv.textContent = "…"; saveCode(v); },
    });
    ed.focus();
    let busy = false;
    async function run(check) {
      if (busy) return;
      busy = true;
      const out = $("#output");
      out.innerHTML = `<div class="running"><span class="spin"></span> ${check ? "Checking" : "Running"} ${LANG[ex.lang]}…</div>`;
      $("#runBtn").disabled = $("#checkBtn").disabled = true;
      try {
        const res = await api("/api/run", { exercise: id, code: ed.value, check });
        renderResult(out, res);
        if (res.check && res.check.passed) {
          $("#passedPill").hidden = false;
          const wasPassed = overview.exercises.find(e => e.id === id).passed;
          await refreshOverview();
          if (!wasPassed) toast("Exercise passed! 🎉", "ok");
          if (ex.next) out.insertAdjacentHTML("beforeend", `<div class="nextup"><a class="btn primary" href="#/ex/${ex.next}">Next exercise →</a></div>`);
        }
      } catch (e) {
        out.innerHTML = `<pre class="err">${esc(String(e))}</pre>`;
      } finally {
        busy = false;
        $("#runBtn").disabled = $("#checkBtn").disabled = false;
      }
    }
    $("#runBtn").onclick = () => run(false);
    $("#checkBtn").onclick = () => run(true);
    $("#resetBtn").onclick = () => { if (confirm("Replace your code with the starter code?")) { ed.value = ex.starter; saveCode(ex.starter); } };
    const hb = $("#hintBtn");
    if (hb) hb.onclick = () => {
      if (hintsShown >= ex.hints.length) return;
      $("#hintList").appendChild(h(`<div class="hint">💡 ${Markdown.inline(ex.hints[hintsShown])}</div>`));
      hintsShown++;
      hb.textContent = `Show a hint (${hintsShown}/${ex.hints.length})`;
      if (hintsShown >= ex.hints.length) hb.disabled = true;
    };
    $("#solBtn").onclick = async () => {
      if (!confirm("Show the model solution? Try the hints first. You learn more by struggling a little.")) return;
      const s = await api("/api/solution/" + id, {});
      const box = $("#solution");
      box.innerHTML = "";
      box.appendChild(h(`<div class="solution"><div class="solhead">Model solution <button class="btn small" id="useSol">Copy into editor</button></div><pre><code>${esc(s.solution)}</code></pre></div>`));
      $("#useSol").onclick = () => { if (confirm("Replace your code with the solution?")) { ed.value = s.solution; saveCode(s.solution); } };
    };
  }

  // ------------------------------------------------------------------ playground
  const SNIPPETS = {
    sql: [
      ["Peek at a table", "SELECT * FROM customers LIMIT 10;"],
      ["Profile every column", "SUMMARIZE customers;"],
      ["Read any CSV", "SELECT * FROM read_csv_auto('data/rentals_raw.csv') LIMIT 20;"],
      ["Revenue by category", "SELECT category, round(sum(quantity * unit_price * (1 - discount)), 2) AS revenue\nFROM orders\nGROUP BY category\nORDER BY revenue DESC;"],
    ],
    python: [
      ["Load & describe", "import pandas as pd\n\ndf = pd.read_csv(\"data/customers.csv\")\nprint(df.shape)\nprint(df.describe(include=\"all\").T)\n"],
      ["Quick chart", "import pandas as pd\nimport matplotlib.pyplot as plt\n\ndf = pd.read_csv(\"data/customers.csv\")\ndf.groupby(\"plan\")[\"churned\"].mean().plot.bar(title=\"Churn rate by plan\")\nplt.ylabel(\"Churn rate\")\nplt.show()\n"],
      ["Query with DuckDB from Python", "import duckdb\n\nprint(duckdb.sql(\"SELECT plan, avg(churned) FROM 'data/customers.csv' GROUP BY plan\").df())\n"],
      ["Capstone: load rentals", "import pandas as pd\n\nraw = pd.read_csv(\"data/rentals_raw.csv\", dtype=str, keep_default_na=False)\nprint(raw.shape)\nprint(raw.head())\nfor c in [\"season\", \"weather\"]:\n    print(raw[c].value_counts())\n"],
    ],
    r: [
      ["Load & summarise", "df <- read.csv(\"data/customers.csv\")\nstr(df)\nsummary(df)\n"],
      ["Quick chart", "df <- read.csv(\"data/customers.csv\")\nrates <- tapply(df$churned, df$plan, mean)\nbarplot(rates, main = \"Churn rate by plan\", ylab = \"Churn rate\")\n"],
      ["ggplot2 chart (if installed)", "library(ggplot2)\ndf <- read.csv(\"data/customers.csv\")\np <- ggplot(df, aes(income, monthly_spend, colour = plan)) + geom_point(alpha = 0.5) +\n  labs(title = \"Spend rises with income\", x = \"Income\", y = \"Monthly spend\")\nprint(p)\n"],
      ["Capstone: load rentals", "raw <- read.csv(\"data/rentals_raw.csv\", colClasses = \"character\")\ndim(raw)\nhead(raw)\ntable(raw$weather)\n"],
    ],
  };

  async function playground(langArg) {
    const saved = await api("/api/playground");
    let lang = LANG[langArg] ? langArg : store.get("pglang", "python");
    const pending = sessionStorage.getItem("dl-pg-load");
    sessionStorage.removeItem("dl-pg-load");
    main.innerHTML = `<div class="page exercise">
      <div class="crumbs"><a href="#/">Dashboard</a> › Playground</div>
      <h1>Playground</h1>
      <p class="lead">Free practice in any language against the same workspace and datasets. Your code is kept per language.</p>
      <div class="codepane">
        <div class="toolbar">
          <div class="seg" id="langSeg">${Object.keys(LANG).map(l => `<button data-l="${l}">${LANG[l]}</button>`).join("")}</div>
          <button class="btn primary" id="runBtn" title="Ctrl+Enter">▶ Run</button>
          <select id="snip"><option value="">Insert snippet…</option></select>
          <span class="spacer"></span>
          <a class="btn ghost" href="#/data">Datasets</a>
        </div>
        <div id="editor"></div>
        <div id="output" class="output"><div class="muted">Press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> to run.</div></div>
      </div></div>`;
    let ed;
    function mount() {
      $$("#langSeg button").forEach(b => b.classList.toggle("on", b.dataset.l === lang));
      const code = saved[lang] != null ? saved[lang] : SNIPPETS[lang][0][1];
      $("#editor").innerHTML = "";
      ed = Editor.create($("#editor"), { value: code, lang, onRun: run, onChange: debounce(v => { saved[lang] = v; api("/api/playground", saved).catch(() => {}); }, 1000) });
      $("#snip").innerHTML = `<option value="">Insert snippet…</option>` + SNIPPETS[lang].map((s, i) => `<option value="${i}">${esc(s[0])}</option>`).join("");
      ed.focus();
    }
    async function run() {
      const out = $("#output");
      out.innerHTML = `<div class="running"><span class="spin"></span> Running ${LANG[lang]}…</div>`;
      try { renderResult(out, await api("/api/run", { lang, code: ed.value, playground_key: lang })); }
      catch (e) { out.innerHTML = `<pre class="err">${esc(String(e))}</pre>`; }
    }
    $$("#langSeg button").forEach(b => b.onclick = () => { lang = b.dataset.l; store.set("pglang", lang); mount(); });
    $("#snip").onchange = (e) => {
      const s = SNIPPETS[lang][+e.target.value];
      if (s) { ed.value = s[1]; saved[lang] = s[1]; api("/api/playground", saved).catch(() => {}); }
      e.target.value = "";
    };
    $("#runBtn").onclick = run;
    if (pending) {
      const p = JSON.parse(pending);
      lang = p.lang;
      saved[lang] = p.code;
      api("/api/playground", saved).catch(() => {});
    }
    mount();
  }
  function openInPlayground(lang, code) {
    sessionStorage.setItem("dl-pg-load", JSON.stringify({ lang, code }));
    location.hash = "#/playground/" + lang;
  }

  // ------------------------------------------------------------------ datasets
  const DATA_INFO = {
    "customers_raw.csv": "CRM export, deliberately messy: duplicates, mixed case, '$52,000' incomes, impossible ages, two date formats.",
    "customers.csv": "The cleaned customer table (answer key for Module 2, Clean). Used from Module 3 (EDA) on.",
    "orders.csv": "4,000 orders 2021–2024: date, category, quantity, unit price, discount.",
    "products.json": "Product categories with department and margin.",
    "ridgeway.db": "SQLite database with the stores and revenue-target tables.",
    "rentals_raw.csv": "Daily bike rentals 2023–2024 for the capstone project (messy).",
    "store_sales.csv": "Weekly Ridgeway sales 2021–2024 with promotion weeks, used in Module 7 (Forecast).",
  };
  async function datasets(name) {
    const list = await api("/api/datasets");
    name = name || "customers_raw.csv";
    main.innerHTML = `<div class="page wide">
      <div class="crumbs"><a href="#/">Dashboard</a> › Datasets</div>
      <h1>Datasets</h1>
      <div class="datagrid">
        <aside class="filelist">${list.map(f => `<a href="#/data/${encodeURIComponent(f.name)}" class="${f.name === name ? "on" : ""}">
          <b>${esc(f.name)}</b><span class="muted small">${(f.size / 1024).toFixed(0)} KB</span></a>`).join("")}
          <button class="btn small ghost" id="resetData" title="Copy fresh datasets into the workspace">Restore original files</button>
        </aside>
        <section id="preview"><div class="running"><span class="spin"></span> Loading…</div></section>
      </div></div>`;
    $("#resetData").onclick = async () => {
      if (!confirm("Overwrite the files in your workspace data folder with fresh copies? Files you created yourself are kept.")) return;
      await api("/api/reset-data", {});
      toast("Datasets restored", "ok");
      datasets(name);
    };
    const p = await api("/api/dataset/" + encodeURIComponent(name)).catch(() => null);
    const box = $("#preview");
    if (!p) { box.innerHTML = "<p>Not found.</p>"; return; }
    const stem = name.replace(/\.\w+$/, "");
    let load = "";
    if (name.endsWith(".csv")) {
      load = "```sql\nSELECT * FROM read_csv_auto('data/" + name + "');   -- or simply: SELECT * FROM " + stem + "\n```\n```python\nimport pandas as pd\n" + stem + " = pd.read_csv(\"data/" + name + "\")\n```\n```r\n" + stem + " <- read.csv(\"data/" + name + "\")\n```";
    } else if (name.endsWith(".json")) {
      load = "```sql\nSELECT * FROM read_json_auto('data/" + name + "');\n```\n```python\nimport pandas as pd\n" + stem + " = pd.read_json(\"data/" + name + "\")\n```\n```r\n" + stem + " <- jsonlite::fromJSON(\"data/" + name + "\")\n```";
    } else if (name.endsWith(".db")) {
      load = "```sql\n-- DuckDB can attach SQLite files (downloads the sqlite extension once)\nATTACH 'data/" + name + "' AS shop (TYPE sqlite);\nSELECT * FROM shop.stores;\n```\n```python\nimport sqlite3, pandas as pd\ncon = sqlite3.connect(\"data/" + name + "\")\nstores = pd.read_sql(\"SELECT * FROM stores\", con)\ncon.close()\n```\n```r\ncon <- DBI::dbConnect(RSQLite::SQLite(), \"data/" + name + "\")\nstores <- DBI::dbGetQuery(con, \"SELECT * FROM stores\")\nDBI::dbDisconnect(con)\n```";
    }
    box.innerHTML = `<h2>${esc(name)}</h2><p>${esc(DATA_INFO[name] || "")}</p>`;
    if (load) { box.appendChild(h("<h3>Load it</h3>")); box.appendChild(md(load)); }
    if (p.kind === "table") {
      box.insertAdjacentHTML("beforeend", `<h3>First rows <span class="muted small">(${p.rows} rows in file, shown as raw text)</span></h3>${tableHTML(p.table)}
        <h3>Column profile <span class="muted small">(DuckDB SUMMARIZE)</span></h3>${tableHTML(p.profile)}`);
    } else {
      box.insertAdjacentHTML("beforeend", `<pre class="out">${esc(p.text)}</pre>`);
    }
  }

  // ------------------------------------------------------------------ capstone project
  const PROJECT_STEPS = [
    { id: "import", title: "1 · Import", body:
`Load **\`data/rentals_raw.csv\`**: daily bike rentals for a city scheme, 2023–2024. Read every column as text first.

Record: number of rows, number of distinct dates, and which columns *should* be numbers.

\`\`\`sql
SELECT count(*) AS n_rows, count(DISTINCT date) AS n_days FROM read_csv('data/rentals_raw.csv', all_varchar = true);
\`\`\`
\`\`\`python
import pandas as pd
raw = pd.read_csv("data/rentals_raw.csv", dtype=str, keep_default_na=False)
print(raw.shape, raw["date"].nunique())
\`\`\`
\`\`\`r
raw <- read.csv("data/rentals_raw.csv", colClasses = "character")
dim(raw); length(unique(raw$date))
\`\`\`` },
    { id: "clean", title: "2 · Clean", body:
`Find and fix the problems yourself. There are at least five:

- duplicated days,
- inconsistent \`weather\` labels,
- \`humidity\` stored as text like \`"65%"\`,
- missing \`temp_c\` values **and** a sensor error code (look at the minimum!),
- \`date\` as text. Also add \`weekday\` and \`is_weekend\`.

Save your result to **\`data/rentals_clean.csv\`**, then press **Validate my clean file** below.` , validate: true },
    { id: "eda", title: "3 · Explore", body:
`Answer with numbers and charts:

- How do rentals differ by **season**, **weather** and **weekend vs weekday**?
- How strongly are rentals related to **temperature**, **humidity** and **wind**? (scatter plots + correlations)
- Is there a **trend** over the two years? (line chart by month)

Write each finding as a sentence with a number. You'll need them in the report.` },
    { id: "model", title: "4 · Model", body:
`Predict daily \`rentals\`.

- Use a **time-based split**: train on 2023, test on 2024. A random split would let the model "see the future".
- Start with a linear regression (temperature, humidity, wind, weather, weekend, holiday, and a time trend such as days since start).
- Report **RMSE** and **MAE** on 2024 and compare with a naive baseline (e.g. the 2023 average for the same season).
- Optional: try a random forest and compare.` },
    { id: "explain", title: "5 · Explain & shape", body:
`- Compute SHAP values (by hand for the linear model, or with \`shap\` for a forest). Which features matter most? In which direction?
- Explain one specific day: why was the prediction so low on a rainy weekday?
- Shape a **season × weather** table of average rentals for the report.` },
    { id: "report", title: "6 · Report", body:
`Open the **Report Builder**, choose the *Capstone* template and write a report for the scheme's operations manager:
how many bikes should they plan for, and what drives demand? Insert at least two charts and make
the rubric go green, then export the HTML.` },
  ];
  const VALIDATE_PY = `import pandas as pd, os
problems = []
p = "data/rentals_clean.csv"
if not os.path.exists(p):
    raise SystemExit(print("data/rentals_clean.csv not found - save your cleaned data there first."))
df = pd.read_csv(p)
def need(cond, msg):
    (None if cond else problems.append(msg))
need("date" in df.columns, "a 'date' column")
if "date" in df.columns:
    d = pd.to_datetime(df["date"], errors="coerce")
    need(d.notna().all(), "every date parses")
    need(df["date"].is_unique, "one row per date (remove the duplicated days)")
    need(len(df) == 730, f"730 days (2023-01-01 .. 2024-12-30); you have {len(df)}")
for c in ["temp_c", "humidity", "windspeed_kmh", "rentals"]:
    need(c in df.columns and pd.api.types.is_numeric_dtype(df[c]), f"'{c}' is numeric")
if "temp_c" in df.columns and pd.api.types.is_numeric_dtype(df["temp_c"]):
    need(df["temp_c"].notna().all(), "temp_c has no missing values (impute them)")
    need(df["temp_c"].min() > -20, f"temp_c has no sensor error codes (min is {df['temp_c'].min()})")
if "humidity" in df.columns and pd.api.types.is_numeric_dtype(df["humidity"]):
    need(df["humidity"].between(0, 100).all(), "humidity is a number between 0 and 100")
if "weather" in df.columns:
    need(set(df["weather"].dropna()) <= {"Clear", "Mist", "Rain"}, f"weather is one of Clear/Mist/Rain (found {sorted(set(df['weather'].dropna()))})")
need("is_weekend" in df.columns, "an 'is_weekend' column")
if problems:
    print("Not yet. Still to do:")
    for m in problems: print("  -", m)
else:
    print("Your cleaned rentals file passes every check. On to EDA!")
`;
  async function project() {
    const state = await api("/api/project");
    state.done = state.done || {};
    state.notes = state.notes || {};
    const save = debounce(() => api("/api/project", state).catch(() => {}), 800);
    main.innerHTML = `<div class="page">
      <div class="crumbs"><a href="#/">Dashboard</a> › Capstone</div>
      <h1>Capstone project: bike rental demand</h1>
      <p class="lead">Use everything you've learned on a new, messy dataset. No step-by-step checks this time,
      apart from a validator for your cleaned file. Work in the <a href="#/playground">Playground</a> in any language,
      keep notes here, and finish with a report.</p>
      <div id="steps"></div></div>`;
    const box = $("#steps");
    PROJECT_STEPS.forEach(s => {
      const card = h(`<section class="card step ${state.done[s.id] ? "done" : ""}">
        <div class="stephead"><h2>${esc(s.title)}</h2>
          <label class="donebox"><input type="checkbox" ${state.done[s.id] ? "checked" : ""}> done</label></div>
        <div class="stepbody"></div>
        <div class="stepactions"></div>
        <label class="small muted">Your notes and findings</label>
        <textarea class="notes" rows="3" placeholder="e.g. 6 duplicated days removed; 22 temperatures imputed...">${esc(state.notes[s.id] || "")}</textarea>
      </section>`);
      $(".stepbody", card).appendChild(md(s.body));
      const acts = $(".stepactions", card);
      acts.appendChild(h(`<button class="btn small">Open in Playground</button>`)).onclick = () => {
        const pane = $(".langtabs .pane:not([hidden]) code", card);
        const lang = pane ? pane.closest(".pane").dataset.lang : store.get("pglang", "python");
        openInPlayground(lang, pane ? pane.textContent + "\n" : "");
      };
      if (s.validate) {
        const out = h(`<div class="output"></div>`);
        acts.appendChild(h(`<button class="btn small ok">Validate my clean file</button>`)).onclick = async () => {
          out.innerHTML = `<div class="running"><span class="spin"></span> Validating…</div>`;
          renderResult(out, await api("/api/run", { lang: "python", code: VALIDATE_PY }));
        };
        acts.after(out);
      }
      if (s.id === "report") acts.appendChild(h(`<a class="btn small primary" href="#/report">Open Report Builder</a>`));
      $("input[type=checkbox]", card).onchange = (e) => { state.done[s.id] = e.target.checked; card.classList.toggle("done", e.target.checked); save(); };
      $("textarea", card).oninput = (e) => { state.notes[s.id] = e.target.value; save(); };
      box.appendChild(card);
    });
  }

  // ------------------------------------------------------------------ report builder
  const SECTIONS = [
    ["summary", "Executive summary", "Question → answer → 2-3 key numbers → recommendation. At most 150 words."],
    ["context", "Question & context", "Why does this matter? Who asked? Which decision will it support?"],
    ["data", "Data", "Sources, period, number of rows; what you cleaned, removed or imputed."],
    ["findings", "Findings", "3-5 findings, each a sentence with a number and a comparison. Insert charts."],
    ["model", "Model", "What you predicted, the method, the test-set metric vs a baseline."],
    ["explain", "What drives the result", "Which features matter and in which direction (SHAP / importance)."],
    ["recommendations", "Recommendations", "Concrete actions as bullet points, each linked to a finding."],
    ["limitations", "Limitations & next steps", "Data gaps, assumptions, correlation ≠ causation, what you'd do next."],
  ];
  const TEMPLATES = {
    ridgeway: {
      title: "Support problems and the Basic plan drive churn at Ridgeway",
      sections: {
        summary: "Ridgeway loses **x%** of customers ... (write this last)",
        context: "Ridgeway Retail wants to know which customers are likely to cancel their subscription and why, so the retention team can target its effort.",
        data: "- 618 rows in the CRM export; 18 duplicates removed → 600 customers.\n- 4,000 orders from 2021–2024.\n- Missing / impossible ages and incomes filled with the median (state how many).",
        findings: "- Basic-plan customers churn at ...% vs ...% on Premium.\n- Customers with 4+ support calls churn at ...%.\n- ...",
        model: "Logistic regression on tenure, support calls, plan, fee, age, income and region. Test-set ROC AUC = ... (0.5 = random).",
        explain: "SHAP values show ... pushes churn risk up, while ... pulls it down.",
        recommendations: "- ...\n- ...",
        limitations: "- Observational data: associations, not proven causes.\n- ...",
      },
    },
    capstone: {
      title: "Warm, dry weekends drive bike demand",
      sections: {
        summary: "", context: "The operations manager needs to plan how many bikes to make available each day.",
        data: "- Daily rentals for 2023–2024 (... days after removing duplicates).\n- ...", findings: "- ...", model: "Trained on 2023, tested on 2024. RMSE = ... rentals/day vs baseline ...",
        explain: "", recommendations: "- ...", limitations: "- ...",
      },
    },
    blank: { title: "", sections: {} },
  };

  function reportMarkdown(r) {
    let s = `# ${r.title || "Untitled report"}\n\n`;
    const meta = [r.author, r.date].filter(Boolean).join(" · ");
    if (meta) s += `*${meta}*\n\n`;
    SECTIONS.forEach(([k, title]) => { const t = (r.sections[k] || "").trim(); if (t) s += `## ${title}\n\n${t}\n\n`; });
    return s;
  }
  function words(t) { return (t.replace(/[#*`>\[\]()!-]/g, " ").match(/\S+/g) || []).length; }
  function rubric(r) {
    const S = k => (r.sections[k] || "").trim();
    const all = SECTIONS.map(([k]) => S(k)).join("\n");
    const bullets = t => t.split("\n").filter(l => /^\s*([-*+]|\d+[.)])\s+\S/.test(l));
    const hasNum = t => /\d/.test(t.replace(/!\[[^\]]*\]\([^)]*\)/g, ""));
    const sw = words(S("summary"));
    const findingLines = bullets(S("findings")).length ? bullets(S("findings")) : S("findings").split(/\n\s*\n/);
    const placeholder = /\.\.\.|x%|write this last/i;
    return [
      [words(r.title || "") >= 4 && !/^(report|analysis|churn report)$/i.test((r.title || "").trim()), "Title states the main finding (4+ words)"],
      [sw >= 30 && sw <= 150, `Executive summary is 30–150 words (now ${sw})`],
      [hasNum(S("summary")), "Executive summary quotes at least one number"],
      [findingLines.filter(hasNum).length >= 3, "At least 3 findings contain numbers"],
      [/!\[[^\]]*\]\([^)]+\)/.test(all), "Includes at least one chart"],
      [/(AUC|R²|R2|R-squared|RMSE|MAE|accuracy|precision|recall)/i.test(S("model")), "Model section names an evaluation metric"],
      [/(baseline|naive|compared|vs\.?|versus)/i.test(S("model")), "Model is compared with a baseline"],
      [/(SHAP|importance|driver|coefficient|odds)/i.test(S("explain")), "Explains what drives the result (SHAP / importance)"],
      [bullets(S("recommendations")).length >= 2, "At least 2 recommendations as bullets"],
      [S("limitations").length > 20, "States limitations"],
      [/(clean|duplicate|missing|imput|removed)/i.test(S("data")), "Data section describes cleaning"],
      [!/\d\.\d{4,}/.test(all), "No over-precise numbers (≥4 decimals)"],
      [!placeholder.test(all + r.title), "No placeholders left (…, x%)"],
    ];
  }
  async function imgToDataURI(src) {
    const r = await fetch(src);
    const b = await r.blob();
    return await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(b); });
  }
  async function reportHTML(r) {
    const body = document.createElement("div");
    body.innerHTML = Markdown.render(reportMarkdown(r));
    for (const img of $$("img", body)) {
      if (img.getAttribute("src").startsWith("/figures/")) img.src = await imgToDataURI(img.getAttribute("src"));
      if (img.alt) img.insertAdjacentHTML("afterend", `<div class="cap">${esc(img.alt)}</div>`);
    }
    $$("button.copy, .tabbar", body).forEach(x => x.remove());
    return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(r.title || "Report")}</title><style>
body{font:16px/1.6 Georgia,'Times New Roman',serif;color:#1d232b;max-width:780px;margin:40px auto;padding:0 20px;background:#fff}
h1{font:700 2rem/1.2 system-ui,sans-serif;margin-bottom:.2rem}h2{font:600 1.3rem system-ui,sans-serif;margin-top:2rem;border-bottom:1px solid #e3e6ea;padding-bottom:.2rem}
img{max-width:100%;display:block;margin:1rem auto 0}.cap{text-align:center;font:italic .9rem system-ui,sans-serif;color:#5b6573;margin-bottom:1rem}
table{border-collapse:collapse;margin:1rem 0;font:.9rem system-ui,sans-serif}td,th{border:1px solid #d5d9de;padding:4px 10px}th{background:#f3f5f7}
code,pre{font-family:Consolas,Menlo,monospace;background:#f3f5f7}pre{padding:10px;overflow:auto}blockquote{border-left:3px solid #c5ccd5;margin-left:0;padding-left:1rem;color:#4a5462}
.pane{display:block}@media print{body{margin:0}h2{break-after:avoid}img{break-inside:avoid}}
</style></head><body>${body.innerHTML}</body></html>`;
  }

  async function report() {
    let r = await api("/api/report");
    if (!r.sections) r = { title: "", author: "", date: new Date().toISOString().slice(0, 10), sections: {} };
    let lastFocus = null;
    const save = debounce(() => api("/api/report", r).catch(() => {}), 800);
    main.innerHTML = `<div class="page wide">
      <div class="crumbs"><a href="#/">Dashboard</a> › Report Builder</div>
      <h1>Report Builder</h1>
      <p class="lead">Write your report section by section in Markdown. Insert charts from your runs, check the draft against the rubric, then export a self-contained HTML file (print it to PDF from the browser).</p>
      <div class="toolbar wrap">
        <select id="tpl"><option value="">Start from a template…</option><option value="ridgeway">Ridgeway churn report</option><option value="capstone">Capstone: bike rentals</option><option value="blank">Blank</option></select>
        <button class="btn" id="figBtn">🖼 Insert chart</button>
        <span class="spacer"></span>
        <button class="btn" id="mdBtn">Download .md</button>
        <button class="btn" id="printBtn">Print / PDF</button>
        <button class="btn primary" id="exportBtn">Export HTML</button>
      </div>
      <div class="reportgrid">
        <section class="reportedit">
          <label>Title <input id="rTitle" placeholder="State the main finding, e.g. 'Support problems drive churn'"></label>
          <div class="row2"><label>Author <input id="rAuthor"></label><label>Date <input id="rDate"></label></div>
          <div id="rSections"></div>
        </section>
        <section class="reportside">
          <div class="card"><h3>Rubric <span id="score" class="pill"></span></h3><ul id="rubric" class="rubric"></ul></div>
          <div class="card preview"><h3>Preview</h3><div id="rPreview" class="md report"></div></div>
        </section>
      </div>
      <div id="figModal" class="modal" hidden><div class="modalbox"><div class="modalhead"><h3>Insert a chart</h3><button class="btn small ghost" id="figClose">✕</button></div>
        <p class="muted small">Charts appear here after you run code that draws them (Python plt.show(), R plot(), ggplot print()).</p>
        <div id="figGrid" class="figgrid"></div></div></div>
    </div>`;
    const sec = $("#rSections");
    SECTIONS.forEach(([k, title, guide]) => {
      const el = h(`<div class="rsec"><label>${esc(title)}<span class="muted small"> · ${esc(guide)}</span></label><textarea data-k="${k}" rows="4"></textarea></div>`);
      sec.appendChild(el);
    });
    function fill() {
      $("#rTitle").value = r.title || ""; $("#rAuthor").value = r.author || ""; $("#rDate").value = r.date || "";
      $$("#rSections textarea").forEach(t => { t.value = r.sections[t.dataset.k] || ""; autosize(t); });
      update();
    }
    function autosize(t) { t.style.height = "auto"; t.style.height = Math.max(90, t.scrollHeight + 4) + "px"; }
    const updatePreview = debounce(() => {
      const p = $("#rPreview");
      p.innerHTML = Markdown.render(reportMarkdown(r));
      enhance(p);
    }, 250);
    function update() {
      updatePreview();
      const rb = rubric(r);
      const n = rb.filter(x => x[0]).length;
      $("#score").textContent = `${n}/${rb.length}`;
      $("#score").className = "pill " + (n === rb.length ? "ok" : n >= rb.length / 2 ? "" : "warn");
      $("#rubric").innerHTML = rb.map(([ok, label]) => `<li class="${ok ? "ok" : ""}">${ok ? "✓" : "○"} ${esc(label)}</li>`).join("");
      save();
    }
    $("#rTitle").oninput = e => { r.title = e.target.value; update(); };
    $("#rAuthor").oninput = e => { r.author = e.target.value; update(); };
    $("#rDate").oninput = e => { r.date = e.target.value; update(); };
    $$("#rSections textarea").forEach(t => {
      t.oninput = () => { r.sections[t.dataset.k] = t.value; autosize(t); update(); };
      t.onfocus = () => { lastFocus = t; };
    });
    $("#tpl").onchange = (e) => {
      const tp = TEMPLATES[e.target.value];
      e.target.value = "";
      if (!tp) return;
      const empty = !r.title && !Object.values(r.sections).some(Boolean);
      if (!empty && !confirm("Replace your current draft with the template?")) return;
      r.title = tp.title;
      r.sections = Object.assign({}, tp.sections);
      fill();
    };
    $("#figBtn").onclick = async () => {
      const figs = await api("/api/figures");
      $("#figGrid").innerHTML = figs.length ? figs.map(f => `<button class="fig" data-n="${esc(f.name)}"><img loading="lazy" src="/figures/${encodeURIComponent(f.name)}" alt=""><span>${esc(f.name)}</span></button>`).join("")
        : `<p>No charts yet. Make one in an exercise or the <a href="#/playground">Playground</a>.</p>`;
      $("#figModal").hidden = false;
      $$("#figGrid .fig").forEach(b => b.onclick = () => {
        const cap = prompt("Caption (what should the reader notice?)", "Figure: ") || "Figure";
        const t = lastFocus || $('#rSections textarea[data-k="findings"]');
        const ins = `\n![${cap.replace(/[\[\]]/g, "")}](/figures/${b.dataset.n})\n`;
        const pos = t.selectionStart != null ? t.selectionEnd : t.value.length;
        t.value = t.value.slice(0, pos) + ins + t.value.slice(pos);
        r.sections[t.dataset.k] = t.value;
        autosize(t);
        $("#figModal").hidden = true;
        update();
      });
    };
    $("#figClose").onclick = () => { $("#figModal").hidden = true; };
    function download(name, text, type) {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([text], { type }));
      a.download = name;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    }
    const fname = () => (r.title || "report").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "report";
    $("#mdBtn").onclick = () => download(fname() + ".md", reportMarkdown(r), "text/markdown");
    $("#exportBtn").onclick = async () => {
      const html = await reportHTML(r);
      const res = await api("/api/report/export", { filename: fname(), html, markdown: reportMarkdown(r) });
      download(fname() + ".html", html, "text/html");
      toast("Saved to " + (res.saved.html || "reports folder"), "ok");
    };
    $("#printBtn").onclick = async () => {
      const w = window.open("", "_blank");
      if (!w) { toast("Allow pop-ups to print", "warn"); return; }
      w.document.write(await reportHTML(r));
      w.document.close();
      setTimeout(() => w.print(), 400);
    };
    fill();
  }

  // ------------------------------------------------------------------ setup
  async function setup(refresh) {
    main.innerHTML = `<div class="page"><div class="crumbs"><a href="#/">Dashboard</a> › Setup</div><h1>Setup &amp; environment</h1>
      <div class="running"><span class="spin"></span> Checking Python, R and DuckDB…</div></div>`;
    const [env, settings] = await Promise.all([api("/api/env" + (refresh ? "?refresh=1" : "")), api("/api/settings")]);
    const pk = (pkgs) => Object.entries(pkgs || {}).map(([k, v]) => `<span class="pkg ${v ? "ok" : "no"}">${v ? "✓" : "✗"} ${esc(k)}${v ? ` <small>${esc(String(v))}</small>` : ""}</span>`).join("");
    const py = env.python, r = env.r;
    const missingPy = Object.entries(py.packages || {}).filter(([, v]) => !v).map(([k]) => k === "sklearn" ? "scikit-learn" : k);
    const missingR = Object.entries(r.packages || {}).filter(([, v]) => !v).map(([k]) => k);
    const GUIDE = {
      Windows: `1. Install Python 3.10+ from https://www.python.org/downloads/ (tick "Add python.exe to PATH").
2. In the datalab_trainer folder double-click install.bat (once), then run.bat to start.
3. Install R from https://cran.r-project.org/bin/windows/base/ (default options).
   DataLab finds Rscript.exe under C:\\Program Files\\R automatically.
4. Optional R packages:  Rscript setup_r_packages.R`,
      Ubuntu: `sudo apt update
sudo apt install python3 python3-venv r-base
./install.sh                 # once: creates .venv and installs the Python packages
./run.sh                     # starts DataLab and opens your browser
Rscript setup_r_packages.R   # optional R packages`,
    };
    main.innerHTML = `<div class="page">
      <div class="crumbs"><a href="#/">Dashboard</a> › Setup</div>
      <h1>Setup &amp; environment</h1>
      <p class="lead">DataLab runs SQL with DuckDB, Python with your Python installation and R with <code>Rscript</code>.
      Everything runs natively on Windows and Ubuntu, with no Wine, Bottles or virtual machine.</p>
      <div class="envgrid">
        <section class="card"><h2>SQL <span class="pill ${env.sql.duckdb ? "ok" : "warn"}">${env.sql.duckdb ? "ready" : "missing"}</span></h2>
          <p>DuckDB ${esc(env.sql.duckdb || "not installed")}: built in, nothing else to install.</p></section>
        <section class="card"><h2>Python <span class="pill ${py.version && !missingPy.filter(m => m !== "shap").length ? "ok" : "warn"}">${py.version ? esc(py.version) : "not found"}</span></h2>
          <p class="small muted">${esc(py.path || "")}</p><div class="pkgs">${pk(py.packages)}</div>
          ${(py.path || "").startsWith("built-in") ? `<p class="small muted">Python and all course libraries are bundled with this app. To use extra packages, install Python yourself and enter its path under Settings.</p>`
            : missingPy.length ? `<p class="small">Install missing packages:</p><pre class="out">"${esc(py.path || "python")}" -m pip install ${esc(missingPy.join(" "))}</pre>` : ""}
          ${py.error ? `<pre class="err">${esc(py.error)}</pre>` : ""}</section>
        <section class="card"><h2>R <span class="pill ${r.version ? "ok" : "warn"}">${r.version ? esc(r.version) : "not found"}</span></h2>
          ${r.path ? `<p class="small muted">${esc(r.path)}</p><div class="pkgs">${pk(r.packages)}</div>
          <p class="small muted">All checked R exercises use base R only. The packages are optional extras used in lesson examples.</p>
          ${missingR.length ? `<pre class="out">install.packages(c(${missingR.map(m => `"${esc(m)}"`).join(", ")}))</pre>` : ""}` : `<pre class="err">${esc(r.error || "")}</pre>`}</section>
      </div>
      <section class="card"><h2>Settings</h2>
        <form id="settings" class="settings">
          <label>Python interpreter <span class="muted small">(empty = the Python running DataLab)</span><input name="python_path" value="${esc(settings.python_path || "")}" placeholder="${esc((py.path || "").startsWith("built-in") ? "built-in" : (py.path || ""))}"></label>
          <label>Rscript path <span class="muted small">(empty = find automatically)</span><input name="rscript_path" value="${esc(settings.rscript_path || "")}" placeholder="${navigator.platform.startsWith("Win") ? "C:\\Program Files\\R\\R-4.4.1\\bin\\Rscript.exe" : "/usr/bin/Rscript"}"></label>
          <label>Time limit per run (seconds)<input name="timeout" type="number" min="10" max="1800" value="${esc(String(settings.timeout || 120))}"></label>
          <div class="actions"><button class="btn primary">Save &amp; re-check</button><button type="button" class="btn ghost" id="recheck">Re-check environment</button></div>
        </form></section>
      <section class="card"><h2>Install guide</h2><div id="guide"></div></section>
      <section class="card"><h2>Your files</h2>
        <p>Workspace (code runs here): <code>${esc(env.workspace)}</code></p>
        <p>Progress, settings and drafts: <code>${esc(env.home)}</code></p>
        <div class="actions"><button class="btn ghost" id="resetData">Restore original datasets</button>
          <button class="btn danger" id="resetProg">Reset all progress</button></div></section>
    </div>`;
    const os0 = navigator.platform.startsWith("Win") ? "Windows" : "Ubuntu";
    const g = h(`<div class="langtabs"><div class="tabbar">${Object.keys(GUIDE).map(k => `<button class="tab" data-os="${k}">${k}</button>`).join("")}</div>
      ${Object.entries(GUIDE).map(([k, v]) => `<div class="pane" data-os="${k}"><pre><code>${esc(v)}</code></pre></div>`).join("")}</div>`);
    const showOS = (k) => { $$(".pane", g).forEach(p => p.hidden = p.dataset.os !== k); $$(".tab", g).forEach(t => t.classList.toggle("on", t.dataset.os === k)); };
    $$(".tab", g).forEach(t => t.onclick = () => showOS(t.dataset.os));
    showOS(os0);
    $("#guide").appendChild(g);
    $("#settings").onsubmit = async (e) => {
      e.preventDefault();
      const f = new FormData(e.target);
      await api("/api/settings", { python_path: f.get("python_path"), rscript_path: f.get("rscript_path"), timeout: +f.get("timeout") });
      toast("Settings saved", "ok");
      setup(false);
    };
    $("#recheck").onclick = () => setup(true);
    $("#resetData").onclick = async () => { if (confirm("Overwrite workspace datasets with fresh copies?")) { await api("/api/reset-data", {}); toast("Datasets restored", "ok"); } };
    $("#resetProg").onclick = async () => {
      if (!confirm("Delete ALL progress, saved code, quiz scores and report drafts? This can't be undone.")) return;
      await api("/api/reset-progress", {});
      await refreshOverview();
      toast("Progress reset");
      location.hash = "#/";
    };
  }

  route();
})();
