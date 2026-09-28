// Notizen: schnell erfassen, finden und von der KI überarbeiten lassen.
// Obsidian bleibt die endgültige Ansicht; hier geht es ums Tempo.

import { api } from '../api.js';
import { askAI, wikiTarget } from '../capture.js';
import { h, icon, toast } from '../util.js';
import { navigate, refreshFileIndex, state, vaultReady } from '../store.js';

export async function mount({ el }) {
  const view = h('div', { class: 'view' });
  el.main.append(view);
  if (!vaultReady()) {
    view.append(h('div', { class: 'empty' }, icon('note'), h('h3', { text: 'Kein Vault ausgewählt' })));
    return;
  }

  const input = h('input', { class: 'input', placeholder: 'Notizen filtern …', 'aria-label': 'Notizen filtern' });
  const list = h('div', { class: 'list' });
  const count = h('span', { class: 'label' });
  const render = () => {
    const notes = state.files.filter((file) => file.kind === 'note');
    const query = input.value.trim().toLowerCase();
    const filtered = notes.filter((file) => !query || file.path.toLowerCase().includes(query));
    count.textContent = `${notes.length} Markdown-Dateien`;
    list.replaceChildren(...filtered.slice(0, 300).map((file) => h('div', { class: 'list__item' },
      icon('note'),
      h('button', { class: 'list__main', style: 'text-align:left',
        onclick: () => navigate(`/files?path=${encodeURIComponent(file.path)}`) },
        h('span', { class: 'list__title', text: file.name }),
        h('span', { class: 'list__sub', text: file.path })),
      h('button', { class: 'btn btn--sm', title: 'Im Arbeitschat überarbeiten lassen',
        onclick: () => askAI(restructure(file.path)) },
      'Mit KI überarbeiten'))));
  };
  input.addEventListener('input', render);

  view.append(
    h('div', { class: 'page-head' }, count,
      h('h1', { text: 'Notizen' }),
      h('p', { text: 'Schnell erfassen, finden und mit der KI verbessern. Alles bleibt eine normale Obsidian-Notiz.' })),
    captureCard(render),
    h('div', { class: 'row', style: 'margin:18px 0 12px' }, input,
      h('button', { class: 'btn', onclick: () => navigate('/files?new=1') }, icon('plus'), 'Leere Notiz')),
    list,
  );
  render();
}

// Löst im Arbeitschat eine vollständige Neustrukturierung aus; Informationen bleiben erhalten.
const restructure = (path) => `Überarbeite die Struktur komplett neu, alle Informationen bleiben erhalten: [[${wikiTarget(path)}]]`;

/** Titel + Text → sofort gespeicherte Notiz, optional direkt weiter zur KI. */
function captureCard(onSaved) {
  const folders = [...new Set(state.files.map((file) => file.path.includes('/') ? file.path.slice(0, file.path.lastIndexOf('/')) : ''))]
    .filter(Boolean).sort((a, b) => a.localeCompare(b, 'de'));
  const title = h('input', { class: 'input', placeholder: 'Titel (optional)', 'aria-label': 'Titel' });
  const folder = h('input', { class: 'input input--mono', placeholder: 'Ordner (leer = Vault-Stamm)',
    list: 'capture-folders', 'aria-label': 'Ordner' });
  const text = h('textarea', { class: 'textarea', rows: 5, 'aria-label': 'Notiztext',
    placeholder: 'Stichpunkte, Gedanken, kopierter Text … Markdown ist erlaubt.' });

  const save = async (thenAI) => {
    const body = text.value.trim();
    if (!body && !title.value.trim()) { text.focus(); return; }
    const name = (title.value.trim() || body.split('\n')[0].replace(/^#+\s*/, '').slice(0, 60) || 'Notiz')
      .replace(/[\\/:*?"<>|#^[\]]/g, '-').trim() || 'Notiz';
    const dir = folder.value.trim().replace(/^\/+|\/+$/g, '');
    const content = body.startsWith('#') ? `${body}\n` : `# ${name}\n\n${body}\n`;
    try {
      const result = await api.writeFile(`${dir ? `${dir}/` : ''}${name}.md`, content, false, true);
      toast(`Notiz gespeichert: ${result.path}`, 'ok');
      title.value = '';
      text.value = '';
      await refreshFileIndex();
      onSaved();
      if (thenAI) askAI(restructure(result.path));
    } catch (error) {
      toast(error.message, 'bad');
    }
  };
  text.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) { event.preventDefault(); save(false); }
  });

  return h('section', { class: 'card capture' },
    h('div', { class: 'card__title' }, h('span', { class: 'label', text: 'Schnell erfassen' })),
    h('div', { class: 'row row--wrap' }, title, folder),
    h('datalist', { id: 'capture-folders' }, ...folders.map((value) => h('option', { value }))),
    text,
    h('div', { class: 'row row--wrap' },
      h('span', { class: 'field__hint', text: 'Strg+Enter speichert · gleiche Namen werden nummeriert' }),
      h('span', { class: 'spacer' }),
      h('button', { class: 'btn', onclick: () => save(true) }, 'Speichern + KI strukturieren'),
      h('button', { class: 'btn btn--primary', onclick: () => save(false) }, icon('save'), 'Speichern')));
}
