// Bilder: ablegen (Ziehen, Strg+V, Auswahl), ansehen, einbetten, auswerten lassen.

import { api } from '../api.js';
import { askAIWithFile, dropZone } from '../capture.js';
import { copyText, h, icon } from '../util.js';
import { navigate, on, state, vaultReady } from '../store.js';

let cleanup = [];
export function unmount() {
  for (const off of cleanup) off();
  cleanup = [];
}

export async function mount({ el }) {
  const view = h('div', { class: 'view' });
  el.main.append(view);
  if (!vaultReady()) {
    view.append(h('div', { class: 'empty' }, icon('image'), h('h3', { text: 'Kein Vault ausgewählt' })));
    return;
  }
  const grid = h('div');
  const count = h('span', { class: 'label' });
  const filter = h('input', { class: 'input', placeholder: 'Bilder filtern …', 'aria-label': 'Bilder filtern' });
  const render = () => {
    const query = filter.value.trim().toLowerCase();
    const images = state.files.filter((file) => file.kind === 'image'
      && (!query || file.path.toLowerCase().includes(query)));
    count.textContent = `${state.files.filter((file) => file.kind === 'image').length} Bilder`;
    grid.replaceChildren(images.length
      ? h('div', { class: 'asset-grid' }, ...images.slice(0, 400).map(card))
      : h('div', { class: 'empty' }, icon('image'), h('h3', { text: query ? 'Kein passendes Bild' : 'Noch keine Bilder im Vault' })));
  };
  filter.addEventListener('input', render);

  const zone = dropZone({ label: 'Bilder hier ablegen', accept: 'image/*', onSaved: render });
  document.addEventListener('paste', zone.pasteHandler);
  cleanup.push(() => document.removeEventListener('paste', zone.pasteHandler), on('files', render));

  view.append(
    h('div', { class: 'page-head' }, count,
      h('h1', { text: 'Bilder' }),
      h('p', { text: `Screenshots, Fotos und Scans. Neue Bilder landen sofort in „${state.status?.vault?.attachments_dir || 'dem Anhangordner'}“.` })),
    zone,
    h('div', { class: 'row', style: 'margin:16px 0 12px' }, filter),
    grid,
  );
  render();
}

function card(file) {
  return h('div', { class: 'asset-card', title: file.path },
    h('button', { class: 'asset-card__open', onclick: () => navigate(`/files?path=${encodeURIComponent(file.path)}`) },
      h('img', { src: api.rawUrl(file.path), alt: file.name, loading: 'lazy' }),
      h('span', { text: file.name })),
    h('span', { class: 'asset-card__tools' },
      h('button', { class: 'icon-btn', title: 'Einbettung kopieren (![[…]])',
        onclick: () => copyText(`![[${file.path}]]`) }, icon('copy')),
      h('button', { class: 'icon-btn', title: 'Mit KI auswerten und als Notiz speichern',
        onclick: () => askAIWithFile(file.path, 'Werte das angehängte Bild aus und erstelle daraus eine strukturierte Notiz mit eingebettetem Bild.') },
      icon('chat'))));
}
