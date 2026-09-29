// Kleine DOM- und Formatierungshelfer. Bewusst ohne Framework.

import { locale, t } from './i18n.js';

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

/**
 * Ersetzt den Inhalt eines Elements. Anders als replaceChildren()/append() werden
 * null, undefined und false ausgelassen — sie erschienen sonst als Text „null“.
 */
export function fill(host, ...children) {
  host.replaceChildren(...children.flat().filter((child) => child !== null && child !== undefined && child !== false));
  return host;
}

/** Ein Wert ist anzeigbar, wenn er nicht leer und kein technischer Platzhalter ist. */
export function hasValue(value) {
  if (value === null || value === undefined || value === false) return false;
  const text = String(value).trim();
  return text !== '' && text !== 'null' && text !== 'undefined' && text !== 'NaN';
}

/** Beschriftete Wertepaare (<dl>); Felder ohne Wert werden komplett ausgeblendet. */
export function kv(rows) {
  const items = rows.filter(([, value]) => hasValue(value));
  if (!items.length) return null;
  return h('dl', { class: 'ctx-kv' }, ...items.flatMap(([label, value]) =>
    [h('dt', { text: label }), h('dd', { text: String(value) })]));
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
  if (diff < 60) return t('time.now');
  if (diff < 3600) return t('time.minutesAgo', { n: Math.floor(diff / 60) });
  if (diff < 86400) return t('time.hoursAgo', { n: Math.floor(diff / 3600) });
  if (diff < 604800) return t('time.daysAgo', { n: Math.floor(diff / 86400) });
  return date.toLocaleDateString(locale(), { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export function fmtTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' });
}

export function fmtBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${value >= 100 || index === 0 ? Math.round(value) : value.toFixed(1)} ${units[index]}`;
}

export function fmtNumber(value) {
  return new Intl.NumberFormat(locale()).format(value ?? 0);
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

const KIND_TITLE = { ok: 'toast.done', bad: 'toast.error', info: 'toast.info' };

export function toast(message, kind = 'info', title = '') {
  const host = document.getElementById('toasts');
  const node = h('div', { class: `toast toast--${kind}` },
    h('div', { class: 'toast__body' },
      h('strong', { text: title || t(KIND_TITLE[kind] || 'toast.info') }),
      h('span', { text: message })),
    h('button', { class: 'icon-btn', title: t('common.close'), onclick: () => node.remove() },
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

  const titleId = `modal-title-${Date.now()}`;
  const modal = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': titleId },
    h('div', { class: 'modal__head' }, h('h2', { id: titleId, text: title }), description ? h('p', { text: description }) : null),
    h('div', { class: 'modal__body' }, body),
    actions.length ? foot : null,
  );

  root.append(modal);
  root.onclick = (event) => { if (event.target === root) close(); };
  setTimeout(() => modal.querySelector('input, textarea, button')?.focus(), 30);
  return { close, modal };
}

export function confirmDialog({ title, message, confirmLabel = t('common.confirm'), danger = false }) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value, close) => { settled = true; resolve(value); close(); };
    openModal({
      title,
      body: h('p', { text: message, style: 'margin:0;color:var(--text-2)' }),
      actions: [
        { label: t('common.cancel'), onClick: (close) => finish(false, close) },
        { label: confirmLabel, variant: danger ? 'danger' : 'primary', onClick: (close) => finish(true, close) },
      ],
      onClose: () => { if (!settled) resolve(false); },
    });
  });
}

export function promptDialog({ title, description = '', label, value = '', confirmLabel = t('common.save'), mono = false }) {
  return new Promise((resolve) => {
    let settled = false;
    const input = h('input', { class: `input ${mono ? 'input--mono' : ''}`, value });
    const form = h('div', {}, h('div', { class: 'field' }, h('span', { class: 'label', text: label }), input));
    const finish = (result, close) => { settled = true; resolve(result); close(); };
    const { close } = openModal({
      title, description, body: form,
      actions: [
        { label: t('common.cancel'), onClick: (c) => finish(null, c) },
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
    toast(t('common.copied'), 'ok');
  } catch {
    // Fallback für Kontexte ohne Clipboard-API.
    const area = h('textarea', { style: 'position:fixed;opacity:0' });
    area.value = text;
    document.body.append(area);
    area.select();
    document.execCommand('copy');
    area.remove();
    toast(t('common.copied'), 'ok');
  }
}

export function debounce(fn, wait = 200) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}
