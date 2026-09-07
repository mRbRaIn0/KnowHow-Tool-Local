// Kleine DOM- und Formatierungshelfer. Bewusst ohne Framework.

export function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'html') node.innerHTML = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === 'dataset') {
      for (const [k, v] of Object.entries(value)) node.dataset[k] = v;
    } else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function icon(name, cls = '') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  if (cls) svg.setAttribute('class', cls);
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
}

export function esc(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

export function fmtDate(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 60) return 'gerade eben';
  if (diff < 3600) return `vor ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `vor ${Math.floor(diff / 3600)} h`;
  if (diff < 604800) return `vor ${Math.floor(diff / 86400)} T`;
  return date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export function fmtTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
}

export function fmtBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${value >= 100 || index === 0 ? Math.round(value) : value.toFixed(1)} ${units[index]}`;
}

export function fmtNumber(value) {
  return new Intl.NumberFormat('de-DE').format(value ?? 0);
}

export function baseName(path) {
  return String(path || '').split('/').pop();
}

export function parentDir(path) {
  const parts = String(path || '').split('/');
  parts.pop();
  return parts.join('/');
}

/* --------------------------------------------------------- Toasts */

const KIND_TITLE = { ok: 'Erledigt', bad: 'Fehler', info: 'Hinweis' };

export function toast(message, kind = 'info', title = '') {
  const host = document.getElementById('toasts');
  const node = h('div', { class: `toast toast--${kind}` },
    h('div', { class: 'toast__body' },
      h('strong', { text: title || KIND_TITLE[kind] || 'Hinweis' }),
      h('span', { text: message })),
    h('button', { class: 'icon-btn', title: 'Schließen', onclick: () => node.remove() },
      h('span', { text: '×', style: 'font-size:17px;line-height:1' })),
  );
  host.append(node);
  setTimeout(() => node.remove(), kind === 'bad' ? 9000 : 4500);
  return node;
}

/* ---------------------------------------------------------- Modal */

export function openModal({ title, description = '', body, actions = [], onClose = null }) {
  const root = document.getElementById('modal-root');
  clear(root);
  root.hidden = false;

  const close = () => {
    root.hidden = true;
    clear(root);
    document.removeEventListener('keydown', onKey);
    if (onClose) onClose();
  };
  const onKey = (event) => { if (event.key === 'Escape') close(); };
  document.addEventListener('keydown', onKey);

  const foot = h('div', { class: 'modal__foot' });
  for (const action of actions) {
    foot.append(h('button', {
      class: `btn ${action.variant ? `btn--${action.variant}` : ''}`,
      onclick: () => action.onClick?.(close),
    }, action.label));
  }

  const modal = h('div', { class: 'modal' },
    h('div', { class: 'modal__head' }, h('h2', { text: title }), description ? h('p', { text: description }) : null),
    h('div', { class: 'modal__body' }, body),
    actions.length ? foot : null,
  );

  root.append(modal);
  root.onclick = (event) => { if (event.target === root) close(); };
  setTimeout(() => modal.querySelector('input, textarea, button')?.focus(), 30);
  return { close, modal };
}

export function confirmDialog({ title, message, confirmLabel = 'Bestätigen', danger = false }) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value, close) => { settled = true; resolve(value); close(); };
    openModal({
      title,
      body: h('p', { text: message, style: 'margin:0;color:var(--text-2)' }),
      actions: [
        { label: 'Abbrechen', onClick: (close) => finish(false, close) },
        { label: confirmLabel, variant: danger ? 'danger' : 'primary', onClick: (close) => finish(true, close) },
      ],
      onClose: () => { if (!settled) resolve(false); },
    });
  });
}

export function promptDialog({ title, description = '', label, value = '', confirmLabel = 'Speichern', mono = false }) {
  return new Promise((resolve) => {
    let settled = false;
    const input = h('input', { class: `input ${mono ? 'input--mono' : ''}`, value });
    const form = h('div', {}, h('div', { class: 'field' }, h('span', { class: 'label', text: label }), input));
    const finish = (result, close) => { settled = true; resolve(result); close(); };
    const { close } = openModal({
      title, description, body: form,
      actions: [
        { label: 'Abbrechen', onClick: (c) => finish(null, c) },
        { label: confirmLabel, variant: 'primary', onClick: (c) => finish(input.value.trim() || null, c) },
      ],
      onClose: () => { if (!settled) resolve(null); },
    });
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') { event.preventDefault(); finish(input.value.trim() || null, close); }
    });
  });
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('In die Zwischenablage kopiert.', 'ok');
  } catch {
    // Fallback für Kontexte ohne Clipboard-API.
    const area = h('textarea', { style: 'position:fixed;opacity:0' });
    area.value = text;
    document.body.append(area);
    area.select();
    document.execCommand('copy');
    area.remove();
    toast('In die Zwischenablage kopiert.', 'ok');
  }
}

export function debounce(fn, wait = 200) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}
