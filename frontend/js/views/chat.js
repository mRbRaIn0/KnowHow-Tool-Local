// Chat: Verlauf links, Unterhaltung in der Mitte, Details rechts.
//
// Die Ansicht hält keinen Stream-Zustand. Laufende Antworten und Entwürfe
// liegen in chatstream.js und überleben deshalb jeden Ansichtswechsel.

import { api, uploadFiles } from '../api.js';
import { renderMarkdown } from '../markdown.js';
import {
  clear, confirmDialog, copyText, fmtBytes, fmtDate, fmtTime, h, icon,
  promptDialog, toast,
} from '../util.js';
import { markdownOptions, navigate, on, refreshFileIndex, refreshStatus, state, vaultReady } from '../store.js';
import * as stream from '../chatstream.js';

let elements = {};
let unsubscribe = [];
let live = null;  // { node, caret, thinkingNode } der gerade laufenden Antwort
let attachmentState = [];
let activeMode = null;
let folderContextMenu = null;
let folderContextCleanup = null;

const MAX_ATTACHMENTS = 50;
const CHIP_ICONS = { image: 'image', doc: 'doc', code: 'code', note: 'note', text: 'doc' };
const CHAT_MODES = {
  vault: {
    purpose: 'vault', route: 'chat', label: 'Wissen erweitern',
    newTitle: 'Neuer Wissens-Chat', emptyTitle: 'Kein Arbeitschat ausgewählt',
    emptyText: 'Starte einen Arbeitschat, um Wissen oder Dateien in den Vault aufzunehmen.',
    newLabel: 'Wissen hinzufügen',
    placeholder: 'Wissen oder Datei zum Vault hinzufügen …',
  },
  ask: {
    purpose: 'ask', route: 'ask', label: 'Wissen fragen',
    newTitle: 'Neue Frage', emptyTitle: 'Kein Fragen-Chat ausgewählt',
    emptyText: 'Starte einen Fragen-Chat für Antworten aus Wissensbasis und KI.',
    newLabel: 'Neue Frage',
    placeholder: 'Frage an Wissensbasis und KI stellen …',
  },
};

export function unmount() {
  // Wichtig: Der Stream wird NICHT abgebrochen — er läuft im Hintergrund weiter.
  closeFolderContextMenu();
  if (elements.input && state.activeChatId) {
    stream.setDraft(state.activeChatId, elements.input.value);
  }
  for (const off of unsubscribe) off();
  unsubscribe = [];
  elements = {};
  live = null;
  attachmentState = [];
  activeMode = null;
}

export async function mount({ route, el }) {
  activeMode = route.view === 'ask' ? CHAT_MODES.ask : CHAT_MODES.vault;
  elements = { rail: el.rail, main: el.main, context: el.context };
  state.activeChatId = route.id || null;
  await renderRail(route.id);

  if (!route.id) {
    el.main.append(emptyState());
    return;
  }

  const chat = h('div', { class: 'chat' });
  const scroll = h('div', { class: 'chat__scroll' });
  const inner = h('div', { class: 'chat__inner' });
  scroll.append(inner);
  chat.append(scroll, composer());
  el.main.append(chat);
  elements.scroll = scroll;
  elements.list = inner;

  let data;
  try {
    data = await api.getChat(route.id);
  } catch (error) {
    toast(error.message, 'bad');
    navigate(`/${activeMode.route}`);
    return;
  }

  if ((data.chat.purpose || 'vault') !== activeMode.purpose) {
    const correctRoute = data.chat.purpose === 'ask' ? 'ask' : 'chat';
    navigate(`/${correctRoute}/${route.id}`);
    return;
  }

  elements.chat = data.chat;
  const run = stream.getRun(route.id);

  for (const message of data.messages) {
    // Die noch leere Platzhalter-Zeile der laufenden Antwort überspringen —
    // sie wird gleich mit dem aktuellen Stand neu aufgebaut.
    if (message.role === 'assistant' && !message.content.trim()) continue;
    inner.append(renderMessage(message));
  }

  if (run) restoreRunning(run);
  else if (!data.messages.length) inner.append(starter());

  // Entwurf zurückholen, der beim letzten Verlassen gesichert wurde.
  const draft = stream.getDraft(route.id);
  if (draft) {
    elements.input.value = draft;
    autosize(elements.input);
  }

  await loadAttachments(route.id);

  unsubscribe.push(on('chat:event', onStreamEvent));
  renderContext(data.chat, data.messages.length);
  scrollToEnd();
  if (!run) elements.input.focus();
}

/** Eine im Hintergrund weiterlaufende Antwort wieder sichtbar machen. */
function restoreRunning(run) {
  const node = renderMessage({
    id: run.messageId, role: 'assistant', content: run.content,
    thinking: run.thinking, model: run.model, sources: run.steps,
    created_at: new Date().toISOString(),
  });
  const caret = h('span', { class: 'caret' });
  node._content.append(caret);
  elements.list.append(node);
  live = { node, caret, thinkingNode: node.querySelector('.msg__think') };
  setSending(true);
}

/* --------------------------------------------------------- Liste */

// Chat-Id, die gerade gezogen wird. dataTransfer allein reicht nicht, weil
// dragover den Inhalt aus Sicherheitsgründen nicht auslesen darf.
let dragChatId = null;

