// Bildübersicht über den gesamten Vault.

import { api } from '../api.js';
import { h, icon } from '../util.js';
import { navigate, state, vaultReady } from '../store.js';

export async function mount({ el }) {
  const view = h('div', { class: 'view' });
  el.main.append(view);
  if (!vaultReady()) {
    view.append(h('div', { class: 'empty' }, icon('image'), h('h3', { text: 'Kein Vault ausgewählt' })));
    return;
  }
  const images = state.files.filter((file) => file.kind === 'image');
  view.append(
    h('div', { class: 'page-head' },
      h('span', { class: 'label', text: `${images.length} Bilder` }),
      h('h1', { text: 'Bilder' }),
      h('p', { text: 'Screenshots, Fotos und Scans im Vault. Die lokale KI analysiert sie im Chat.' })),
    images.length
      ? h('div', { class: 'asset-grid' }, ...images.map((file) => h('button', {
        class: 'asset-card', title: file.path,
        onclick: () => navigate(`/files?path=${encodeURIComponent(file.path)}`),
      }, h('img', { src: api.rawUrl(file.path), alt: file.name, loading: 'lazy' }),
      h('span', { text: file.name }))))
      : h('div', { class: 'empty' }, icon('image'), h('h3', { text: 'Noch keine Bilder im Vault' })),
  );
}
