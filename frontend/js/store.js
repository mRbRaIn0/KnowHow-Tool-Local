// Gemeinsamer Zustand: Systemstatus, Dateiindex, Navigation, Design.

import { api } from './api.js';

export const state = {
  status: null,
  settings: null,
  files: [],
  chats: [],
  activeChatId: null,
  activeFilePath: null,
  contextVisible: true,
  busy: false,
  vaultRevision: 0,
};

const listeners = new Map();

export function on(event, handler) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(handler);
  return () => listeners.get(event).delete(handler);
}

export function emit(event, payload) {
  for (const handler of listeners.get(event) || []) {
    try { handler(payload); } catch (error) { console.error(error); }
  }
}

/* ------------------------------------------------------- Status */

let statusTicket = 0;
export async function refreshStatus() {
  const ticket = ++statusTicket;
  try {
    const status = await api.status();
    if (ticket !== statusTicket) return state.status;
    state.status = status;
    emit('status', state.status);
  } catch (error) {
    if (ticket !== statusTicket) return state.status;
    state.status = null;
    emit('status', null);
  }
  return state.status;
}

export function vaultReady() {
  return Boolean(state.status?.vault?.ok);
}

export function modelReady() {
  return Boolean(state.status?.ollama?.online && state.status?.model?.installed);
}

/* --------------------------------------------------- Dateiindex */

let fileMaps = { byPath: new Map(), byName: new Map(), byStem: new Map() };

export async function refreshFileIndex() {
  if (!vaultReady()) {
    state.files = [];
    fileMaps = { byPath: new Map(), byName: new Map(), byStem: new Map() };
    emit('files', state.files);
    return state.files;
  }
  try {
    const data = await api.get('/api/files/index');
    state.files = data.files || [];
  } catch {
    state.files = [];
  }
  const byPath = new Map();
  const byName = new Map();
  const byStem = new Map();
  for (const file of state.files) {
    byPath.set(file.path.toLowerCase(), file.path);
    if (!byName.has(file.name.toLowerCase())) byName.set(file.name.toLowerCase(), file.path);
    if (!byStem.has(file.stem.toLowerCase())) byStem.set(file.stem.toLowerCase(), file.path);
  }
  fileMaps = { byPath, byName, byStem };
  emit('files', state.files);
  return state.files;
}

/** Meldet Änderungen, die außerhalb der App (vor allem in Obsidian) entstanden. */
export async function refreshVaultChanges() {
  if (!vaultReady()) return null;
  try {
    const data = await api.fileChanges(state.vaultRevision);
    const previous = state.vaultRevision;
    state.vaultRevision = data.revision || previous;
    if (data.changed && (data.events || []).length) {
      await refreshFileIndex();
      emit('vault:changed', data);
    }
    return data;
  } catch {
    return null;
  }
}

/** Löst ein WikiLink-Ziel auf einen echten Vault-Pfad auf. */
export function resolveLink(target) {
  if (!target) return null;
  const clean = String(target).replace(/\\/g, '/').replace(/^\.\//, '').trim().toLowerCase();
  const { byPath, byName, byStem } = fileMaps;
  return byPath.get(clean)
    || byPath.get(`${clean}.md`)
    || byName.get(clean)
    || byName.get(clean.split('/').pop())
    || byStem.get(clean)
    || byStem.get(clean.split('/').pop())
    || null;
}

export function blockExternal() {
  return Boolean(state.status?.privacy?.block_external_urls ?? true);
}

export const markdownOptions = () => ({ resolveLink, blockExternal: blockExternal() });

/* ----------------------------------------------------- Navigation */

export function navigate(route) {
  const next = route.startsWith('#') ? route : `#${route}`;
  if (location.hash === next) emit('route', parseRoute());
  else location.hash = next;
}

export function parseRoute() {
  const raw = location.hash.replace(/^#\/?/, '') || 'dashboard';
  const [pathPart, queryPart] = raw.split('?');
  const segments = pathPart.split('/').filter(Boolean);
  const params = Object.fromEntries(new URLSearchParams(queryPart || ''));
  return { view: segments[0] || 'dashboard', id: segments[1] ? decodeURIComponent(segments[1]) : '', params };
}

/* --------------------------------------------------------- Design */

export function applyTheme(theme) {
  const resolved = theme === 'system'
    ? (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark')
    : theme;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themePreference = theme;
}

// Jedes Profil bekommt eine eigene Kantenfarbe — privat und geschäftlich
// sind so auf einen Blick auseinanderzuhalten.
const TONES = ['#3ab3bf', '#c98a3c', '#8a7fd4', '#5aa469', '#c9647d'];

export function profileTone(profileId, profiles = []) {
  const index = Math.max(0, profiles.findIndex((p) => p.id === profileId));
  return TONES[index % TONES.length];
}