async function renderRail(activeId) {
  closeFolderContextMenu();
  const head = h('div', { class: 'rail-head' },
    h('span', { class: 'label', text: activeMode.label }),
    h('button', {
      class: 'icon-btn', title: 'Neuer Ordner',
      'aria-label': 'Neuer Ordner', onclick: newFolder,
    }, icon('folder-plus')),
    h('button', {
      class: 'icon-btn', title: activeMode.newLabel,
      'aria-label': activeMode.newLabel, onclick: newChat,
    }, icon('plus')));
  const list = h('div', { class: 'chat-tree' });
  elements.rail.replaceChildren(head, list);

  let folders = [];
  let chats = [];
  try {
    const [chatData, folderData] = await Promise.all([
      api.listChats(activeMode.purpose),
      api.listChatFolders(activeMode.purpose),
    ]);
    chats = chatData.chats || [];
    folders = folderData.folders || [];
    state.chats = chats;
  } catch (error) {
    list.append(h('p', { class: 'field__hint', style: 'padding:8px 4px', text: error.message }));
    return;
  }

  const known = new Set(folders.map((folder) => folder.id));
  const archived = chats.filter((chat) => chat.archived);
  const offen = chats.filter((chat) => !chat.archived);
  // Chats aus gelöschten Ordnern dürfen nicht unsichtbar werden.
  const lose = offen.filter((chat) => !chat.folder_id || !known.has(chat.folder_id));

  for (const folder of folders) {
    const inhalt = offen.filter((chat) => chat.folder_id === folder.id);
    list.append(folderGroup({
      key: `folder:${folder.id}`,
      name: folder.name,
      iconName: 'folder',
      collapsed: folder.collapsed,
      onCollapse: (value) => api.updateChatFolder(folder.id, { collapsed: value }).catch(() => {}),
      chats: inhalt,
      activeId,
      emptyText: 'Chats hierher ziehen',
      onDrop: (chatId) => moveChat(chatId, { folder_id: folder.id, archived: false }),
      tools: [
        { title: 'Ordner umbenennen', iconName: 'pencil', onClick: () => renameFolder(folder) },
        { title: 'Ordner löschen', iconName: 'trash', danger: true, onClick: () => deleteFolder(folder) },
      ],
    }));
  }

  // Ohne Ordner und ohne Archiv bleibt die Liste schlicht — dann braucht es
  // auch keine Überschrift für die oberste Ebene.
  if (folders.length || archived.length) {
    list.append(folderGroup({
      key: 'root',
      name: 'Chats',
      iconName: 'chat',
      collapsed: readCollapsed('root'),
      onCollapse: (value) => writeCollapsed('root', value),
      chats: lose,
      activeId,
      emptyText: 'Chats hierher ziehen',
      onDrop: (chatId) => moveChat(chatId, { folder_id: '', archived: false }),
    }));
  } else if (lose.length) {
    const host = h('div', { class: 'chat-tree__loose' }, ...lose.map((chat) => chatItem(chat, chat.id === activeId)));
    list.append(host);
  } else {
    list.append(h('p', {
      class: 'field__hint', style: 'padding:8px 4px',
      text: activeMode.purpose === 'ask' ? 'Noch keine Fragen-Verläufe.' : 'Noch keine Arbeitsverläufe.',
    }));
  }

  list.append(folderGroup({
    key: 'archive',
    name: 'Archiviert',
    iconName: 'archive',
    modifier: 'chat-folder--archive',
    collapsed: readCollapsed('archive'),
    onCollapse: (value) => writeCollapsed('archive', value),
    chats: archived,
    activeId,
    archive: true,
    emptyText: 'Chats zum Archivieren hierher ziehen',
    onDrop: (chatId) => moveChat(chatId, { archived: true }),
  }));
}

/** Eine ein- und ausklappbare Gruppe, die Chats per Drag & Drop annimmt. */
function folderGroup(options) {
  const { name, iconName, collapsed, onCollapse, chats, activeId, emptyText, onDrop } = options;
  const body = h('div', { class: 'chat-folder__body' });
  if (chats.length) {
    body.append(...chats.map((chat) => chatItem(chat, chat.id === activeId, options.archive)));
  } else {
    body.append(h('p', { class: 'chat-folder__empty', text: emptyText }));
  }

  const chevron = icon('chevron', 'chat-folder__chevron');
  const toggle = h('button', { class: 'chat-folder__main', type: 'button' },
    chevron,
    icon(iconName, 'chat-folder__icon'),
    h('span', { class: 'chat-folder__name', text: name }),
    h('span', { class: 'chat-folder__count', text: String(chats.length) }));

  const tools = h('span', { class: 'chat-folder__tools' },
    ...(options.tools || []).map((tool) => h('button', {
      class: 'icon-btn', title: tool.title, 'aria-label': tool.title, type: 'button',
      onclick: (event) => { event.stopPropagation(); tool.onClick(); },
    }, icon(tool.iconName))));

  const head = h('div', { class: 'chat-folder__head' }, toggle, tools);
  if (options.tools?.length) {
    head.title = 'Rechtsklick für Ordneroptionen';
    head.addEventListener('contextmenu', (event) => {
      event.preventDefault();
      event.stopPropagation();
      openFolderContextMenu(event, name, options.tools, toggle);
    });
  }

  const group = h('div', {
    class: `chat-folder ${options.modifier || ''} ${collapsed ? 'is-collapsed' : ''}`,
  }, head, body);

  toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  toggle.addEventListener('click', () => {
    const next = !group.classList.contains('is-collapsed');
    group.classList.toggle('is-collapsed', next);
    toggle.setAttribute('aria-expanded', next ? 'false' : 'true');
    onCollapse(next);
  });

  // Ein Chat, der auf einen zugeklappten Ordner fällt, wäre sonst weg vom Bild.
  return dropZone(group, (chatId) => {
    if (group.classList.contains('is-collapsed')) {
      group.classList.remove('is-collapsed');
      onCollapse(false);
    }
    onDrop(chatId);
  });
}

