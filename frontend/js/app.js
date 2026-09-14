// Anwendungsgerüst: Statusleiste, Navigation, Routing.

import { api } from './api.js';
import { clear, debounce, h, toast } from './util.js';
import {
  applyTheme, emit, navigate, on, parseRoute, profileTone,
  refreshFileIndex, refreshStatus, refreshVaultChanges, state,
} from './store.js';

import { runningChatIds } from './chatstream.js';

// Ansichten werden erst beim Öffnen geladen. Ein Fehler in einer einzelnen
// Unterseite darf nicht mehr das komplette Anwendungsgerüst blockieren.
const VIEW_LOADERS = {
  dashboard: () => import('./views/dashboard.js'),
  chat: () => import('./views/chat.js'),
  ask: () => import('./views/chat.js'),
  files: () => import('./views/files.js'),
  search: () => import('./views/search.js'),
  settings: () => import('./views/settings.js'),
  knowledge: () => import('./views/knowledge.js'),
  images: () => import('./views/images.js'),
  notes: () => import('./views/notes.js'),
  templates: () => import('./views/templates.js'),
};
const viewCache = new Map();

const el = {
  main: document.getElementById('main'),
  rail: document.getElementById('rail-panel'),
  context: document.getElementById('context-inner'),
  workspace: document.getElementById('workspace'),
  nav: document.getElementById('nav'),
  searchForm: document.getElementById('omnisearch'),
  searchInput: document.getElementById('omnisearch-input'),
};

let currentView = null;
let routeRevision = 0;

/* --------------------------------------------------- Statusleiste */

function setGauge(id, gaugeState, value, title = '') {
  const node = document.getElementById(id);
  if (!node) return;
  node.dataset.state = gaugeState;
  const valueNode = document.getElementById(`${id}-value`);
  if (valueNode) valueNode.textContent = value;
  if (title) node.title = title;
}

function renderStatus(status) {
  if (!status) {
    setGauge('gauge-ollama', 'bad', 'kein Backend', 'Das lokale Backend antwortet nicht.');
    return;
  }

  const { ollama, model, vault, profile, profiles, privacy, ui } = status;

  setGauge('gauge-ollama', ollama.online ? 'ok' : 'bad',
    ollama.online ? ollama.version || 'online' : 'offline',
    ollama.online ? `Ollama ${ollama.version} unter ${ollama.base_url}` : ollama.error || 'Nicht erreichbar');

  setGauge('gauge-model', model.installed ? 'ok' : (ollama.online ? 'warn' : 'bad'),
    model.name,
    model.installed
      ? `${model.name}${model.vision ? ' · Bilder' : ''}${model.thinking ? ' · Thinking' : ''}`
      : `${model.name} ist nicht installiert.`);

  setGauge('gauge-vault', vault.ok ? 'ok' : 'warn',
    vault.ok ? vault.name : 'nicht gesetzt', vault.path || 'Noch kein Vault ausgewählt.');

  setGauge('gauge-offline', privacy.offline_mode ? 'ok' : 'warn',
    privacy.offline_mode ? 'ein' : 'aus',
    privacy.offline_mode
      ? 'Offline-Modus aktiv: Es sind nur lokale Verbindungen erlaubt.'
      : 'Offline-Modus ist ausgeschaltet.');

  document.getElementById('brand-vault').textContent = 'KnowHow Tool';
  document.getElementById('brand-profile').textContent = profile.name;

  document.documentElement.style.setProperty('--spine', profileTone(profile.id, profiles));

  if (ui?.theme && document.documentElement.dataset.themePreference !== ui.theme) {
    applyTheme(ui.theme);
  }
}

/** Zeigt an, dass gerade eine Modellantwort läuft. */
export function setModelBusy(busy) {
  state.busy = busy;
  const node = document.getElementById('gauge-model');
  if (!node) return;
  if (busy) node.dataset.state = 'busy';
  else renderStatus(state.status);
}

/* ------------------------------------------------------- Routing */

async function route() {
  const current = parseRoute();
  const viewName = VIEW_LOADERS[current.view] ? current.view : 'dashboard';
  const revision = ++routeRevision;

  currentView?.unmount?.();
  currentView = null;
  clear(el.main);
  clear(el.rail);
  clear(el.context);

  for (const button of el.nav.querySelectorAll('.nav__item')) {
    button.classList.toggle('is-active', button.dataset.nav === current.view);
  }

  try {
    const view = await loadView(viewName);
    if (revision !== routeRevision) return;
    currentView = view;
    await view.mount({ route: current, el });
  } catch (error) {
    console.error(error);
    if (revision !== routeRevision) return;
    renderViewError(current.view, error);
  }
}

