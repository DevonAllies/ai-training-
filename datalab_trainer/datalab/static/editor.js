/* A light code editor built on <textarea>: line numbers, Tab / Shift+Tab indenting,
 * auto-indent, Ctrl+/ comment toggle and run shortcuts. No external libraries,
 * so DataLab works offline.
 */
(function () {
  const COMMENT = { sql: "-- ", python: "# ", r: "# " };

  function create(host, { value = "", lang = "python", onRun, onCheck, onChange } = {}) {
    host.classList.add("editor");
    host.innerHTML = '<div class="gutter" aria-hidden="true"></div><textarea spellcheck="false" autocapitalize="off" autocomplete="off" wrap="off"></textarea>';
    const gutter = host.querySelector(".gutter");
    const ta = host.querySelector("textarea");
    ta.value = value;
    const indent = lang === "r" ? "  " : "    ";

    function lines() {
      const n = ta.value.split("\n").length;
      let s = "";
      for (let k = 1; k <= n; k++) s += k + "\n";
      gutter.textContent = s;
      gutter.scrollTop = ta.scrollTop;
    }

    function replaceRange(start, end, text, selStart, selEnd) {
      ta.setRangeText(text, start, end, "end");
      if (selStart !== undefined) ta.setSelectionRange(selStart, selEnd);
      ta.dispatchEvent(new Event("input"));
    }

    function lineBounds() {
      const v = ta.value;
      const s = v.lastIndexOf("\n", ta.selectionStart - 1) + 1;
      let e = v.indexOf("\n", ta.selectionEnd - (ta.selectionEnd > ta.selectionStart && v[ta.selectionEnd - 1] === "\n" ? 1 : 0));
      if (e === -1) e = v.length;
      return [s, e];
    }

    ta.addEventListener("keydown", (ev) => {
      const ctrl = ev.ctrlKey || ev.metaKey;
      if (ctrl && ev.key === "Enter") {
        ev.preventDefault();
        if (ev.shiftKey) onCheck && onCheck(); else onRun && onRun();
        return;
      }
      if (ctrl && ev.key === "/") {
        ev.preventDefault();
        const [s, e] = lineBounds();
        const c = COMMENT[lang] || "# ";
        const block = ta.value.slice(s, e).split("\n");
        const all = block.every(l => !l.trim() || l.trimStart().startsWith(c.trim()));
        const nb = block.map(l => {
          if (!l.trim()) return l;
          if (all) return l.replace(new RegExp("^(\\s*)" + c.trim().replace(/[-#]/g, "\\$&") + " ?"), "$1");
          return l.replace(/^(\s*)/, "$1" + c);
        }).join("\n");
        replaceRange(s, e, nb, s, s + nb.length);
        return;
      }
      if (ev.key === "Tab") {
        ev.preventDefault();
        const multi = ta.value.slice(ta.selectionStart, ta.selectionEnd).includes("\n");
        if (!multi && !ev.shiftKey) { replaceRange(ta.selectionStart, ta.selectionEnd, indent); return; }
        const [s, e] = lineBounds();
        const block = ta.value.slice(s, e).split("\n");
        const nb = block.map(l => ev.shiftKey ? l.replace(new RegExp("^( {1," + indent.length + "}|\\t)"), "") : indent + l).join("\n");
        replaceRange(s, e, nb, s, s + nb.length);
        return;
      }
      if (ev.key === "Enter" && !ev.shiftKey && !ctrl) {
        const v = ta.value;
        const s = v.lastIndexOf("\n", ta.selectionStart - 1) + 1;
        const cur = v.slice(s, ta.selectionStart);
        let pad = (cur.match(/^\s*/) || [""])[0];
        if (/[:({[]\s*$/.test(cur) || (lang === "r" && /\{\s*$/.test(cur))) pad += indent;
        ev.preventDefault();
        replaceRange(ta.selectionStart, ta.selectionEnd, "\n" + pad);
      }
    });
    ta.addEventListener("input", () => { lines(); onChange && onChange(ta.value); });
    ta.addEventListener("scroll", () => { gutter.scrollTop = ta.scrollTop; });
    lines();

    return {
      get value() { return ta.value; },
      set value(v) { ta.value = v; lines(); },
      focus() { ta.focus(); },
      textarea: ta,
    };
  }

  window.Editor = { create };
})();
