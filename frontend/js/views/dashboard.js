// Übersicht: Systemzustand, Kennzahlen, letzte Notizen und Chats.

import { api, streamPost } from '../api.js';
import { fmtDate, fmtNumber, h, icon, openModal, toast } from '../util.js';
import { navigate, refreshFileIndex, refreshStatus, state, vaultReady } from '../store.js';

export async function mount({ el }) {
  const view = h('div', { class: 'view' });
  el.main.append(view);
  render(view);
  renderContext(el.context);
}

function render(view) {
  const status = state.status;
  view.replaceChildren(
    h('div', { class: 'page-head' },
      h('span', { class: 'label', text: 'Übersicht' }),
      h('h1', { text: greeting() }),
      h('p', { text: status?.vault?.ok
        ? `Vault ${status.vault.name} · Profil ${status.profile.name}`
        : 'Wähle zuerst einen Vault aus, dann steht dir dein Wissen hier zur Verfügung.' })),
    ...problems(view),
    statStrip(),
    quickActions(),
    h('div', { class: 'grid grid--2' }, recentNotesCard(), recentChatsCard()),
  );
  loadStats(view);
  loadRecent(view);
  loadChats(view);
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 5) return 'Noch wach.';
  if (hour < 11) return 'Guten Morgen.';
  if (hour < 18) return 'Guten Tag.';
  return 'Guten Abend.';
}

/* ------------------------------------------------------- Probleme */

function problems(view) {
  const status = state.status;
  const items = [];
  if (!status) {
    items.push(notice('bad', 'Kein Backend', 'Die lokale Anwendung antwortet nicht. Starte sie neu.', []));
    return items;
  }

  if (!status.ollama.online) {
    items.push(notice('bad', 'Ollama ist nicht erreichbar',
      `Unter ${status.ollama.base_url} antwortet kein Dienst.`, [
        { label: 'Erneut versuchen', onClick: () => reloadDashboard(view) },
        { label: 'Ollama starten', variant: 'primary', onClick: () => startOllama(view) },
      ]));
  } else if (!status.model.installed) {
    items.push(notice('warn', `${status.model.name} ist nicht installiert`,
      'Das eingestellte Chat-Modell fehlt in Ollama. Du kannst es jetzt herunterladen.', [
        { label: 'Modell herunterladen', variant: 'primary', onClick: () => pullModel(status.model.name, view) },
        { label: 'Anderes Modell wählen', onClick: () => navigate('/settings') },
      ]));
  }

  if (!status.vault.ok) {
    const dataHint = !(status.counts?.chats)
      ? ` Verlauf und Einstellungen liegen in „${status.paths?.data_dir || 'data'}“ neben der EXE. Eine neue Version in denselben Ordner legen und diesen data-Ordner behalten.`
      : '';
    items.push(notice('warn', 'Kein Vault ausgewählt',
      (status.vault.error || 'Wähle den Ordner deines Obsidian-Vaults aus.') + dataHint, [
        { label: 'Ordner auswählen', variant: 'primary', onClick: () => chooseVault(view) },
        { label: 'Einstellungen öffnen', onClick: () => navigate('/settings') },
      ]));
  }
  return items;
}

function notice(kind, title, message, actions) {
  return h('div', { class: `notice ${kind === 'bad' ? 'notice--bad' : ''}` },
    h('div', { class: 'notice__body' },
      h('strong', { text: title }),
      h('p', { text: message }),
      actions.length
        ? h('div', { class: 'notice__actions' },
          ...actions.map((action) => h('button', {
            class: `btn btn--sm ${action.variant ? `btn--${action.variant}` : ''}`,
            onclick: action.onClick,
          }, action.label)))
        : null));
}

async function reloadDashboard(view) {
  await refreshStatus();
  await refreshFileIndex();
  render(view);
}

async function startOllama(view) {
  toast('Ollama wird gestartet …');
  try {
    const result = await api.startOllama();
    toast(result.message, result.online ? 'ok' : 'info');
  } catch (error) {
    toast(error.message, 'bad');
  }
  await reloadDashboard(view);
}

