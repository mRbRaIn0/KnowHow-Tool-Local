// Kompakter Markdown-Renderer mit Obsidian-Syntax.
// Bewusst selbst geschrieben: keine CDN-Abhängigkeit, WikiLinks und Embeds
// werden direkt unterstützt.

import { esc } from './util.js';

const PLACEHOLDER = String.fromCharCode(0);

/** Trennt YAML-Frontmatter vom Inhalt (Obsidian legt dort Metadaten ab). */
export function splitFrontmatter(text) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text || '');
  if (!match) return { frontmatter: null, body: text || '' };
  const frontmatter = {};
  for (const line of match[1].split(/\r?\n/)) {
    const pair = /^([A-Za-z0-9_-]+)\s*:\s*(.*)$/.exec(line.trim());
    if (pair) frontmatter[pair[1]] = pair[2];
  }
  return { frontmatter, body: (text || '').slice(match[0].length) };
}

/** Alle WikiLinks und Embeds eines Textes — Basis für die Kontextspalte. */
export function collectLinks(text) {
  const links = [];
  const pattern = /(!?)\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]/g;
  let match;
  while ((match = pattern.exec(text || '')) !== null) {
    links.push({ embed: match[1] === '!', target: match[2].trim(), alias: (match[3] || '').trim() });
  }
  return links;
}

export function renderMarkdown(text, options = {}) {
  const { body } = splitFrontmatter(text || '');
  const lines = body.replace(/\r\n/g, '\n').split('\n');
  const out = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];

    // Codeblock
    const fence = /^(\s*)(```+|~~~+)\s*([\w+#.-]*)\s*$/.exec(line);
    if (fence) {
      const marker = fence[2][0].repeat(3);
      const language = fence[3] || '';
      const buffer = [];
      index += 1;
      while (index < lines.length && !new RegExp(`^\\s*${marker}`).test(lines[index])) {
        buffer.push(lines[index]);
        index += 1;
      }
      index += 1;
      out.push(
        `<pre><button class="copy-code" type="button">Kopieren</button>` +
        `<code${language ? ` class="lang-${esc(language)}"` : ''}>${esc(buffer.join('\n'))}</code></pre>`,
      );
      continue;
    }

    if (!line.trim()) { index += 1; continue; }

    // Überschrift
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = Math.min(heading[1].length, 6);
      out.push(`<h${level}>${inline(heading[2].trim(), options)}</h${level}>`);
      index += 1;
      continue;
    }

    // Trennlinie
    if (/^\s*([-*_])\s*(\1\s*){2,}$/.test(line)) { out.push('<hr>'); index += 1; continue; }

    // Zitat
    if (/^\s*>/.test(line)) {
      const buffer = [];
      while (index < lines.length && /^\s*>/.test(lines[index])) {
        buffer.push(lines[index].replace(/^\s*>\s?/, ''));
        index += 1;
      }
      out.push(`<blockquote>${renderMarkdown(buffer.join('\n'), options)}</blockquote>`);
      continue;
    }

    // Tabelle
    if (line.includes('|') && index + 1 < lines.length && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(lines[index + 1])) {
      const header = splitRow(line);
      const align = splitRow(lines[index + 1]).map((cell) => {
        const left = cell.startsWith(':');
        const right = cell.endsWith(':');
        if (left && right) return 'center';
        if (right) return 'right';
        return left ? 'left' : '';
      });
      index += 2;
      const rows = [];
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        rows.push(splitRow(lines[index]));
        index += 1;
      }
      const th = header.map((cell, i) => `<th${align[i] ? ` style="text-align:${align[i]}"` : ''}>${inline(cell, options)}</th>`).join('');
      const tb = rows.map((row) =>
        `<tr>${header.map((_, i) => `<td${align[i] ? ` style="text-align:${align[i]}"` : ''}>${inline(row[i] ?? '', options)}</td>`).join('')}</tr>`,
      ).join('');
      out.push(`<table><thead><tr>${th}</tr></thead><tbody>${tb}</tbody></table>`);
      continue;
    }

    // Liste
    if (/^\s*([-*+]|\d+[.)])\s+/.test(line)) {
      const [html, next] = renderList(lines, index, options);
      out.push(html);
      index = next;
      continue;
    }

    // Absatz
    const buffer = [];
    while (index < lines.length && lines[index].trim()
      && !/^\s*(```|~~~|#{1,6}\s|>|([-*+]|\d+[.)])\s)/.test(lines[index])) {
      buffer.push(lines[index]);
      index += 1;
    }
    if (buffer.length) out.push(`<p>${inline(buffer.join('\n'), options).replace(/\n/g, '<br>')}</p>`);
    else index += 1;
  }

  return out.join('\n');
}

function splitRow(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim());
}

function indentOf(line) {
  const match = /^(\s*)/.exec(line);
  return match[1].replace(/\t/g, '    ').length;
}