/** Zeigt die Aktionen eines echten Chat-Ordners am Mauszeiger. */
function openFolderContextMenu(event, folderName, actions, returnFocus) {
  closeFolderContextMenu();

  const buttons = actions.map((action) => h('button', {
    class: `chat-folder-menu__item ${action.danger ? 'chat-folder-menu__item--danger' : ''}`,
    type: 'button', role: 'menuitem',
    onclick: () => {
      closeFolderContextMenu();
      action.onClick();
    },
  }, icon(action.iconName), h('span', { text: action.title })));

  const menu = h('div', {
    class: 'chat-folder-menu', role: 'menu',
    'aria-label': `Ordner ${folderName} verwalten`,
  }, ...buttons);
  document.body.append(menu);
  folderContextMenu = menu;

  const anchor = returnFocus.getBoundingClientRect();
  const requestedX = event.clientX || anchor.left + 12;
  const requestedY = event.clientY || anchor.bottom;
  const bounds = menu.getBoundingClientRect();
  const gap = 8;
  menu.style.left = `${Math.max(gap, Math.min(requestedX, window.innerWidth - bounds.width - gap))}px`;
  menu.style.top = `${Math.max(gap, Math.min(requestedY, window.innerHeight - bounds.height - gap))}px`;

  const abort = new AbortController();
  const { signal } = abort;
  folderContextCleanup = () => abort.abort();

  document.addEventListener('pointerdown', (nextEvent) => {
    if (!menu.contains(nextEvent.target)) closeFolderContextMenu();
  }, { capture: true, signal });
  document.addEventListener('contextmenu', (nextEvent) => {
    if (!menu.contains(nextEvent.target)) closeFolderContextMenu();
  }, { capture: true, signal });
  document.addEventListener('keydown', (keyEvent) => {
    const current = buttons.indexOf(document.activeElement);
    if (keyEvent.key === 'Escape') {
      keyEvent.preventDefault();
      closeFolderContextMenu();
      returnFocus.focus({ preventScroll: true });
    } else if (keyEvent.key === 'ArrowDown') {
      keyEvent.preventDefault();
      buttons[(current + 1) % buttons.length].focus();
    } else if (keyEvent.key === 'ArrowUp') {
      keyEvent.preventDefault();
      buttons[(current - 1 + buttons.length) % buttons.length].focus();
    } else if (keyEvent.key === 'Home') {
      keyEvent.preventDefault();
      buttons[0].focus();
    } else if (keyEvent.key === 'End') {
      keyEvent.preventDefault();
      buttons.at(-1).focus();
    }
  }, { signal });
  window.addEventListener('resize', closeFolderContextMenu, { signal });
  document.addEventListener('scroll', closeFolderContextMenu, { capture: true, signal });
  buttons[0]?.focus({ preventScroll: true });
}

function closeFolderContextMenu() {
  folderContextCleanup?.();
  folderContextCleanup = null;
  folderContextMenu?.remove();
  folderContextMenu = null;
}

/** Markiert ein Ziel während des Ziehens und meldet den fallen gelassenen Chat. */
function dropZone(node, onDrop) {
  node.addEventListener('dragover', (event) => {
    if (!dragChatId) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    node.classList.add('is-drop');
  });
  node.addEventListener('dragleave', (event) => {
    if (node.contains(event.relatedTarget)) return;
    node.classList.remove('is-drop');
  });
  node.addEventListener('drop', (event) => {
    event.preventDefault();
    event.stopPropagation();
    node.classList.remove('is-drop');
    const chatId = dragChatId || event.dataTransfer.getData('text/plain');
    if (chatId) onDrop(chatId);
  });
  return node;
}

function chatItem(chat, active, archived = false) {
  const running = stream.isRunning(chat.id);
  const node = h('div', {
    class: `chat-item ${active ? 'is-active' : ''}`, draggable: 'true',
    title: 'Zum Verschieben in einen Ordner ziehen',
  },
    h('button', {
      class: 'chat-item__main', draggable: 'true', style: 'text-align:left;min-width:0',
      onclick: () => navigate(`/${activeMode.route}/${chat.id}`),
    },
      h('span', { class: 'chat-item__title', text: chat.title }),
      h('span', { class: 'chat-item__sub', text: running ? 'antwortet …' : `${fmtDate(chat.updated_at)} · ${chat.message_count}` })),
    running ? h('span', { class: 'chat-item__live', title: 'Antwort läuft' }) : null,
    h('span', { class: 'chat-item__tools' },
      archived
        ? h('button', {
            class: 'icon-btn', title: 'Aus dem Archiv holen',
            onclick: () => moveChat(chat.id, { archived: false }),
          }, icon('folder-open'))
        : h('button', {
            class: 'icon-btn', title: 'Archivieren',
            onclick: () => moveChat(chat.id, { archived: true }),
          }, icon('archive')),
      h('button', { class: 'icon-btn', title: 'Umbenennen', onclick: () => renameChat(chat) }, icon('pencil')),
      h('button', { class: 'icon-btn', title: 'Löschen', onclick: () => deleteChat(chat) }, icon('trash'))));

  node.addEventListener('dragstart', (event) => {
    dragChatId = chat.id;
    node.classList.add('is-dragging');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', chat.id);
  });
  node.addEventListener('dragend', () => {
    dragChatId = null;
    node.classList.remove('is-dragging');
    for (const zone of document.querySelectorAll('.chat-folder.is-drop')) zone.classList.remove('is-drop');
  });
  return node;
}

/* Klappzustand von "Chats" und "Archiviert" gehört zur Oberfläche und bleibt
   deshalb lokal — echte Ordner merken ihn sich in der Datenbank. */
const collapseKey = (key) => `chatTree:${activeMode.purpose}:${key}`;
const readCollapsed = (key) => localStorage.getItem(collapseKey(key)) === '1';
const writeCollapsed = (key, value) => localStorage.setItem(collapseKey(key), value ? '1' : '0');

