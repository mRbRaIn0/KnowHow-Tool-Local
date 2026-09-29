// Übersicht: Systemzustand, Kennzahlen, letzte Notizen und Chats.

import { api, streamPost } from '../api.js';
import { t } from '../i18n.js';
import { fill, fmtDate, fmtNumber, h, icon, kv, openModal, toast } from '../util.js';
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
      h('span', { class: 'label', text: t('nav.dashboard') }),
      h('h1', { text: greeting() }),
      h('p', { text: status?.vault?.ok
        ? t('dash.vaultProfile', { vault: status.vault.name, profile: status.profile.name })
        : t('dash.chooseVaultFirst') })),
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
  if (hour < 5) return t('dash.greetingNight');
  if (hour < 11) return t('dash.greetingMorning');
  if (hour < 18) return t('dash.greetingDay');
  return t('dash.greetingEvening');
}

/* ------------------------------------------------------- Probleme */

function problems(view) {
  const status = state.status;
  const items = [];
  if (!status) {
    items.push(notice('bad', t('dash.noBackend'), t('dash.noBackendText'), []));
    return items;
  }

  if (!status.ollama.online) {
    items.push(notice('bad', t('dash.ollamaDown'),
      t('dash.ollamaDownText', { url: status.ollama.base_url }), [
        { label: t('dash.retry'), onClick: () => reloadDashboard(view) },
        { label: t('dash.startOllama'), variant: 'primary', onClick: () => startOllama(view) },
      ]));
  } else if (!status.model.installed) {
    items.push(notice('warn', t('dash.modelMissing', { name: status.model.name }),
      t('dash.modelMissingText'), [
        { label: t('dash.downloadModel'), variant: 'primary', onClick: () => pullModel(status.model.name, view) },
        { label: t('dash.otherModel'), onClick: () => navigate('/settings') },
      ]));
  }

  if (!status.vault.ok) {
    const dataHint = !(status.counts?.chats)
      ? ` ${t('dash.dataHint', { folder: status.paths?.data_dir || 'data' })}`
      : '';
    items.push(notice('warn', t('common.noVault'),
      (status.vault.error || t('dash.chooseVaultText')) + dataHint, [
        { label: t('dash.chooseFolder'), variant: 'primary', onClick: () => chooseVault(view) },
        { label: t('dash.openSettings'), onClick: () => navigate('/settings') },
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
  toast(t('dash.ollamaStarting'));
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
    toast(t('dash.vaultSet', { path: picked.path }), 'ok');
    await refreshStatus();
    await refreshFileIndex();
    if (view) render(view);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

export function pullModel(name, view) {
  const bar = h('div', { class: 'progress__bar' });
  const line = h('p', { text: t('dash.pullPreparing'), style: 'margin:10px 0 0;color:var(--text-2);font-size:.8125rem' });
  const { close } = openModal({
    title: t('dash.pullTitle', { name }),
    description: t('dash.pullDescription'),
    body: h('div', {}, h('div', { class: 'progress' }, bar), line),
    actions: [{ label: t('dash.pullBackground'), onClick: (c) => c() }],
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
        line.textContent = text || t('dash.pullRunning');
      }
      if (event.done) {
        bar.style.width = '100%';
        line.textContent = t('dash.pullDone');
        toast(t('dash.pullInstalled', { name }), 'ok');
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
    stat('notes', t('nav.notes')), stat('docs', t('dash.docs')), stat('images', t('nav.images')),
    stat('chats', t('dash.chats')), stat('messages', t('dash.messages')));
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
    { label: t('nav.chat'), icon: 'chat', run: newVaultChat },
    { label: t('nav.ask'), icon: 'question', run: newAskChat },
    { label: t('dash.newNote'), icon: 'note', run: () => navigate('/files?new=1') },
    { label: t('dash.openFiles'), icon: 'files', run: () => navigate('/files') },
    { label: t('nav.settings'), icon: 'gear', run: () => navigate('/settings') },
  ];
  return h('div', { class: 'quick' },
    ...actions.map((action) => h('button', { class: 'btn', onclick: action.run },
      icon(action.icon), action.label)));
}

async function newVaultChat() {
  try {
    const chat = await api.createChat(t('mode.vault.newTitle'), 'vault');
    navigate(`/chat/${chat.id}`);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function newAskChat() {
  try {
    const chat = await api.createChat(t('mode.ask.newTitle'), 'ask');
    navigate(`/ask/${chat.id}`);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

/* --------------------------------------------------------- Listen */

function recentNotesCard() {
  return h('div', { class: 'card' },
    h('div', { class: 'card__title' },
      h('span', { class: 'label', text: t('dash.recentlyEdited') }),
      h('button', { class: 'btn btn--ghost btn--sm', onclick: () => navigate('/files') }, t('dash.all'))),
    h('div', { class: 'list', id: 'recent-files' },
      h('p', { class: 'field__hint', text: t('common.loading') })));
}

async function loadRecent(view) {
  const host = view.querySelector('#recent-files');
  if (!host) return;
  if (!vaultReady()) {
    host.replaceChildren(h('p', { class: 'field__hint', text: t('status.noVaultYet') }));
    return;
  }
  try {
    const data = await api.recentFiles(7);
    if (!data.files.length) {
      host.replaceChildren(h('p', { class: 'field__hint', text: t('dash.vaultEmpty') }));
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
      h('span', { class: 'label', text: t('dash.recentChats') }),
      h('button', { class: 'btn btn--ghost btn--sm', onclick: () => navigate('/chat') }, t('dash.extend')),
      h('button', { class: 'btn btn--ghost btn--sm', onclick: () => navigate('/ask') }, t('dash.ask'))),
    h('div', { class: 'list', id: 'recent-chats' },
      h('p', { class: 'field__hint', text: t('common.loading') })));
}

async function loadChats(view) {
  const host = view.querySelector('#recent-chats');
  if (!host) return;
  try {
    const data = await api.listChats();
    if (!data.chats.length) {
      host.replaceChildren(
        h('p', { class: 'field__hint', text: t('dash.noChats') }),
        h('button', { class: 'btn btn--sm', style: 'margin-top:8px', onclick: newAskChat }, icon('plus'), t('dash.firstQuestion')));
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
        h('span', { class: 'list__sub', text: t('dash.chatMeta', { kind: chat.purpose === 'ask' ? t('dash.ask') : t('dash.extend'), n: chat.message_count }) })),
      h('span', { class: 'list__meta', text: fmtDate(chat.updated_at) }))));
  } catch (error) {
    host.replaceChildren(h('p', { class: 'field__hint', text: error.message }));
  }
}

/* -------------------------------------------------------- Kontext */

const CAP_KEYS = {
  completion: 'cap.completion', vision: 'cap.vision', tools: 'cap.tools',
  thinking: 'cap.thinking', embedding: 'cap.embedding', insert: 'cap.insert',
};

function renderContext(host) {
  const status = state.status;
  if (!status) return;
  const model = status.model.info;
  const capabilities = model?.capabilities || [];
  fill(host,
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: t('dash.runtime') }),
      kv([
        ['Ollama', status.ollama.online ? `v${status.ollama.version}` : t('status.offline')],
        [t('dash.address'), status.ollama.base_url],
        [t('status.model'), status.model.name],
        [t('dash.size'), model ? [model.parameters, model.quantization].filter(Boolean).join(' · ') : null],
        [t('dash.context'), model?.context_length ? fmtNumber(model.context_length) : null],
        [t('dash.embedding'), status.embedding?.name
          ? (status.embedding.installed ? status.embedding.name : t('dash.embeddingMissing', { name: status.embedding.name })) : null],
      ])),
    capabilities.length
      ? h('div', { class: 'ctx-block' },
        h('span', { class: 'label', text: t('dash.capabilities') }),
        h('div', { class: 'row row--wrap' },
          ...capabilities.map((cap) => h('span', { class: 'chip', text: CAP_KEYS[cap] ? t(CAP_KEYS[cap]) : cap }))))
      : null,
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: t('dash.privacy') }),
      kv([
        [t('dash.offline'), status.privacy.offline_mode ? t('common.on') : t('common.off')],
        [t('dash.externalUrls'), status.privacy.block_external_urls ? t('dash.blocked') : t('dash.allowed')],
      ])),
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: 'Vault' }),
      kv([
        [t('dash.path'), status.vault.path || '–'],
        [t('dash.files'), fmtNumber(state.files.length)],
      ])),
  );
}
