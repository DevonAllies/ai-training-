// Tiny dependency-free canvas charts (works offline).
"use strict";

const Charts = (() => {
  function setup(canvas) {
    const dpr = window.devicePixelRatio || 1;
    if (!canvas.dataset.h) canvas.dataset.h = canvas.getAttribute("height") || "200";
    const h = +canvas.dataset.h;
    canvas.style.height = h + "px";
    const w = canvas.clientWidth;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return { ctx, w, h };
  }

  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  /**
   * series: [{data:number[], color, width?, fill?, axis?: 'left'|'right'}]
   * opts: {n (x points), ymin, ymax, y2min, y2max, zeroLine2, regions:[{start,end,label}], cursor, onHover}
   */
  function line(canvas, series, opts = {}) {
    const { ctx, w, h } = setup(canvas);
    const hasRight = opts.y2min !== undefined || series.some((s) => s.axis === "right");
    const pad = { l: 40, r: hasRight ? 44 : 8, t: 8, b: 16 };
    const n = opts.n || Math.max(...series.map((s) => (s.data ? s.data.length : 0)), 1);
    const pw = w - pad.l - pad.r, ph = h - pad.t - pad.b;
    const X = (i) => pad.l + (i / (n - 1)) * pw;

    const range = (axis) => {
      let lo = axis === "right" ? opts.y2min : opts.ymin, hi = axis === "right" ? opts.y2max : opts.ymax;
      if (lo === undefined || hi === undefined || lo === null || hi === null) {
        let a = Infinity, b = -Infinity;
        series.filter((s) => (s.axis || "left") === axis && s.data).forEach((s) => s.data.forEach((v) => {
          if (v !== null && isFinite(v)) { a = Math.min(a, v); b = Math.max(b, v); }
        }));
        if (!isFinite(a)) { a = 0; b = 1; }
        if (axis === "right") { const m = Math.max(Math.abs(a), Math.abs(b), 0.05); a = -m; b = m; }
        const p = (b - a) * 0.05 || 1;
        lo = lo ?? a - p; hi = hi ?? b + p;
      }
      return [lo, hi];
    };
    const [l1, h1] = range("left");
    const [l2, h2] = range("right");
    const Y = (v, axis) => {
      const [lo, hi] = axis === "right" ? [l2, h2] : [l1, h1];
      return pad.t + ph - ((v - lo) / (hi - lo)) * ph;
    };

    // corner regions
    ctx.font = "10px Segoe UI, sans-serif";
    (opts.regions || []).forEach((r, k) => {
      if (k % 2 === 0) { ctx.fillStyle = "rgba(255,255,255,0.03)"; ctx.fillRect(X(r.start), pad.t, X(r.end) - X(r.start), ph); }
      ctx.fillStyle = css("--muted");
      ctx.fillText(r.label, X(r.apex ?? r.start) - 6, pad.t + 10);
    });

    // grid + axes labels
    ctx.strokeStyle = css("--line"); ctx.lineWidth = 1; ctx.fillStyle = css("--muted");
    for (let k = 0; k <= 4; k++) {
      const v = l1 + ((h1 - l1) * k) / 4, y = Y(v, "left");
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
      ctx.fillText((opts.fmt || ((x) => x.toFixed(0)))(v), 2, y + 3);
      if (hasRight) {
        const v2 = l2 + ((h2 - l2) * k) / 4;
        ctx.fillText((v2 >= 0 ? "+" : "") + v2.toFixed(2), w - pad.r + 4, Y(v2, "right") + 3);
      }
    }
    if (series.some((s) => s.axis === "right")) {
      ctx.strokeStyle = css("--muted"); ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(pad.l, Y(0, "right")); ctx.lineTo(w - pad.r, Y(0, "right")); ctx.stroke();
      ctx.setLineDash([]);
    }
    if (opts.zeroLine) {
      ctx.strokeStyle = css("--muted"); ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(pad.l, Y(0, "left")); ctx.lineTo(w - pad.r, Y(0, "left")); ctx.stroke();
      ctx.setLineDash([]);
    }

    series.forEach((s) => {
      if (!s.data || !s.data.length) return;
      const axis = s.axis || "left";
      ctx.beginPath();
      s.data.forEach((v, i) => { const x = X(i), y = Y(v, axis); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
      if (s.fill) {
        ctx.lineTo(X(s.data.length - 1), Y(0, axis)); ctx.lineTo(X(0), Y(0, axis)); ctx.closePath();
        ctx.fillStyle = s.fill; ctx.fill();
      } else {
        ctx.strokeStyle = s.color; ctx.lineWidth = s.width || 1.5; ctx.stroke();
      }
    });

    if (opts.cursor !== undefined && opts.cursor !== null) {
      const x = pad.l + opts.cursor * pw;
      ctx.strokeStyle = css("--text"); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, pad.t); ctx.lineTo(x, pad.t + ph); ctx.stroke();
    }
    return { X, Y, pad, pw, ph, n };
  }

  /** Track map coloured by per-bin delta change. */
  function trackMap(canvas, lat, lon, colourVals, opts = {}) {
    const { ctx, w, h } = setup(canvas);
    if (!lat || !lon) return;
    const cosLat = Math.cos((lat.reduce((a, b) => a + b, 0) / lat.length) * Math.PI / 180);
    const xs = lon.map((v) => v * cosLat), ys = lat;
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const s = Math.min((w - 20) / (maxX - minX || 1), (h - 20) / (maxY - minY || 1));
    const ox = (w - (maxX - minX) * s) / 2, oy = (h - (maxY - minY) * s) / 2;
    const P = (i) => [ox + (xs[i] - minX) * s, h - (oy + (ys[i] - minY) * s)];
    const maxAbs = Math.max(...colourVals.map(Math.abs), 1e-4);
    ctx.lineWidth = 5; ctx.lineCap = "round";
    for (let i = 1; i < xs.length; i++) {
      const v = colourVals[i] / maxAbs;
      const a = Math.min(1, Math.abs(v) * 1.5);
      ctx.strokeStyle = v > 0 ? `rgba(255,90,95,${0.25 + 0.75 * a})` : `rgba(51,194,127,${0.25 + 0.75 * a})`;
      const [x0, y0] = P(i - 1), [x1, y1] = P(i);
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
    }
    ctx.fillStyle = css("--text"); ctx.font = "11px Segoe UI, sans-serif";
    (opts.labels || []).forEach((l) => { const [x, y] = P(l.i); ctx.fillText(l.text, x + 6, y - 6); });
    const [sx, sy] = P(0);
    ctx.fillStyle = "#fff"; ctx.fillRect(sx - 2, sy - 6, 4, 12);
    if (opts.marker !== undefined) {
      const [mx, my] = P(opts.marker); ctx.fillStyle = css("--me");
      ctx.beginPath(); ctx.arc(mx, my, 6, 0, 2 * Math.PI); ctx.fill();
    }
  }

  /** Several lines on one map (e.g. your line vs the reference), optional zoom to a bin range. */
  function trackLines(canvas, lines, opts = {}) {
    const { ctx, w, h } = setup(canvas);
    const base = lines.find((l) => l.lat && l.lon); if (!base) return;
    const n = base.lat.length;
    const [a, b] = opts.range || [0, n - 1];
    const idx = []; for (let i = a; i <= b; i++) idx.push(((i % n) + n) % n);
    const cosLat = Math.cos((base.lat.reduce((p, q) => p + q, 0) / n) * Math.PI / 180);
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    lines.forEach((l) => idx.forEach((i) => {
      const x = l.lon[i] * cosLat, y = l.lat[i];
      minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    }));
    const s = Math.min((w - 24) / (maxX - minX || 1e-9), (h - 24) / (maxY - minY || 1e-9));
    const ox = (w - (maxX - minX) * s) / 2, oy = (h - (maxY - minY) * s) / 2;
    const P = (l, i) => [ox + (l.lon[i] * cosLat - minX) * s, h - (oy + (l.lat[i] - minY) * s)];
    lines.forEach((l) => {
      ctx.strokeStyle = l.color; ctx.lineWidth = l.width || 2; ctx.lineCap = "round"; ctx.beginPath();
      idx.forEach((i, k) => { const [x, y] = P(l, i); k ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
      ctx.stroke();
    });
    ctx.fillStyle = css("--text"); ctx.font = "11px Segoe UI, sans-serif";
    (opts.labels || []).forEach((lab) => {
      if (lab.i < a || lab.i > b) return;
      const [x, y] = P(base, lab.i); ctx.fillText(lab.text, x + 6, y - 6);
    });
    if (opts.scaleM) {                       // scale bar
      const metresPerDeg = 110540, px = (opts.scaleM / metresPerDeg) * s;
      ctx.strokeStyle = css("--muted"); ctx.lineWidth = 2; ctx.beginPath();
      ctx.moveTo(10, h - 10); ctx.lineTo(10 + px, h - 10); ctx.stroke();
      ctx.fillStyle = css("--muted"); ctx.fillText(opts.scaleM + " m", 14 + px, h - 6);
    }
  }

  return { line, trackMap, trackLines, css };
})();
