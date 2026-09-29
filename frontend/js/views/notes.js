// Notizen: schnell erfassen, finden und von der KI überarbeiten lassen.
// Obsidian bleibt die endgültige Ansicht; hier geht es ums Tempo.
// Rechts steht der Markdown-Spickzettel.

import { api } from '../api.js';
import { askAI, wikiTarget } from '../capture.js';
import { renderCheatSheet } from '../cheatsheet.js';
import { t } from '../i18n.js';
import { h, icon, toast } from '../util.js';
import { navigate, refreshFileIndex, state, vaultReady } from '../store.js';

export async function mount({ el }) {
  const view = h('div', { class: 'view' });
  el.main.append(view);
  if (!vaultReady()) {
    view.append(h('div', { class: 'empty' }, icon('note'), h('h3', { text: t('common.noVault') })));
    return;
  }

  const input = h('input', { class: 'input', placeholder: t('notes.filter'), 'aria-label': t('notes.filter') });
  const list = h('div', { class: 'list' });
  const count = h('span', { class: 'label' });
  const render = () => {
    const notes = state.files.filter((file) => file.kind === 'note');
    const query = input.value.trim().toLowerCase();
    const filtered = notes.filter((file) => !query || file.path.toLowerCase().includes(query));
    count.textContent = t('notes.count', { n: notes.length });
    list.replaceChildren(...filtered.slice(0, 300).map((file) => h('div', { class: 'list__item' },
      icon('note'),
      h('button', { class: 'list__main', style: 'text-align:left',
        onclick: () => navigate(`/files?path=${encodeURIComponent(file.path)}`) },
        h('span', { class: 'list__title', text: file.name }),
        h('span', { class: 'list__sub', text: file.path })),
      h('button', { class: 'btn btn--sm', title: t('notes.aiEditHint'),
        onclick: () => askAI(restructure(file.path)) },
      t('notes.aiEdit')))));
  };
  input.addEventListener('input', render);

  const capture = captureCard(render);
  view.append(
    h('div', { class: 'page-head' }, count,
      h('h1', { text: t('nav.notes') }),
      h('p', { text: t('notes.lead') })),
    capture.card,
    h('div', { class: 'row', style: 'margin:18px 0 12px' }, input,
      h('button', { class: 'btn', onclick: () => navigate('/files?new=1') }, icon('plus'), t('notes.emptyNote'))),
    list,
  );
  render();

  // Rechte Seitenleiste: Spickzettel; Einfügen geht direkt in den Erfassungstext.
  renderCheatSheet(el.context, { onInsert: capture.insert });
}

// Löst im Arbeitschat eine vollständige Neustrukturierung aus; Informationen bleiben erhalten.
const restructure = (path) => t('notes.restructurePrompt', { link: `[[${wikiTarget(path)}]]` });

/** Titel + Text → sofort gespeicherte Notiz, optional direkt weiter zur KI. */
function captureCard(onSaved) {
  const folders = [...new Set(state.files.map((file) => file.path.includes('/') ? file.path.slice(0, file.path.lastIndexOf('/')) : ''))]
    .filter(Boolean).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base', numeric: true }));
  const title = h('input', { class: 'input', placeholder: t('notes.titleOptional'), 'aria-label': t('chat.titleLabel') });
  const folder = h('input', { class: 'input input--mono', placeholder: t('notes.folderPlaceholder'),
    list: 'capture-folders', 'aria-label': t('notes.folder') });
  const text = h('textarea', { class: 'textarea', rows: 5, 'aria-label': t('notes.text'),
    placeholder: t('notes.textPlaceholder') });

  const save = async (thenAI) => {
    const body = text.value.trim();
    if (!body && !title.value.trim()) { text.focus(); return; }
    const name = (title.value.trim() || body.split('\n')[0].replace(/^#+\s*/, '').slice(0, 60) || t('notes.defaultName'))
      .replace(/[\\/:*?"<>|#^[\]]/g, '-').trim() || t('notes.defaultName');
    const dir = folder.value.trim().replace(/^\/+|\/+$/g, '');
    const content = body.startsWith('#') ? `${body}\n` : `# ${name}\n\n${body}\n`;
    try {
      const result = await api.writeFile(`${dir ? `${dir}/` : ''}${name}.md`, content, false, true);
      toast(t('chat.noteSaved', { path: result.path }), 'ok');
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

  /** Fügt einen Spickzettel-Ausschnitt an der Cursorposition ein (bzw. am Ende). */
  let caretPosition = null;  // beim Verlassen des Feldes gemerkt; nie fokussiert → Ende
  text.addEventListener('blur', () => { caretPosition = [text.selectionStart, text.selectionEnd]; });
  const insert = (snippet) => {
    const [start, end] = caretPosition || [text.value.length, text.value.length];
    const before = text.value.slice(0, start);
    const lead = before && !before.endsWith('\n') ? '\n' : '';
    text.value = `${before}${lead}${snippet}\n${text.value.slice(end)}`;
    const caret = before.length + lead.length + snippet.length + 1;
    text.focus();
    text.setSelectionRange(caret, caret);
  };

  const card = h('section', { class: 'card capture' },
    h('div', { class: 'card__title' }, h('span', { class: 'label', text: t('notes.captureTitle') })),
    h('div', { class: 'row row--wrap' }, title, folder),
    h('datalist', { id: 'capture-folders' }, ...folders.map((value) => h('option', { value }))),
    text,
    h('div', { class: 'row row--wrap' },
      h('span', { class: 'field__hint', text: t('notes.captureHint') }),
      h('span', { class: 'spacer' }),
      h('button', { class: 'btn', onclick: () => save(true) }, t('notes.saveAndStructure')),
      h('button', { class: 'btn btn--primary', onclick: () => save(false) }, icon('save'), t('common.save'))));
  return { card, insert };
}