async function moveChat(chatId, patch) {
  try {
    await api.updateChat(chatId, patch);
    await renderRail(state.activeChatId);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function newChat() {
  try {
    const chat = await api.createChat(activeMode.newTitle, activeMode.purpose);
    navigate(`/${activeMode.route}/${chat.id}`);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function newFolder() {
  const name = await promptDialog({
    title: 'Ordner anlegen', label: 'Name', value: '', confirmLabel: 'Anlegen',
  });
  if (!name) return;
  try {
    await api.createChatFolder(name, activeMode.purpose);
    await renderRail(state.activeChatId);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function renameFolder(folder) {
  const name = await promptDialog({
    title: 'Ordner umbenennen', label: 'Name', value: folder.name, confirmLabel: 'Umbenennen',
  });
  if (!name) return;
  try {
    await api.updateChatFolder(folder.id, { name });
    await renderRail(state.activeChatId);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function deleteFolder(folder) {
  const ok = await confirmDialog({
    title: 'Ordner löschen',
    message: `„${folder.name}" wird entfernt. Die enthaltenen Chats bleiben erhalten und liegen danach wieder direkt in der Liste.`,
    confirmLabel: 'Löschen', danger: true,
  });
  if (!ok) return;
  try {
    await api.deleteChatFolder(folder.id);
    await renderRail(state.activeChatId);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function renameChat(chat) {
  const title = await promptDialog({
    title: 'Chat umbenennen', label: 'Titel', value: chat.title, confirmLabel: 'Umbenennen',
  });
  if (!title) return;
  try {
    await api.renameChat(chat.id, title);
    await renderRail(state.activeChatId);
    if (elements.chat?.id === chat.id) { elements.chat.title = title; renderContext(elements.chat); }
    toast('Chat umbenannt.', 'ok');
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function deleteChat(chat) {
  const laufend = stream.isRunning(chat.id);
  const ok = await confirmDialog({
    title: 'Chat löschen',
    message: laufend
      ? `„${chat.title}" antwortet gerade. Die laufende Antwort wird abgebrochen und der Chat endgültig entfernt.`
      : `„${chat.title}" wird endgültig aus der lokalen Datenbank entfernt.`,
    confirmLabel: 'Löschen', danger: true,
  });
  if (!ok) return;
  try {
    stream.stop(chat.id);
    stream.clearDraft(chat.id);
    await api.deleteChat(chat.id);
    toast('Chat gelöscht.', 'ok');
    if (state.activeChatId === chat.id) navigate(`/${activeMode.route}`);
    else await renderRail(state.activeChatId);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

/* ---------------------------------------------------- Nachrichten */

function renderMessage(message) {
  const isUser = message.role === 'user';
  const body = h('div', { class: 'msg__body' });

  if (message.thinking) body.append(thinkingBlock(message.thinking));

  const stepHost = h('div', { class: 'msg__steps' });
  for (const step of message.sources || []) stepHost.append(renderStep(step));
  if (!isUser) body.append(stepHost);

  // Mitgeschickte Dateien bleiben an der Nachricht sichtbar.
  const anhaenge = message.attachments || [];
  if (isUser && anhaenge.length) {
    body.append(h('div', { class: 'msg__attachments' },
      ...anhaenge.map((item) => renderMessageAttachment(item))));
  }

  const content = h('div', { class: 'md' });
  content.innerHTML = renderMarkdown(message.content, markdownOptions());
  body.append(content);

  const node = h('div', { class: `msg msg--${isUser ? 'user' : 'assistant'}`, dataset: { id: message.id ?? '' } },
    h('div', { class: 'msg__head' },
      h('span', { class: 'msg__who', text: isUser ? 'Du' : (message.model || 'Modell') }),
      h('span', { class: 'msg__time', text: fmtTime(message.created_at) }),
      h('span', { class: 'msg__tools' },
        h('button', { class: 'icon-btn', title: 'Antwort kopieren', onclick: () => copyText(currentText(node, message)) }, icon('copy')),
        !isUser && activeMode.purpose === 'vault'
          ? h('button', { class: 'icon-btn', title: 'Als Notiz speichern', onclick: () => saveAsNote({ ...message, content: currentText(node, message) }) }, icon('note'))
          : null)),
    body);
  node._content = content;
  node._steps = stepHost;
  return node;
}

// Bei laufenden Antworten steht der aktuelle Text im Stream, nicht im Objekt.
function currentText(node, message) {
  const run = stream.getRun(state.activeChatId);
  if (run && live?.node === node) return run.content;
  return message.content;
}

/** Ein Anhang, wie er an einer abgeschickten Nachricht erscheint. */
function renderMessageAttachment(item) {
  const url = api.attachmentUrl(state.activeChatId, item.name);
  if (item.kind === 'image') {
    return h('a', { class: 'attach-thumb', href: url, target: '_blank',
                    rel: 'noreferrer', title: item.name },
      h('img', { src: url, alt: item.name, loading: 'lazy' }));
  }
  return h('a', { class: 'attach-file', href: url, target: '_blank',
                  rel: 'noreferrer', title: item.name },
    icon(CHIP_ICONS[item.kind] || 'doc'),
    h('span', { text: item.name }));
}

const STEP_LABELS = {
  vault_suchen: ['Vault durchsucht', 'search'],
  notiz_lesen: ['Notiz gelesen', 'note'],
  ordner_auflisten: ['Ordner angesehen', 'folder-open'],
  notiz_erstellen: ['Notiz erstellt', 'plus'],
  notiz_ergaenzen: ['Notiz ergänzt', 'pencil'],
  notiz_bearbeiten: ['Notiz bearbeitet', 'pencil'],
  markdown_dateien_bereinigen: ['Alle Markdown-Dateien geprüft', 'pencil'],
  dateien_in_unterordner_verschieben: ['Dateien eingeordnet und Links aktualisiert', 'folder'],
  anhang_in_vault_ablegen: ['Original abgelegt', 'clip'],
  dateien_verknuepfen: ['Dateien verknüpft', 'note'],
  wissenssuche: ['Wissen abgeglichen', 'search'],
};

/** Eine Zeile pro Werkzeugaufruf — nachvollziehbar, was die KI im Vault getan hat. */
function renderStep(step, pending = false) {
  const [label, iconName] = STEP_LABELS[step.tool] || [step.tool, 'files'];
  const result = step.result || {};
  const ziel = result.erstellt || result.ergaenzt || result.bearbeitet || result.abgelegt || result.notiz || result.pfad
    || step.arguments?.pfad || step.arguments?.suchbegriff || '';

  let detail = ziel;
  if (pending) detail = `${ziel} …`;
  else if (result.fehler) detail = result.fehler;
  else if (result.anzahl !== undefined) {
    const query = step.arguments?.suchbegriff || step.arguments?.query || '';
    detail = `${query ? `„${query}" — ` : ''}${result.anzahl} Treffer${result.semantisch ? ' · semantisch' : ''}`;
  }
  else if (result.hinweis && !result.treffer?.length) detail = result.hinweis;

  const oeffnet = !pending && (result.erstellt || result.ergaenzt || result.bearbeitet
    || result.abgelegt || result.notiz || result.pfad);
  const classes = ['step'];
  if (step.writing && !result.fehler) classes.push('step--writing');
  if (result.fehler) classes.push('step--failed');
  if (pending) classes.push('step--pending');

  const kinder = [
    icon(iconName, 'step__icon'),
    h('span', { class: 'step__label', text: label }),
    h('span', { class: 'step__detail', text: detail, title: detail }),
  ];

  return oeffnet
    ? h('button', { class: classes.join(' '), title: `${oeffnet} öffnen`,
        onclick: () => navigate(`/files?path=${encodeURIComponent(oeffnet)}`) }, ...kinder)
    : h('div', { class: classes.join(' ') }, ...kinder);
}

function thinkingBlock(text) {
  return h('details', { class: 'msg__think' },
    h('summary', { text: 'Gedankengang' }),
    h('pre', { text }));
}

function starter() {
  const status = state.status;
  const askMode = activeMode.purpose === 'ask';
  const examples = askMode
    ? [
      'Was sind die wichtigsten Aussagen in meiner Wissensbasis?',
      'Erkläre das Thema anhand meiner Notizen und ergänze KI-Wissen.',
      'Welche lokalen Quellen passen zu meiner Frage?',
    ]
    : [
      'Erstelle aus meinen Angaben eine strukturierte Notiz.',
      'Übernimm die angehängte Datei in den Vault und fasse sie zusammen.',
      'Ergänze eine vorhandene Notiz um diese Information.',
    ];
  return h('div', { class: 'empty', style: 'padding-top:60px' },
    icon(askMode ? 'question' : 'chat'),
    h('h3', { text: askMode ? 'Wissensbasis + KI' : 'Vault-Wissen erweitern' }),
    h('p', { text: askMode
      ? 'Frage dein lokales Wissen ab. Fehlende Zusammenhänge darf die KI klar gekennzeichnet ergänzen.'
      : `Informationen und Dateien werden mit ${status?.model?.name || 'dem lokalen Modell'} in deinen Vault eingepflegt.` }),
    h('div', { class: 'row row--wrap', style: 'justify-content:center;margin-top:6px' },
      ...examples.map((example) => h('button', {
        class: 'btn btn--sm',
        onclick: () => { elements.input.value = example; elements.input.focus(); autosize(elements.input); },
      }, example.length > 46 ? `${example.slice(0, 44)}…` : example))));
}

function emptyState() {
  return h('div', { class: 'empty', style: 'height:100%' },
    icon(activeMode.purpose === 'ask' ? 'question' : 'chat'),
    h('h3', { text: activeMode.emptyTitle }),
    h('p', { text: activeMode.emptyText }),
    h('button', { class: 'btn btn--primary', onclick: newChat }, icon('plus'), activeMode.newLabel));
}

/* ------------------------------------------------------- Composer */

function composer() {
  const askMode = activeMode.purpose === 'ask';
  const input = h('textarea', {
    rows: 1, placeholder: `${activeMode.placeholder}  (Enter senden, Umschalt+Enter neue Zeile)`,
    'aria-label': activeMode.placeholder,
    oninput: (event) => {
      autosize(event.target);
      // Laufend sichern, damit auch ein Klick in der Navigation nichts kostet.
      stream.setDraft(state.activeChatId, event.target.value);
    },
    onkeydown: (event) => {
      if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send(); }
    },
    onpaste: askMode ? null : (event) => {
      // Screenshot aus der Zwischenablage direkt anhängen.
      const dateien = [...(event.clipboardData?.files || [])];
      if (dateien.length) { event.preventDefault(); addFiles(dateien); }
    },
  });
  elements.input = input;

  const dateiwahl = askMode ? null : h('input', {
    type: 'file', multiple: true, style: 'display:none',
    onchange: (event) => { addFiles([...event.target.files]); event.target.value = ''; },
  });
  elements.fileInput = dateiwahl;

  const plus = askMode ? null : h('button', {
    class: 'composer__add', title: 'Dateien anhängen — Bilder, Dokumente, Quellcode',
    'aria-label': 'Dateien anhängen', onclick: () => dateiwahl.click(),
  }, icon('plus'));

  const chips = h('div', { class: 'composer__files' });
  elements.chips = chips;

  const sendButton = h('button', { class: 'btn btn--primary', onclick: send }, icon('send'), 'Senden');
  const stopButton = h('button', { class: 'btn', onclick: stopCurrent, style: 'display:none' }, 'Stopp');
  elements.sendButton = sendButton;
  elements.stopButton = stopButton;

  const box = h('div', { class: 'composer__box' },
    chips,
    h('div', { class: 'composer__row' }, plus, input),
    h('div', { class: 'composer__bar' },
      h('span', { class: 'spacer' }),
      stopButton, sendButton));

  const wrapper = h('div', { class: 'composer' },
    h('div', { class: 'composer__inner' }, composerMeta(), box, dateiwahl));

  unsubscribe.push(on('status', syncComposerMeta));
  syncComposerMeta(state.status);
  if (!askMode) wireDropzone(box);
  return wrapper;
}

function composerMeta() {
  const select = h('select', {
    class: 'composer__model',
    'aria-label': 'Chat-Modell',
    onchange: (event) => changeChatModel(event.target.value),
  });
  const checkbox = h('input', {
    type: 'checkbox',
    onchange: (event) => changeThinking(event.target.checked),
  });
  const think = h('label', { class: 'switch composer__think' },
    checkbox,
    h('span', { class: 'switch__track' }),
    h('span', { class: 'composer__think-label', text: 'Thinking' }));
  elements.modelSelect = select;
  elements.thinkToggle = checkbox;
  elements.thinkLabel = think;
  return h('div', { class: 'composer__side' }, select, think);
}

function fillModelSelect(select, status) {
  const current = status?.model?.name || '';
  const models = (status?.models || []).filter((model) => !/embed/i.test(model.name || ''));
  const names = models.map((model) => model.name);
  const signature = `${current}|${names.join(',')}`;
  if (select.dataset.sig === signature) {
    select.value = current || '';
    return;
  }
  select.dataset.sig = signature;
  clear(select);
  if (current && !names.includes(current)) {
    select.append(h('option', { value: current, text: current }));
  }
  if (!names.length && !current) {
    select.append(h('option', { value: '', text: 'kein Modell' }));
  }
  for (const model of models) {
    select.append(h('option', { value: model.name, text: model.name }));
  }
  select.value = current || '';
  select.disabled = !models.length && !current;
}

function syncComposerMeta(status) {
  const select = elements.modelSelect;
  const checkbox = elements.thinkToggle;
  const label = elements.thinkLabel;
  if (!select || !checkbox || !label) return;
  fillModelSelect(select, status);
  const canThink = Boolean(status?.model?.thinking);
  checkbox.disabled = !canThink;
  checkbox.checked = canThink && Boolean(status?.ai?.thinking);
  label.classList.toggle('is-disabled', !canThink);
  label.title = canThink
    ? 'Denkprozess des Modells ein- oder ausschalten.'
    : 'Dieses Modell unterstützt keinen Denkprozess.';
}

async function patchProfile(body) {
  const id = state.status?.profile?.id;
  if (!id) return;
  try {
    await api.updateProfile(id, body);
    await refreshStatus();
  } catch (error) {
    toast(error.message, 'bad');
  }
}

function changeChatModel(name) {
  if (!name || name === state.status?.model?.name) return;
  patchProfile({ ollama: { chat_model: name } });
}

function changeThinking(enabled) {
  if (!state.status?.model?.thinking) return;
  patchProfile({ ai: { thinking: enabled } });
}

/* -------------------------------------------------------- Anhänge */

/** Ziehen und Ablegen über dem gesamten Chatbereich. */
function wireDropzone(box) {
  let tiefe = 0;
  const ziel = elements.main;
  const hatDateien = (event) => [...(event.dataTransfer?.types || [])].includes('Files');

  ziel.addEventListener('dragenter', (event) => {
    if (!hatDateien(event)) return;
    event.preventDefault();
    tiefe += 1;
    box.classList.add('is-dropping');
  });
  ziel.addEventListener('dragover', (event) => { if (hatDateien(event)) event.preventDefault(); });
  ziel.addEventListener('dragleave', () => {
    tiefe = Math.max(0, tiefe - 1);
    if (!tiefe) box.classList.remove('is-dropping');
  });
  ziel.addEventListener('drop', (event) => {
    const dateien = [...(event.dataTransfer?.files || [])];
    if (!dateien.length) return;
    event.preventDefault();
    tiefe = 0;
    box.classList.remove('is-dropping');
    addFiles(dateien);
  });
}

async function addFiles(dateien) {
  if (activeMode?.purpose === 'ask' || !dateien.length || !state.activeChatId) return;

  const frei = MAX_ATTACHMENTS - attachmentState.length;
  if (frei <= 0) {
    toast(`Mehr als ${MAX_ATTACHMENTS} Anhänge je Chat sind nicht möglich.`, 'bad');
    return;
  }
  if (dateien.length > frei) {
    toast(`Nur ${frei} von ${dateien.length} Dateien passen noch dazu.`, 'bad');
    dateien = dateien.slice(0, frei);
  }

  const platzhalter = h('span', { class: 'filechip filechip--busy' },
    icon('clip', 'filechip__icon'),
    h('span', { class: 'filechip__name', text: `${dateien.length} Datei(en) werden übertragen …` }));
  elements.chips?.append(platzhalter);

  try {
    const ergebnis = await uploadFiles(state.activeChatId, dateien);
    attachmentState = ergebnis.alle || [];
    for (const problem of ergebnis.fehler || []) toast(`${problem.name}: ${problem.grund}`, 'bad');
    if (ergebnis.gespeichert?.length) {
      toast(ergebnis.gespeichert.length === 1
        ? `${ergebnis.gespeichert[0].name} angehängt.`
        : `${ergebnis.gespeichert.length} Dateien angehängt.`, 'ok');
    }
  } catch (error) {
    toast(error.message, 'bad');
  } finally {
    platzhalter.remove();
    renderChips();
  }
}

async function removeAttachment(name) {
  try {
    await api.deleteAttachment(state.activeChatId, name);
    attachmentState = attachmentState.filter((item) => item.name !== name);
    renderChips();
  } catch (error) {
    toast(error.message, 'bad');
  }
}

function renderChips() {
  const host = elements.chips;
  if (!host) return;
  host.replaceChildren();
  if (!attachmentState.length) return;

  for (const item of attachmentState) {
    const vorschau = item.kind === 'image'
      ? h('img', { class: 'filechip__thumb', loading: 'lazy',
                   src: api.attachmentUrl(state.activeChatId, item.name), alt: '' })
      : icon(CHIP_ICONS[item.kind] || 'doc', 'filechip__icon');

    host.append(h('span', { class: 'filechip', title: `${item.name} · ${fmtBytes(item.size)}` },
      vorschau,
      h('span', { class: 'filechip__name', text: item.name }),
      h('button', {
        class: 'filechip__remove', title: 'Anhang entfernen',
        onclick: () => removeAttachment(item.name),
      }, icon('close'))));
  }

  host.append(h('span', { class: 'filechip filechip--count',
    text: `${attachmentState.length}/${MAX_ATTACHMENTS}` }));
}

async function loadAttachments(chatId) {
  if (activeMode.purpose === 'ask') {
    attachmentState = [];
    renderChips();
    return;
  }
  try {
    attachmentState = (await api.listAttachments(chatId)).attachments || [];
  } catch {
    attachmentState = [];
  }
  renderChips();
}

function autosize(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`;
}

function scrollToEnd() {
  requestAnimationFrame(() => {
    if (elements.scroll) elements.scroll.scrollTop = elements.scroll.scrollHeight;
  });
}

function setSending(sending) {
  if (!elements.sendButton) return;
  elements.sendButton.style.display = sending ? 'none' : '';
  elements.stopButton.style.display = sending ? '' : 'none';
  // Das Eingabefeld bleibt bedienbar: Die nächste Frage darf schon getippt werden.
  elements.input.placeholder = sending
    ? 'Antwort läuft — du kannst schon weiterschreiben …'
    : `${activeMode.placeholder}  (Enter senden, Umschalt+Enter neue Zeile)`;
}

function stopCurrent() {
  stream.stop(state.activeChatId);
  toast('Antwort abgebrochen.');
}

function send() {
  const content = elements.input.value.trim();
  if ((!content && !attachmentState.length) || !state.activeChatId) return;

  if (stream.isRunning(state.activeChatId)) {
    toast('Dieser Chat antwortet gerade noch.');
    return;
  }
  if (!state.status?.ollama?.online) {
    toast('Ollama ist nicht erreichbar. Starte den Dienst und versuche es erneut.', 'bad');
    return;
  }

  elements.list.querySelector('.empty')?.remove();
  elements.input.value = '';
  stream.clearDraft(state.activeChatId);
  autosize(elements.input);
  setSending(true);

  // Die Anhänge gehen mit dieser Nachricht mit und starten die nächste
  // Eingabe nicht erneut. Gelöscht wird nichts — sie bleiben im Chat und
  // über ihren Namen weiterhin ansprechbar.
  attachmentState = [];
  renderChips();

  stream.send(
    state.activeChatId,
    content || 'Übernimm die angehängten Dateien in den Vault und dokumentiere ihren Inhalt.',
  );
}

/* -------------------------------------------- Stream-Ereignisse */

function onStreamEvent({ chatId, event, run }) {
  // Ereignisse anderer Chats laufen im Hintergrund weiter, ohne die Ansicht zu stören.
  if (chatId !== state.activeChatId || !elements.list) return;

  if (event.type === 'user_message') {
    elements.list.append(renderMessage(event.message));
    const node = renderMessage({
      id: null, role: 'assistant', content: '', thinking: '',
      model: state.status?.model?.name || '', created_at: new Date().toISOString(),
    });
    elements.list.append(node);
    live = { node, caret: null, thinkingNode: null, progress: null };
    scrollToEnd();
    return;
  }

  if (event.type === 'start') {
    if (live?.node) {
      // Der Platzhalter der Anhang-Auswertung wird zur echten Antwort.
      live.caret = h('span', { class: 'caret' });
      live.node._content.append(live.caret);
      scrollToEnd();
      return;
    }
    const node = renderMessage({
      id: event.message_id, role: 'assistant', content: '', thinking: '',
      model: event.model, created_at: new Date().toISOString(),
    });
    const caret = h('span', { class: 'caret' });
    node._content.append(caret);
    elements.list.append(node);
    live = { node, caret, thinkingNode: null };
    scrollToEnd();
    return;
  }

  if (!live) return;

  if (event.type === 'knowledge_progress') {
    live.knowledge = h('div', { class: 'step step--pending' },
      icon('search', 'step__icon'),
      h('span', { class: 'step__label', text: 'Wissensindex' }),
      h('span', { class: 'step__detail', text: event.message || 'wird abgeglichen …' }));
    live.node._steps.append(live.knowledge);
    scrollToEnd();
    return;
  }

  if (event.type === 'knowledge_ready') {
    live.knowledge?.remove();
    live.knowledge = null;
    return;
  }

  if (event.type === 'attachment_progress') {
    if (!live.progress) {
      live.progress = h('div', { class: 'step step--pending' },
        icon('clip', 'step__icon'),
        h('span', { class: 'step__label', text: 'Anhänge' }),
        h('span', { class: 'step__detail' }));
      live.node._steps.append(live.progress);
    }
    live.progress.querySelector('.step__detail').textContent =
      `${event.nummer}/${event.gesamt} — ${event.name} wird ausgewertet …`;
    scrollToEnd();
    return;
  }

  if (event.type === 'attachments_ready') {
    if (live.progress) {
      live.progress.className = 'step';
      live.progress.querySelector('.step__detail').textContent =
        `${event.anzahl} Datei(en) ausgewertet`;
      live.progress = null;
    }
    return;
  }

  if (event.type === 'tool_start') {
    live.pending = renderStep({ tool: event.tool, arguments: event.arguments, result: {} }, true);
    live.node._steps.append(live.pending);
    scrollToEnd();
    return;
  }

  if (event.type === 'tool_result') {
    const fertig = renderStep(event);
    if (live.pending) live.pending.replaceWith(fertig);
    else live.node._steps.append(fertig);
    live.pending = null;
    scrollToEnd();
    return;
  }

  if (event.type === 'thinking') {
    if (!live.thinkingNode) {
      live.thinkingNode = thinkingBlock('');
      live.node.querySelector('.msg__body').prepend(live.thinkingNode);
    }
    live.thinkingNode.querySelector('pre').textContent = run.thinking;
    return;
  }

  if (event.type === 'content') {
    const nearBottom = elements.scroll.scrollHeight - elements.scroll.scrollTop
      - elements.scroll.clientHeight < 120;
    live.node._content.innerHTML = renderMarkdown(run.content, markdownOptions());
    live.node._content.append(live.caret);
    if (nearBottom) scrollToEnd();
    return;
  }

  if (event.type === 'done' || event.type === 'stopped') {
    live.caret.remove();
    live.node._content.innerHTML = renderMarkdown(run.content, markdownOptions());
    if (run.changedFiles?.length) {
      refreshFileIndex();
      toast(run.changedFiles.length === 1
        ? `Im Vault gespeichert: ${run.changedFiles[0]}`
        : `${run.changedFiles.length} Dateien im Vault geschrieben.`, 'ok');
    }
    endLive();
    return;
  }

  if (event.type === 'error') {
    live.caret.remove();
    live.node.classList.add('msg--error');
    live.node.querySelector('.msg__body')
      .append(h('p', { style: 'color:var(--bad);margin:6px 0 0', text: event.message }));
    if (event.kind === 'offline' || event.kind === 'not_found') refreshStatus();
    endLive();
  }
}

function endLive() {
  live = null;
  setSending(false);
  renderRail(state.activeChatId);
}

/* --------------------------------------------- Antwort als Notiz */

async function saveAsNote(message) {
  if (!vaultReady()) {
    toast('Es ist kein Vault ausgewählt. Lege ihn in den Einstellungen fest.', 'bad');
    return;
  }
  const title = (elements.chat?.title || 'KI-Antwort').replace(/[\\/:*?"<>|]/g, '-').slice(0, 60);
  const suggestion = `02 KI-Notizen/${title}.md`;
  let target;
  try {
    target = (await api.uniquePath(suggestion)).path;
  } catch {
    target = suggestion;
  }

  const path = await promptDialog({
    title: 'Als Obsidian-Notiz speichern',
    description: 'Die Antwort wird als normale Markdown-Datei im Vault abgelegt.',
    label: 'Pfad im Vault', value: target, confirmLabel: 'Speichern', mono: true,
  });
  if (!path) return;

  const stamp = new Date().toISOString().slice(0, 10);
  const body = `# ${title}\n\n${message.content}\n\n---\nQuelle: Chat vom ${stamp} · Modell ${message.model || ''}\n`;

  try {
    await api.writeFile(path, body, false);
    toast(`Notiz gespeichert: ${path}`, 'ok');
    await refreshFileIndex();
  } catch (error) {
    if (error.kind === 'exists') {
      const ok = await confirmDialog({
        title: 'Datei überschreiben?',
        message: `„${path}" existiert bereits. Der bisherige Inhalt geht verloren.`,
        confirmLabel: 'Überschreiben', danger: true,
      });
      if (!ok) return;
      await api.writeFile(path, body, true);
      toast(`Notiz überschrieben: ${path}`, 'ok');
      await refreshFileIndex();
    } else {
      toast(error.message, 'bad');
    }
  }
}

/* --------------------------------------------------------- Kontext */

function renderContext(chat, messageCount = 0) {
  const status = state.status;
  clear(elements.context).append(
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: 'Modus' }),
      h('strong', { class: 'ctx-mode', text: activeMode.label }),
      h('p', { class: 'field__hint', text: activeMode.purpose === 'ask'
        ? 'Liest die Wissensbasis und ergänzt bei Bedarf klar gekennzeichnetes KI-Wissen. Keine Vault-Änderungen.'
        : 'Nimmt Informationen und Dateien auf und darf den Vault gezielt erweitern oder bearbeiten.' })),
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: 'Chat' }),
      h('dl', { class: 'ctx-kv' },
        h('dt', { text: 'Titel' }), h('dd', { text: chat?.title || '–' }),
        h('dt', { text: 'Erstellt' }), h('dd', { text: fmtDate(chat?.created_at) }),
        h('dt', { text: 'Nachrichten' }), h('dd', { text: String(messageCount) }))),
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: 'Modell' }),
      h('dl', { class: 'ctx-kv' },
        h('dt', { text: 'Name' }), h('dd', { text: status?.model?.name || '–' }),
        h('dt', { text: 'Bilder' }), h('dd', { text: status?.model?.vision ? 'ja' : 'nein' }),
        h('dt', { text: 'Thinking' }), h('dd', { text: status?.model?.thinking ? 'verfügbar' : 'nein' }))),
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: 'Aktionen' }),
      h('div', { class: 'row row--wrap' },
        h('button', { class: 'btn btn--sm', onclick: () => chat && renameChat(chat) }, icon('pencil'), 'Umbenennen'),
        h('button', { class: 'btn btn--sm btn--danger', onclick: () => chat && deleteChat(chat) }, icon('trash'), 'Löschen'))),
  );
}
