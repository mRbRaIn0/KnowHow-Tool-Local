import { api } from './api.js';
import { h, toast } from './util.js';
import { refreshFileIndex } from './store.js';

export function writePreview(draft, chatId, resolved = () => {}) {
  const prefix = `preview-${draft.id}`;
  const path = h('input', { class: 'input input--mono', id: `${prefix}-path`,
    value: draft.path, readOnly: true });
  const editor = h('textarea', { class: 'textarea write-preview__editor', id: `${prefix}-content`,
    rows: 14, hidden: true }, draft.after);
  const diff = h('pre', { class: 'write-preview__diff', tabindex: '0',
    'aria-label': 'Änderungen: Minus entfernt, Plus hinzugefügt' });
  for (const line of (draft.diff || '(Keine Textänderung)').split('\n')) {
    diff.append(h('span', { class: line.startsWith('+') ? 'diff-add' : line.startsWith('-') ? 'diff-remove' : '',
      text: line + '\n' }));
  }
  const old = h('details', {}, h('summary', { text: 'Bisheriger vollständiger Inhalt' }),
    h('pre', { class: 'write-preview__diff', text: draft.before || '(Neue Notiz)' }));
  const sources = h('details', {}, h('summary', { text: `Quellenlinks (${draft.sources.length})` }),
    h('ul', {}, ...draft.sources.map(text => h('li', { text }))));
  const status = h('p', { class: 'field__hint', role: 'status', 'aria-live': 'polite' });
  const card = h('section', { class: 'card write-preview', 'aria-labelledby': `${prefix}-title` },
    h('h3', { id: `${prefix}-title`, text: 'Schreibvorschau · Alt → Neu' }),
    h('label', { class: 'label', for: `${prefix}-path`, text: 'Zielpfad im Vault' }), path,
    diff, old, sources,
    h('label', { class: 'label', for: `${prefix}-content`, text: 'Neuer Inhalt · nach „Anpassen“ editierbar' }), editor,
    status);
  let submitting = false;
  const decide = async (accept) => {
    if (submitting) return;
    submitting = true;
    buttons.forEach(button => { button.disabled = true; });
    status.textContent = accept ? 'Wird übernommen …' : 'Auftrag wird abgebrochen …';
    try {
      await api.post(`/api/chats/${chatId}/preview/${draft.id}`, {
        accept, path: path.value, content: editor.value,
      });
      resolved();
      card.replaceChildren(h('p', { role: 'status', text: accept ? 'Vorschau übernommen.' : 'Vorschau abgebrochen.' }));
    } catch (error) {
      status.textContent = error.message;
      submitting = false;
      buttons.forEach(button => { button.disabled = false; });
    }
  };
  const buttons = [
    h('button', { class: 'btn', type: 'button', onclick: () => decide(false) }, 'Abbrechen'),
    h('button', { class: 'btn', type: 'button', onclick: () => {
      editor.hidden = false;
      diff.hidden = true;
      path.readOnly = draft.path_locked || !draft.create;
      editor.focus();
      status.textContent = 'Inhalt bearbeiten und anschließend übernehmen. Bestehende Notizen behalten ihren Zielpfad.';
    } }, 'Anpassen'),
    h('button', { class: 'btn btn--primary', type: 'button', onclick: () => decide(true) }, 'Übernehmen'),
  ];
  card.append(h('div', { class: 'row row--wrap write-preview__actions' }, ...buttons));
  return card;
}

export function undoButton() {
  const button = h('button', { class: 'btn btn--sm', type: 'button', disabled: true },
    'Letzten Vault-Auftrag rückgängig');
  const hint = h('p', { class: 'field__hint', role: 'status', text: 'Rücknahme wird geprüft …' });
  const wrapper = h('div', {}, button, hint);
  api.get('/api/chats/vault/last-action').then(result => {
    button.disabled = !result.available || result.busy;
    hint.textContent = result.busy ? 'Während eines Auftrags nicht verfügbar.'
      : result.available ? `${result.paths.length} betroffene Dateien. Neuere Änderungen werden geschützt.`
        : 'Noch kein Vault-Auftrag zum Rückgängigmachen.';
  }).catch(error => { hint.textContent = error.message; });
  button.addEventListener('click', async () => {
    button.disabled = true;
    hint.textContent = 'Wird rückgängig gemacht …';
    try {
      const result = await api.post('/api/chats/vault/undo', {});
      hint.textContent = result.undone ? `${result.paths.length} Dateien zurückgesetzt.` : 'Keine Änderung verfügbar.';
      toast(hint.textContent);
      await refreshFileIndex();
    } catch (error) {
      hint.textContent = error.message;
      button.disabled = false;
    }
  });
  return wrapper;
}