async function loadView(name) {
  if (!viewCache.has(name)) {
    const pending = VIEW_LOADERS[name]();
    viewCache.set(name, pending);
    pending.catch(() => viewCache.delete(name));
  }
  return viewCache.get(name);
}

function renderViewError(viewName, error) {
  const message = error?.message || 'Unbekannter Fehler beim Laden der Ansicht.';
  el.main.replaceChildren(h('div', { class: 'view' },
    h('div', { class: 'notice notice--bad' },
      h('div', { class: 'notice__body' },
        h('strong', { text: 'Ansicht konnte nicht geladen werden' }),
        h('p', { text: `Die Seite „${viewName}“ ist fehlgeschlagen: ${message}` }),
        h('div', { class: 'notice__actions' },
          h('button', { class: 'btn btn--sm btn--primary', onclick: () => location.reload() }, 'Erneut laden'),
          h('button', { class: 'btn btn--sm', onclick: () => navigate('/dashboard') }, 'Zur Übersicht'))))));
  toast('Die Ansicht konnte nicht geladen werden.', 'bad');
}

/* ---------------------------------------------------------- Setup */

function wireChrome() {
  el.nav.addEventListener('click', (event) => {
    const button = event.target.closest('.nav__item');
    if (button) navigate(`/${button.dataset.nav}`);
  });

  document.querySelector('.brand').addEventListener('click', (event) => {
    event.preventDefault();
    navigate('/dashboard');
  });

  document.getElementById('btn-settings').addEventListener('click', () => navigate('/settings'));

  document.getElementById('btn-theme').addEventListener('click', async () => {
    const order = ['dark', 'light', 'system'];
    const current = document.documentElement.dataset.themePreference || 'system';
    const next = order[(order.indexOf(current) + 1) % order.length];
    applyTheme(next);
    try {
      await api.updateUI(next);
      toast(`Design: ${{ dark: 'Dunkel', light: 'Hell', system: 'System' }[next]}`, 'ok');
    } catch { /* Design bleibt lokal gesetzt */ }
  });

  const contextButton = document.getElementById('btn-context');
  contextButton.classList.toggle('is-on', state.contextVisible);
  contextButton.addEventListener('click', () => {
    state.contextVisible = !state.contextVisible;
    el.workspace.classList.toggle('no-context', !state.contextVisible);
    contextButton.classList.toggle('is-on', state.contextVisible);
  });

  el.searchForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const query = el.searchInput.value.trim();
    if (query) navigate(`/search?q=${encodeURIComponent(query)}`);
  });

  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      el.searchInput.focus();
      el.searchInput.select();
    }
  });

  // Codeblöcke: Kopieren-Button überall im Dokument.
  document.addEventListener('click', (event) => {
    const button = event.target.closest('.copy-code');
    if (!button) return;
    const code = button.parentElement.querySelector('code');
    if (code) {
      navigator.clipboard.writeText(code.textContent).then(
        () => toast('Code kopiert.', 'ok'),
        () => toast('Kopieren nicht möglich.', 'bad'),
      );
    }
  });

  window.addEventListener('hashchange', route);
  on('route', route);

  // Laufende Antworten leben ausserhalb der Ansicht — die Statusleiste
  // zeigt deshalb auch dann noch an, dass das Modell arbeitet.
  on('chat:running', ({ running }) => setModelBusy(running));

  window.addEventListener('beforeunload', (event) => {
    if (runningChatIds().length) {
      event.preventDefault();
      event.returnValue = '';
    }
  });

  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
    if ((document.documentElement.dataset.themePreference || 'system') === 'system') applyTheme('system');
  });
}

const pollStatus = debounce(async () => {
  await refreshStatus();
  renderStatus(state.status);
}, 50);

async function start() {
  // Der Sitzungsschlüssel steht nur beim allerersten Aufruf in der Adresse.
  // Danach trägt ihn das Cookie; aus der Adresszeile darf er verschwinden,
  // damit er nicht in Lesezeichen oder auf Bildschirmfotos landet.
  if (new URLSearchParams(location.search).has('t')) {
    history.replaceState(null, '', location.pathname + location.hash);
  }

  applyTheme('dark');
  wireChrome();
  on('status', renderStatus);

  await refreshStatus();
  renderStatus(state.status);
  applyTheme(state.status?.ui?.theme || 'system');
  await refreshFileIndex();

  await route();

  // Statusleiste regelmäßig auffrischen (rein lokal, keine externen Aufrufe).
  setInterval(() => { if (!state.busy) pollStatus(); }, 12000);
  await refreshVaultChanges();
  setInterval(refreshVaultChanges, 3000);
}

start();

export { renderStatus, route };
