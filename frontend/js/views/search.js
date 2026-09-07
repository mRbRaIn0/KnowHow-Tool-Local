// Suchergebnisse über Notizen, Dokumente, Bilder, Ordner und Chats.

import { api } from '../api.js';
import { esc, h, icon, toast } from '../util.js';
import { navigate, state } from '../store.js';

const GROUPS = [
  ['notes', 'Notizen', 'note'],
  ['documents', 'Dokumente', 'files'],
  ['images', 'Bilder', 'image'],
  ['folders', 'Ordner', 'folder-open'],
  ['chats', 'Chats', 'chat'],
  ['library', 'NAS-Bibliothek', 'files'],
];
let generation = 0;
export function unmount() { generation++; }

export async function mount({ route, el }) {
  const ticket = ++generation;
  const query = route.params.q || '';
  const view = h('div', { class: 'view' });
  el.main.append(view);

  const input = document.getElementById('omnisearch-input');
  if (input && input.value !== query) input.value = query;

  view.append(
    h('div', { class: 'page-head' },
      h('span', { class: 'label', text: 'Suche' }),
      h('h1', { text: query || 'Wonach suchst du?' }),
      h('p', { text: 'Durchsucht Dateinamen, Notizinhalte und Chatverläufe — alles lokal.' })),
  );

  if (!query) {
    view.append(h('div', { class: 'empty' }, icon('search'),
      h('p', { text: 'Gib oben einen Suchbegriff ein.' })));
    return;
  }

  const results = h('div', {}, h('p', { class: 'field__hint', text: 'wird gesucht …' }));
  view.append(results);

  try {
    const data = await api.search(query);
    if (ticket !== generation) return;
    render(results, data, el.context);
  } catch (error) {
    if (ticket !== generation) return;
    results.replaceChildren(h('p', { class: 'field__hint', text: error.message }));
    toast(error.message, 'bad');
  }
}

function render(host, data, contextHost) {
  if (!data.total) {
    host.replaceChildren(h('div', { class: 'empty' },
      h('h3', { text: 'Nichts gefunden' }),
      h('p', { text: `Für „${data.query}" gibt es weder Dateien noch Chatnachrichten.` })));
    contextHost.replaceChildren();
    return;
  }

  const blocks = [];
  for (const [key, label, iconName] of GROUPS) {
    const items = data.groups[key] || [];
    if (!items.length) continue;
    blocks.push(h('div', { class: 'result-group' },
      h('div', { class: 'result-group__head' },
        h('span', { class: 'label', text: label }),
        h('span', { class: 'result-group__count', text: `${items.length}` })),
      h('div', { class: 'list' },
        ...items.map((item) => resultRow(key, item, iconName, data.query)))));
  }
  host.replaceChildren(...blocks);

  contextHost.replaceChildren(h('div', { class: 'ctx-block' },
    h('span', { class: 'label', text: 'Treffer' }),
    h('dl', { class: 'ctx-kv' },
      ...GROUPS.flatMap(([key, label]) => [
        h('dt', { text: label }),
        h('dd', { text: String((data.groups[key] || []).length) }),
      ]))));
}

function resultRow(group, item, iconName, query) {
  if (group === 'library') {
    return h('button', { class: 'list__item', onclick: () => navigate('/library?item=' + encodeURIComponent(item.id)) },
      icon('files'), h('span', { class: 'list__main' },
        h('span', { class: 'list__title', text: item.name }),
        h('span', { class: 'list__sub', text: item.source_name + ' / ' + item.path + ' · ' + item.tags.join(', ') })));
  }
  if (group === 'chats') {
    return h('button', {
      class: 'list__item', onclick: () => navigate(`/chat/${item.chat_id}`),
    }, icon('chat'),
      h('span', { class: 'list__main' },
        h('span', { class: 'list__title', text: item.chat_title }),
        h('span', { class: 'list__sub', html: highlight(item.snippet, query) })));
  }

  if (group === 'folders') {
    return h('button', {
      class: 'list__item', onclick: () => navigate(`/files?path=${encodeURIComponent(item.path)}`),
    }, icon('folder-open'),
      h('span', { class: 'list__main' },
        h('span', { class: 'list__title', text: item.name }),
        h('span', { class: 'list__sub', text: item.path })));
  }

  return h('button', {
    class: 'list__item', onclick: () => navigate(`/files?path=${encodeURIComponent(item.path)}`),
  }, icon(iconName),
    h('span', { class: 'list__main' },
      h('span', { class: 'list__title', html: highlight(item.name, query) }),
      h('span', { class: 'list__sub', html: item.snippet ? highlight(item.snippet, query) : esc(item.path) })),
    item.line ? h('span', { class: 'list__meta', text: `Z. ${item.line}` }) : null);
}

function highlight(text, query) {
  const safe = esc(text || '');
  if (!query) return safe;
  const pattern = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
  return safe.replace(pattern, '<mark>$1</mark>');
}
