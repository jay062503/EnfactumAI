/* Minimal, XSS-safe Markdown renderer: all input is HTML-escaped before any markup is produced. */
(function () {
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const safeUrl = (u) => /^(https?:\/\/|mailto:)/i.test(u.replace(/&amp;/g, "&"));
  const LIST = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
  const TABLE_SEP = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;

  function inline(text) {
    const codes = [];
    text = text.replace(/`([^`\n]+)`/g, (_, c) => { codes.push(c); return `\u0001${codes.length - 1}\u0001`; });
    text = text.replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g, (m, label, url) =>
      safeUrl(url) ? `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>` : label);
    text = text.replace(/(^|[\s(])(https?:\/\/[^\s<)]+[^\s<).,;:!?])/g,
      (m, pre, url) => `${pre}<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`);
    text = text.replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>").replace(/__([^_\n]+?)__/g, "<strong>$1</strong>");
    text = text.replace(/(^|[^*\w])\*([^*\n]+?)\*(?!\*)/g, "$1<em>$2</em>");
    text = text.replace(/(^|[^_\w])_([^_\n]+?)_(?![_\w])/g, "$1<em>$2</em>");
    text = text.replace(/~~([^~\n]+)~~/g, "<del>$1</del>");
    text = text.replace(/\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\](?!\()/g, (m, nums) =>
      nums.split(",").map((n) => `<button type="button" class="cite" data-n="${n.trim()}">${n.trim()}</button>`).join(""));
    return text.replace(/\u0001(\d+)\u0001/g, (_, i) => `<code>${codes[+i]}</code>`);
  }

  const cells = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => inline(c.trim()));

  function render(src) {
    const blocks = [];
    src = (src || "").replace(/\r\n?/g, "\n").replace(/```([\w+#.-]*)[^\n]*\n([\s\S]*?)(?:```|$)/g, (m, lang, code) => {
      blocks.push({ lang, code: code.replace(/\n$/, "") });
      return `\n\u0002${blocks.length - 1}\u0002\n`;
    });
    const lines = esc(src).split("\n");
    let html = "", i = 0;
    const para = [];
    const flush = () => {
      if (para.length) { html += `<p>${inline(para.join("\n")).replace(/\n/g, "<br>")}</p>`; para.length = 0; }
    };

    function list() {
      let out = "";
      const stack = [];
      while (i < lines.length) {
        const l = lines[i];
        const m = l.match(LIST);
        if (!m) {
          if (!l.trim()) {
            if (i + 1 < lines.length && LIST.test(lines[i + 1])) { i++; continue; }
            break;
          }
          if (/^\s{2,}/.test(l) && stack.length) { out += "<br>" + inline(l.trim()); i++; continue; }
          break;
        }
        const indent = m[1].replace(/\t/g, "    ").length;
        const type = /\d/.test(m[2]) ? "ol" : "ul";
        while (stack.length > 1 && indent < stack[stack.length - 1].indent) out += `</li></${stack.pop().type}>`;
        const top = stack[stack.length - 1];
        if (!top || indent > top.indent + 1) {
          const n = parseInt(m[2], 10);
          out += `<${type}${type === "ol" && n > 1 ? ` start="${n}"` : ""}>`;
          stack.push({ indent, type });
        } else if (top.type !== type) {
          out += `</li></${top.type}><${type}>`;
          top.type = type;
        } else {
          out += "</li>";
        }
        out += `<li>${inline(m[3])}`;
        i++;
      }
      while (stack.length) out += `</li></${stack.pop().type}>`;
      return out;
    }

    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();
      let m;
      if (/^\u0002\d+\u0002$/.test(trimmed)) {
        flush();
        const b = blocks[+trimmed.slice(1, -1)];
        html += `<div class="code"><div class="code-head"><span>${esc(b.lang || "code")}</span>` +
          `<button type="button" class="copy-code">Copy</button></div><pre><code>${esc(b.code)}</code></pre></div>`;
        i++;
      } else if (!trimmed) {
        flush(); i++;
      } else if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
        flush();
        const lvl = Math.min(m[1].length + 1, 6);
        html += `<h${lvl}>${inline(m[2])}</h${lvl}>`;
        i++;
      } else if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
        flush(); html += "<hr>"; i++;
      } else if (line.startsWith("&gt;")) {
        flush();
        const q = [];
        while (i < lines.length && lines[i].startsWith("&gt;")) q.push(inline(lines[i++].replace(/^&gt;\s?/, "")));
        html += `<blockquote>${q.join("<br>")}</blockquote>`;
      } else if (line.includes("|") && i + 1 < lines.length && TABLE_SEP.test(lines[i + 1]) && lines[i + 1].includes("-")) {
        flush();
        const head = cells(line);
        i += 2;
        let body = "";
        while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
          body += `<tr>${cells(lines[i++]).map((c) => `<td>${c}</td>`).join("")}</tr>`;
        }
        html += `<div class="table-wrap"><table><thead><tr>${head.map((c) => `<th>${c}</th>`).join("")}</tr></thead>` +
          `<tbody>${body}</tbody></table></div>`;
      } else if (LIST.test(line)) {
        flush(); html += list();
      } else {
        para.push(line); i++;
      }
    }
    flush();
    return html;
  }

  window.Markdown = { render, escape: esc };
})();
