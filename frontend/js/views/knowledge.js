// Hybride lokale Wissenssuche mit Datei- und Seitenquellen.

import { api } from '../api.js';
import { h, icon, toast } from '../util.js';
import { navigate, vaultReady } from '../store.js';

let host = null;
let statusNode = null;
let resultsNode = null;
let generation = 0;
export function unmount() { generation++; }

export async function mount({ route, el }) {
  const ticket = ++generation;
  host = el.main;
  const query = route.params.q || '';
  const input = h('input', {
    class: 'input', value: query,
    placeholder: 'Vault oder freigegebene Bibliotheksinhalte durchsuchen …',
  });
  const form = h('form', { class: 'row', style: 'margin-bottom:16px' },
    input,
    h('button', { class: 'btn btn--primary', type: 'submit' }, icon('search'), 'Suchen'));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const q = input.value.trim();
    if (q) search(q);
  });

  statusNode = h('div', { class: 'card', style: 'margin-bottom:14px' });
  resultsNode = h('div');
  host.append(h('div', { class: 'view' },
    h('div', { class: 'page-head' },
      h('span', { class: 'label', text: 'Lokaler Wissensindex' }),
      h('h1', { text: 'Wissen' }),
      h('p', { text: 'Hybride Suche nach Stichwort und Bedeutung – mit Datei- und PDF-Seitenquelle.' })),
    form, statusNode, resultsNode));

  if (!vaultReady()) {
    statusNode.replaceChildren(h('p', { class: 'field__hint', text: 'Kein Vault gewählt. Freigegebene Bibliotheksinhalte können trotzdem durchsucht werden.' }));
    if (query) await search(query);
    return;
  }
  await renderStatus();
  if (query && ticket === generation) await search(query);
}

async function renderStatus() {
  const ticket = generation;
  try {
    const status = await api.knowledgeStatus();
    if (ticket !== generation) return;
    statusNode.replaceChildren(
      h('div', { class: 'card__title' },
        h('span', { class: 'label', text: 'Index' }),
        h('button', { class: 'btn btn--sm', onclick: rebuild }, icon('knowledge'), 'Neu aufbauen')),
      h('div', { class: 'stat-strip', style: 'margin:0' },
        stat('Dateien', status.files), stat('Abschnitte', status.chunks),
        stat('Vektoren', status.embedded)),
      h('p', { class: 'field__hint', style: 'margin:10px 0 0',
        text: `Embedding-Modell: ${status.model || 'nicht konfiguriert'}` }));
  } catch (error) {
    if (ticket !== generation) return;
    statusNode.replaceChildren(h('p', { class: 'field__hint', text: error.message }));
  }
}

function stat(label, value) {
  return h('div', { class: 'stat' },
    h('div', { class: 'stat__value', text: String(value || 0) }),
    h('div', { class: 'stat__label', text: label }));
}

async function rebuild() {
  const ticket = generation;
  statusNode.classList.add('is-loading');
  toast('Wissensindex wird lokal aufgebaut …');
  try {
    const result = await api.reindexKnowledge();
    if (ticket !== generation) return;
    toast(`${result.files} Dateien · ${result.chunks} Abschnitte indexiert.`, 'ok');
    await renderStatus();
  } catch (error) {
    if (ticket !== generation) return;
    toast(error.message, 'bad');
  } finally {
    if (ticket === generation) statusNode.classList.remove('is-loading');
  }
}

async function search(query) {
  const ticket = generation;
  resultsNode.replaceChildren(h('p', { class: 'field__hint', text: 'Freigegebenes Wissen wird durchsucht …' }));
  try {
    const data = await api.knowledgeSearch(query, 10);
    if (ticket !== generation) return;
    const items = data.results || [];
    if (!items.length) {
      resultsNode.replaceChildren(h('div', { class: 'empty' }, icon('search'),
        h('h3', { text: 'Keine passende Quelle' }),
        h('p', { text: 'Versuche einen anderen Begriff oder baue den Index neu auf.' })));
      return;
    }
    const resultRows = items.map((item) => h('button', {
        class: 'list__item',
        onclick: () => navigate('/files?path=' + encodeURIComponent(item.path)),
      }, icon('note'), h('span', { class: 'list__main' },
        h('span', { class: 'list__title', text: 'Vault · ' + item.path }),
        h('span', { class: 'list__sub', text: `${item.page ? `Seite ${item.page} · ` : ''}${item.snippet}` })),
      h('span', { class: 'chip', text: `${Math.round(item.score * 100)} %` })));

    resultsNode.replaceChildren(
      h('div', { class: 'page-head', style: 'margin-bottom:10px' },
        h('span', { class: 'label', text: `${items.length} Quellen${data.semantic ? ' · semantisch' : ' · Stichwort'}` })),
      h('div', { class: 'list' }, ...resultRows),
    );
  } catch (error) {
    if (ticket !== generation) return;
    resultsNode.replaceChildren(h('p', { style: 'color:var(--bad)', text: error.message }));
  }
}
