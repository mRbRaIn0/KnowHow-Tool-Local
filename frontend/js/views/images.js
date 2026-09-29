// Bilder: ablegen (Ziehen, Strg+V, Auswahl), ansehen, einbetten, auswerten lassen.

import { api } from '../api.js';
import { askAIWithFile, dropZone } from '../capture.js';
import { t } from '../i18n.js';
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
    view.append(h('div', { class: 'empty' }, icon('image'), h('h3', { text: t('common.noVault') })));
    return;
  }
  const grid = h('div');
  const count = h('span', { class: 'label' });
  const filter = h('input', { class: 'input', placeholder: t('images.filter'), 'aria-label': t('images.filter') });
  const render = () => {
    const query = filter.value.trim().toLowerCase();
    const all = state.files.filter((file) => file.kind === 'image');
    const images = all.filter((file) => !query || file.path.toLowerCase().includes(query));
    count.textContent = t('images.count', { n: all.length });
    grid.replaceChildren(images.length
      ? h('div', { class: 'asset-grid' }, ...images.slice(0, 400).map(card))
      : h('div', { class: 'empty' }, icon('image'), h('h3', { text: query ? t('images.noMatch') : t('images.none') })));
  };
  filter.addEventListener('input', render);

  const zone = dropZone({ label: t('images.dropLabel'), accept: 'image/*', onSaved: render });
  document.addEventListener('paste', zone.pasteHandler);
  cleanup.push(() => document.removeEventListener('paste', zone.pasteHandler), on('files', render));

  view.append(
    h('div', { class: 'page-head' }, count,
      h('h1', { text: t('nav.images') }),
      h('p', { text: t('images.lead', { folder: state.status?.vault?.attachments_dir || t('images.attachmentFolder') }) })),
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
      h('button', { class: 'icon-btn', title: t('images.copyEmbed'),
        onclick: () => copyText(`![[${file.path}]]`) }, icon('copy')),
      h('button', { class: 'icon-btn', title: t('images.aiAnalyse'),
        onclick: () => askAIWithFile(file.path, t('images.analysePrompt')) },
      icon('chat'))));
}