export async function chooseVault(view) {
  try {
    const picked = await api.browseFolder();
    if (picked.cancelled) return;
    await api.updateProfile(state.status.profile.id, { vault: { path: picked.path } });
    toast(`Vault gesetzt: ${picked.path}`, 'ok');
    await refreshStatus();
    await refreshFileIndex();
    if (view) render(view);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

export function pullModel(name, view) {
  const bar = h('div', { class: 'progress__bar' });
  const line = h('p', { text: 'Download wird vorbereitet …', style: 'margin:10px 0 0;color:var(--text-2);font-size:.8125rem' });
  const { close } = openModal({
    title: `${name} herunterladen`,
    description: 'Ollama lädt das Modell direkt von der Modellquelle. Das ist der einzige Vorgang, der eine Internetverbindung benötigt.',
    body: h('div', {}, h('div', { class: 'progress' }, bar), line),
    actions: [{ label: 'Im Hintergrund weiterlaufen lassen', onClick: (c) => c() }],
  });

  streamPost('/api/system/pull', { model: name }, {
    onEvent: (event) => {
      if (event.error) {
        line.textContent = event.error;
        toast(event.error, 'bad');
        return;
      }
      const { completed = 0, total = 0, status: text = '' } = event;
      if (total > 0) {
        const percent = Math.round((completed / total) * 100);
        bar.style.width = `${percent}%`;
        line.textContent = `${text} — ${percent} %`;
      } else {
        line.textContent = text || 'läuft …';
      }
      if (event.done) {
        bar.style.width = '100%';
        line.textContent = 'Fertig.';
        toast(`${name} wurde installiert.`, 'ok');
        setTimeout(() => { close(); reloadDashboard(view); }, 700);
      }
    },
    onError: (error) => { line.textContent = error.message; toast(error.message, 'bad'); },
  });
}

/* ------------------------------------------------------ Kennzahlen */

function stat(id, label) {
  return h('div', { class: 'stat' },
    h('div', { class: 'stat__value', id: `stat-${id}`, text: '–' }),
    h('div', { class: 'stat__label', text: label }));
}

function statStrip() {
  return h('div', { class: 'stat-strip' },
    stat('notes', 'Notizen'), stat('docs', 'Dokumente'), stat('images', 'Bilder'),
    stat('chats', 'Chats'), stat('messages', 'Nachrichten'));
}

async function loadStats(view) {
  const set = (id, value) => {
    const node = view.querySelector(`#stat-${id}`);
    if (node) node.textContent = value;
  };
  set('chats', fmtNumber(state.status?.counts?.chats ?? 0));
  set('messages', fmtNumber(state.status?.counts?.messages ?? 0));
  if (!vaultReady()) {
    ['notes', 'docs', 'images'].forEach((id) => set(id, '–'));
    return;
  }
  try {
    const data = await api.vaultStats();
    set('notes', fmtNumber(data.counts.note));
    set('docs', fmtNumber(data.counts.doc));
    set('images', fmtNumber(data.counts.image));
  } catch { /* Kennzahlen sind optional */ }
}

/* --------------------------------------------------- Schnellaktionen */

function quickActions() {
  const actions = [
    { label: 'Wissen erweitern', icon: 'chat', run: newVaultChat },
    { label: 'Wissen fragen', icon: 'question', run: newAskChat },
    { label: 'Neue Notiz', icon: 'note', run: () => navigate('/files?new=1') },
    { label: 'Dateien öffnen', icon: 'files', run: () => navigate('/files') },
    { label: 'Einstellungen', icon: 'gear', run: () => navigate('/settings') },
  ];
  return h('div', { class: 'quick' },
    ...actions.map((action) => h('button', { class: 'btn', onclick: action.run },
      icon(action.icon), action.label)));
}

async function newVaultChat() {
  try {
    const chat = await api.createChat('Neuer Wissens-Chat', 'vault');
    navigate(`/chat/${chat.id}`);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function newAskChat() {
  try {
    const chat = await api.createChat('Neue Frage', 'ask');
    navigate(`/ask/${chat.id}`);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

/* --------------------------------------------------------- Listen */

function recentNotesCard() {
  return h('div', { class: 'card' },
    h('div', { class: 'card__title' },
      h('span', { class: 'label', text: 'Zuletzt bearbeitet' }),
      h('button', { class: 'btn btn--ghost btn--sm', onclick: () => navigate('/files') }, 'Alle')),
    h('div', { class: 'list', id: 'recent-files' },
      h('p', { class: 'field__hint', text: 'wird geladen …' })));
}

async function loadRecent(view) {
  const host = view.querySelector('#recent-files');
  if (!host) return;
  if (!vaultReady()) {
    host.replaceChildren(h('p', { class: 'field__hint', text: 'Noch kein Vault ausgewählt.' }));
    return;
  }
  try {
    const data = await api.recentFiles(7);
    if (!data.files.length) {
      host.replaceChildren(h('p', { class: 'field__hint', text: 'Der Vault ist noch leer.' }));
      return;
    }
    host.replaceChildren(...data.files.map((file) => h('button', {
      class: 'list__item',
      onclick: () => navigate(`/files?path=${encodeURIComponent(file.path)}`),
    },
      icon(file.kind === 'image' ? 'image' : file.kind === 'doc' ? 'files' : 'note'),
      h('span', { class: 'list__main' },
        h('span', { class: 'list__title', text: file.name }),
        h('span', { class: 'list__sub', text: file.path })),
      h('span', { class: 'list__meta', text: fmtDate(file.modified) }))));
  } catch (error) {
    host.replaceChildren(h('p', { class: 'field__hint', text: error.message }));
  }
}

function recentChatsCard() {
  return h('div', { class: 'card' },
    h('div', { class: 'card__title' },
      h('span', { class: 'label', text: 'Letzte Chats' }),
      h('button', { class: 'btn btn--ghost btn--sm', onclick: () => navigate('/chat') }, 'Erweitern'),
      h('button', { class: 'btn btn--ghost btn--sm', onclick: () => navigate('/ask') }, 'Fragen')),
    h('div', { class: 'list', id: 'recent-chats' },
      h('p', { class: 'field__hint', text: 'wird geladen …' })));
}

async function loadChats(view) {
  const host = view.querySelector('#recent-chats');
  if (!host) return;
  try {
    const data = await api.listChats();
    if (!data.chats.length) {
      host.replaceChildren(
        h('p', { class: 'field__hint', text: 'Noch keine Chats.' }),
        h('button', { class: 'btn btn--sm', style: 'margin-top:8px', onclick: newAskChat }, icon('plus'), 'Erste Frage stellen'));
      return;
    }
    host.replaceChildren(...data.chats.slice(0, 7).map((chat) => h('button', {
      class: 'list__item', onclick: () => navigate(
        `/${chat.purpose === 'ask' ? 'ask' : 'chat'}/${chat.id}`,
      ),
    },
      icon(chat.purpose === 'ask' ? 'question' : 'chat'),
      h('span', { class: 'list__main' },
        h('span', { class: 'list__title', text: chat.title }),
        h('span', { class: 'list__sub', text: `${chat.purpose === 'ask' ? 'Fragen' : 'Erweitern'} · ${chat.message_count} Nachrichten` })),
      h('span', { class: 'list__meta', text: fmtDate(chat.updated_at) }))));
  } catch (error) {
    host.replaceChildren(h('p', { class: 'field__hint', text: error.message }));
  }
}

/* -------------------------------------------------------- Kontext */

function renderContext(host) {
  const status = state.status;
  if (!status) return;
  const model = status.model.info;
  host.replaceChildren(
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: 'Laufzeit' }),
      h('dl', { class: 'ctx-kv' },
        h('dt', { text: 'Ollama' }), h('dd', { text: status.ollama.online ? `v${status.ollama.version}` : 'offline' }),
        h('dt', { text: 'Adresse' }), h('dd', { text: status.ollama.base_url }),
        h('dt', { text: 'Modell' }), h('dd', { text: status.model.name }),
        model ? h('dt', { text: 'Größe' }) : null,
        model ? h('dd', { text: `${model.parameters} · ${model.quantization}` }) : null,
        model ? h('dt', { text: 'Kontext' }) : null,
        model ? h('dd', { text: fmtNumber(model.context_length) }) : null,
        h('dt', { text: 'Embedding' }), h('dd', { text: status.embedding.installed ? status.embedding.name : `${status.embedding.name} (fehlt)` }))),
    model?.capabilities?.length
      ? h('div', { class: 'ctx-block' },
        h('span', { class: 'label', text: 'Fähigkeiten' }),
        h('div', { class: 'row row--wrap' },
          ...model.capabilities.map((cap) => h('span', { class: 'chip', text: CAP_LABELS[cap] || cap }))))
      : null,
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: 'Datenschutz' }),
      h('dl', { class: 'ctx-kv' },
        h('dt', { text: 'Offline' }), h('dd', { text: status.privacy.offline_mode ? 'ein' : 'aus' }),
        h('dt', { text: 'Externe URLs' }), h('dd', { text: status.privacy.block_external_urls ? 'blockiert' : 'erlaubt' }),
        h('dt', { text: 'Telemetrie' }), h('dd', { text: 'aus' }))),
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: 'Vault' }),
      h('dl', { class: 'ctx-kv' },
        h('dt', { text: 'Pfad' }), h('dd', { text: status.vault.path || '–' }),
        h('dt', { text: 'Dateien' }), h('dd', { text: fmtNumber(state.files.length) }))),
  );
}

const CAP_LABELS = {
  completion: 'Text', vision: 'Bilder', tools: 'Werkzeuge',
  thinking: 'Thinking', embedding: 'Embeddings', insert: 'Einfügen',
};
