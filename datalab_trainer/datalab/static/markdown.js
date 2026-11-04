/* Small Markdown renderer for lessons and reports (no external libraries).
 * Supports headings, paragraphs, **bold**, *italic*, `code`, links, images, tables,
 * lists (incl. "- [ ]" task items), blockquotes, rules and fenced code.
 * Consecutive ```sql / ```python / ```r fences are grouped into one tabbed block.
 */
(function () {
  const LANG_NAMES = { sql: "SQL", python: "Python", r: "R" };

  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function inline(s) {
    const codes = [];
    s = s.replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return "\u0000" + (codes.length - 1) + "\u0000"; });
    s = esc(s);
    s = s.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_, alt, src) => {
      const ok = /^(data:image\/|\/figures\/|https?:)/.test(src);
      return ok ? `<img alt="${alt}" src="${src}">` : alt;
    });
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, t, href) => {
      const ok = /^(https?:|#|\/)/.test(href);
      return ok ? `<a href="${href}"${href.startsWith("http") ? ' target="_blank" rel="noopener"' : ""}>${t}</a>` : t;
    });
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*\w])\*([^*\s][^*]*)\*(?!\w)/g, "$1<em>$2</em>");
    s = s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${esc(codes[+i])}</code>`);
    return s;
  }

  function tableRow(line) {
    let l = line.trim();
    if (l.startsWith("|")) l = l.slice(1);
    if (l.endsWith("|")) l = l.slice(0, -1);
    return l.split("|").map(c => c.trim());
  }

  function codeBlock(lang, code) {
    const cls = lang ? ` class="lang-${esc(lang)}"` : "";
    return `<pre${cls}><code>${esc(code)}</code></pre>`;
  }

  function render(md) {
    const lines = md.replace(/\r\n/g, "\n").split("\n");
    const out = [];
    let i = 0;
    let para = [];
    const flush = () => { if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; } };

    while (i < lines.length) {
      const line = lines[i];
      const fence = line.match(/^```\s*([\w+-]*)\s*$/);
      if (fence) {
        flush();
        // collect one or more consecutive fences (for language tabs)
        const blocks = [];
        while (i < lines.length && /^```/.test(lines[i])) {
          const lang = (lines[i].match(/^```\s*([\w+-]*)/) || [])[1] || "";
          i++;
          const buf = [];
          while (i < lines.length && !/^```\s*$/.test(lines[i])) buf.push(lines[i++]);
          i++; // closing fence
          blocks.push({ lang: lang.toLowerCase(), code: buf.join("\n") });
          // allow blank lines between grouped fences? no: must be adjacent
        }
        const tabbable = blocks.length > 1 && blocks.every(b => LANG_NAMES[b.lang]);
        if (tabbable) {
          const id = "t" + Math.random().toString(36).slice(2, 8);
          const tabs = blocks.map(b => `<button class="tab" data-lang="${b.lang}">${LANG_NAMES[b.lang]}</button>`).join("");
          const panes = blocks.map(b => `<div class="pane" data-lang="${b.lang}">${codeBlock(b.lang, b.code)}</div>`).join("");
          out.push(`<div class="langtabs" id="${id}"><div class="tabbar">${tabs}<button class="copy" title="Copy code">Copy</button></div>${panes}</div>`);
        } else {
          blocks.forEach(b => out.push(`<div class="codewrap">${codeBlock(b.lang, b.code)}<button class="copy" title="Copy code">Copy</button></div>`));
        }
        continue;
      }
      if (/^\s*$/.test(line)) { flush(); i++; continue; }
      const h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) { flush(); out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); i++; continue; }
      if (/^(-{3,}|\*{3,})\s*$/.test(line)) { flush(); out.push("<hr>"); i++; continue; }
      if (/^\s*\|/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
        flush();
        const head = tableRow(line);
        const align = tableRow(lines[i + 1]).map(c => c.endsWith(":") ? (c.startsWith(":") ? "center" : "right") : "");
        i += 2;
        const rows = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(tableRow(lines[i++]));
        const th = head.map((c, k) => `<th${align[k] ? ` style="text-align:${align[k]}"` : ""}>${inline(c)}</th>`).join("");
        const tb = rows.map(r => "<tr>" + r.map((c, k) => `<td${align[k] ? ` style="text-align:${align[k]}"` : ""}>${inline(c)}</td>`).join("") + "</tr>").join("");
        out.push(`<div class="tablewrap"><table><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table></div>`);
        continue;
      }
      if (/^>\s?/.test(line)) {
        flush();
        const buf = [];
        while (i < lines.length && /^>\s?/.test(lines[i])) buf.push(lines[i++].replace(/^>\s?/, ""));
        out.push(`<blockquote>${render(buf.join("\n"))}</blockquote>`);
        continue;
      }
      const li = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
      if (li) {
        flush();
        const ordered = /\d/.test(li[2]);
        const items = [];
        while (i < lines.length) {
          const m = lines[i].match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
          if (m) { items.push(m[3]); i++; continue; }
          if (/^\s{2,}\S/.test(lines[i]) && items.length) { items[items.length - 1] += " " + lines[i].trim(); i++; continue; }
          break;
        }
        const tag = ordered ? "ol" : "ul";
        out.push(`<${tag}>` + items.map(t => {
          const task = t.match(/^\[( |x)\]\s+(.*)$/i);
          if (task) return `<li class="task"><input type="checkbox" ${task[1].toLowerCase() === "x" ? "checked" : ""}> ${inline(task[2])}</li>`;
          return `<li>${inline(t)}</li>`;
        }).join("") + `</${tag}>`);
        continue;
      }
      para.push(line.trim());
      i++;
    }
    flush();
    return out.join("\n");
  }

  window.Markdown = { render, esc, inline };
})();
