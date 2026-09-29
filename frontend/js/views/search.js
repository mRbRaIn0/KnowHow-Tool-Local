// Suchergebnisse über Notizen, Dokumente, Bilder, Ordner und Chats.

import { api } from '../api.js';
import { t } from '../i18n.js';
import { esc, fill, h, icon, kv, toast } from '../util.js';
import { navigate } from '../store.js';

const GROUPS = [
  ['notes', 'nav.notes', 'note'],
  ['documents', 'search.documents', 'files'],
  ['images', 'nav.images', 'image'],
  ['folders', 'search.folders', 'folder-open'],
  ['chats', 'dash.chats', 'chat'],
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
      h('span', { class: 'label', text: t('search.label') }),
      h('h1', { text: query || t('search.whatFor') }),
      h('p', { text: t('search.lead') })),
  );

  if (!query) {
    view.append(h('div', { class: 'empty' }, icon('search'),
      h('p', { text: t('search.enterTerm') })));
    return;
  }

  const results = h('div', {}, h('p', { class: 'field__hint', text: t('search.searching') }));
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
      h('h3', { text: t('search.nothing') }),
      h('p', { text: t('search.nothingText', { query: data.query }) })));
    contextHost.replaceChildren();
    return;
  }

  const blocks = [];
  for (const [key, labelKey, iconName] of GROUPS) {
    const items = data.groups[key] || [];
    if (!items.length) continue;
    blocks.push(h('div', { class: 'result-group' },
      h('div', { class: 'result-group__head' },
        h('span', { class: 'label', text: t(labelKey) }),
        h('span', { class: 'result-group__count', text: `${items.length}` })),
      h('div', { class: 'list' },
        ...items.map((item) => resultRow(key, item, iconName, data.query)))));
  }
  host.replaceChildren(...blocks);

  fill(contextHost, h('div', { class: 'ctx-block' },
    h('span', { class: 'label', text: t('search.hits') }),
    kv(GROUPS.map(([key, labelKey]) => [t(labelKey), String((data.groups[key] || []).length)]))));
}

function resultRow(group, item, iconName, query) {
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
    item.line ? h('span', { class: 'list__meta', text: t('search.line', { n: item.line }) }) : null);
}

function highlight(text, query) {
  const safe = esc(text || '');
  if (!query) return safe;
  const pattern = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
  return safe.replace(pattern, '<mark>$1</mark>');
}