function renderList(lines, start, options) {
  const baseIndent = indentOf(lines[start]);
  const ordered = /^\s*\d+[.)]\s/.test(lines[start]);
  const items = [];
  let index = start;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      // Leerzeile beendet die Liste, wenn danach kein Listenpunkt folgt.
      const next = lines[index + 1];
      if (!next || !/^\s*([-*+]|\d+[.)])\s+/.test(next) || indentOf(next) < baseIndent) break;
      index += 1;
      continue;
    }
    const indent = indentOf(line);
    if (indent < baseIndent || !/^\s*([-*+]|\d+[.)])\s+/.test(line)) {
      if (indent > baseIndent && items.length) { items[items.length - 1].extra.push(line.trim()); index += 1; continue; }
      break;
    }
    if (indent > baseIndent) {
      const [html, next] = renderList(lines, index, options);
      if (items.length) items[items.length - 1].children.push(html);
      index = next;
      continue;
    }
    items.push({ text: line.replace(/^\s*([-*+]|\d+[.)])\s+/, ''), children: [], extra: [] });
    index += 1;
  }

  const rendered = items.map((item) => {
    const task = /^\[( |x|X)\]\s+(.*)$/.exec(item.text);
    const parts = [];
    let cls = '';
    if (task) {
      cls = ' class="task"';
      parts.push(`<input type="checkbox" disabled${task[1].toLowerCase() === 'x' ? ' checked' : ''}> ${inline(task[2], options)}`);
    } else {
      parts.push(inline(item.text, options));
    }
    if (item.extra.length) parts.push(`<br>${inline(item.extra.join('\n'), options)}`);
    return `<li${cls}>${parts.join('')}${item.children.join('')}</li>`;
  }).join('');

  const tag = ordered ? 'ol' : 'ul';
  return [`<${tag}>${rendered}</${tag}>`, index];
}

/* ------------------------------------------------------- Inline */

function inline(raw, options) {
  const stash = [];
  const keep = (html) => `${PLACEHOLDER}${stash.push(html) - 1}${PLACEHOLDER}`;

  let text = esc(raw);

  // Inline-Code zuerst sichern, damit darin nichts weiter interpretiert wird.
  text = text.replace(/(`+)([\s\S]*?)\1/g, (_, __, code) => keep(`<code>${code}</code>`));

  // Obsidian-Embed: ![[Datei]]
  text = text.replace(/!\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]/g,
    (_, target, __, alias) => keep(renderEmbed(target.trim(), alias, options)));

  // Obsidian-WikiLink: [[Notiz|Titel]]
  text = text.replace(/\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]/g, (_, target, anchor, alias) => {
    const clean = target.trim();
    const label = (alias || clean).trim() + (anchor ? ` › ${anchor.trim()}` : '');
    const resolved = options.resolveLink?.(clean) ?? null;
    return keep(
      `<a class="wikilink" href="#" data-wikilink="${esc(clean)}"` +
      `${resolved ? ` data-path="${esc(resolved)}"` : ' data-missing="1"'}>${label}</a>`,
    );
  });

  // Bilder und Links im Standard-Markdown
  text = text.replace(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g,
    (_, alt, src) => keep(`<img src="${esc(resolveSrc(src, options))}" alt="${esc(alt)}" loading="lazy">`));
  text = text.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, (_, label, href) => {
    const safe = safeHref(href, options);
    if (!safe) return keep(`<span title="Externer Link im Offline-Modus blockiert">${label}</span>`);
    const external = /^https?:/i.test(safe);
    return keep(`<a href="${esc(safe)}"${external ? ' target="_blank" rel="noreferrer noopener"' : ''}>${label}</a>`);
  });

  text = text
    .replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[\s(])__([^_]+)__/g, '$1<strong>$2</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/(^|[\s(])_([^_\n]+)_/g, '$1<em>$2</em>')
    .replace(/~~([^~]+)~~/g, '<del>$1</del>')
    .replace(/==([^=]+)==/g, '<mark>$1</mark>');

  return text.replace(new RegExp(`${PLACEHOLDER}(\\d+)${PLACEHOLDER}`, 'g'), (_, i) => stash[Number(i)]);
}

const IMAGE_RE = /\.(png|jpe?g|webp|gif|bmp|svg|tiff?)$/i;

function renderEmbed(target, alias, options) {
  const resolved = options.resolveLink?.(target) ?? null;
  if (IMAGE_RE.test(target)) {
    if (!resolved) {
      return `<span class="attach-file" title="Datei nicht im Vault gefunden">${esc(target)}</span>`;
    }
    return `<figure class="embed"><img src="/api/files/raw?path=${encodeURIComponent(resolved)}" ` +
      `alt="${esc(alias || target)}" loading="lazy">` +
      `<figcaption class="embed__caption">${esc(target)}</figcaption></figure>`;
  }
  const attrs = resolved ? ` data-path="${esc(resolved)}"` : ' data-missing="1"';
  return `<a class="wikilink" href="#" data-wikilink="${esc(target)}"${attrs}>${esc(alias || target)}</a>`;
}

function resolveSrc(src, options) {
  if (/^(https?:|data:|blob:)/i.test(src)) return src;
  const resolved = options.resolveLink?.(decodeURIComponent(src)) ?? null;
  return resolved ? `/api/files/raw?path=${encodeURIComponent(resolved)}` : src;
}

function safeHref(href, options) {
  if (/^(javascript|vbscript|file):/i.test(href.trim())) return null;
  if (/^https?:/i.test(href) && options.blockExternal) return null;
  return href;
}
