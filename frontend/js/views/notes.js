// Schneller Überblick über alle Markdown-Notizen im Vault.

import { h, icon } from '../util.js';
import { navigate, state, vaultReady } from '../store.js';

export async function mount({ el }) {
  const view = h('div', { class: 'view' });
  el.main.append(view);
  if (!vaultReady()) {
    view.append(h('div', { class: 'empty' }, icon('note'), h('h3', { text: 'Kein Vault ausgewählt' })));
    return;
  }

  const notes = state.files.filter((file) => file.kind === 'note');
  const input = h('input', { class: 'input', placeholder: 'Notizen filtern …' });
  const list = h('div', { class: 'list' });
  const render = () => {
    const query = input.value.trim().toLowerCase();
    const filtered = notes.filter((file) => !query || file.path.toLowerCase().includes(query));
    list.replaceChildren(...filtered.map((file) => h('button', {
      class: 'list__item', onclick: () => navigate(`/files?path=${encodeURIComponent(file.path)}`),
    }, icon('note'), h('span', { class: 'list__main' },
      h('span', { class: 'list__title', text: file.name }),
      h('span', { class: 'list__sub', text: file.path })))));
  };
  input.addEventListener('input', render);
  view.append(
    h('div', { class: 'page-head' }, h('span', { class: 'label', text: `${notes.length} Markdown-Dateien` }),
      h('h1', { text: 'Notizen' }), h('p', { text: 'Alle Obsidian-Notizen, unabhängig vom Ordner.' })),
    h('div', { class: 'row', style: 'margin-bottom:14px' }, input,
      h('button', { class: 'btn btn--primary', onclick: () => navigate('/files?new=1') }, icon('plus'), 'Neue Notiz')),
    list,
  );
  render();
}
