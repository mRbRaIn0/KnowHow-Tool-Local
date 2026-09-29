import { api } from './api.js';
import { t } from './i18n.js';
import { h, toast } from './util.js';
import { refreshFileIndex } from './store.js';

export function writePreview(draft, chatId, resolved = () => {}) {
  const prefix = `preview-${draft.id}`;
  const path = h('input', { class: 'input input--mono', id: `${prefix}-path`,
    value: draft.path, readOnly: true });
  const editor = h('textarea', { class: 'textarea write-preview__editor', id: `${prefix}-content`,
    rows: 14, hidden: true }, draft.after);
  const diff = h('pre', { class: 'write-preview__diff', tabindex: '0',
    'aria-label': t('preview.diffLabel') });
  for (const line of (draft.diff || t('preview.noChange')).split('\n')) {
    diff.append(h('span', { class: line.startsWith('+') ? 'diff-add' : line.startsWith('-') ? 'diff-remove' : '',
      text: line + '\n' }));
  }
  const old = h('details', {}, h('summary', { text: t('preview.oldContent') }),
    h('pre', { class: 'write-preview__diff', text: draft.before || t('preview.newNote') }));
  const sources = h('details', {}, h('summary', { text: t('preview.sourceLinks', { n: draft.sources.length }) }),
    h('ul', {}, ...draft.sources.map(text => h('li', { text }))));
  const status = h('p', { class: 'field__hint', role: 'status', 'aria-live': 'polite' });
  const card = h('section', { class: 'card write-preview', 'aria-labelledby': `${prefix}-title` },
    h('h3', { id: `${prefix}-title`, text: t('preview.title') }),
    h('label', { class: 'label', for: `${prefix}-path`, text: t('preview.targetPath') }), path,
    diff, old, sources,
    h('label', { class: 'label', for: `${prefix}-content`, text: t('preview.newContent') }), editor,
    status);
  let submitting = false;
  const decide = async (accept) => {
    if (submitting) return;
    submitting = true;
    buttons.forEach(button => { button.disabled = true; });
    status.textContent = accept ? t('preview.applying') : t('preview.cancelling');
    try {
      await api.post(`/api/chats/${chatId}/preview/${draft.id}`, {
        accept, path: path.value, content: editor.value,
      });
      resolved();
      card.replaceChildren(h('p', { role: 'status', text: accept ? t('preview.applied') : t('preview.cancelled') }));
    } catch (error) {
      status.textContent = error.message;
      submitting = false;
      buttons.forEach(button => { button.disabled = false; });
    }
  };
  const buttons = [
    h('button', { class: 'btn', type: 'button', onclick: () => decide(false) }, t('common.cancel')),
    h('button', { class: 'btn', type: 'button', onclick: () => {
      editor.hidden = false;
      diff.hidden = true;
      path.readOnly = draft.path_locked || !draft.create;
      editor.focus();
      status.textContent = t('preview.editHint');
    } }, t('preview.adjust')),
    h('button', { class: 'btn btn--primary', type: 'button', onclick: () => decide(true) }, t('variants.apply')),
  ];
  card.append(h('div', { class: 'row row--wrap write-preview__actions' }, ...buttons));
  return card;
}

export function undoButton() {
  const button = h('button', { class: 'btn btn--sm', type: 'button', disabled: true },
    t('undo.button'));
  const hint = h('p', { class: 'field__hint', role: 'status', text: t('undo.checking') });
  const wrapper = h('div', {}, button, hint);
  api.get('/api/chats/vault/last-action').then(result => {
    button.disabled = !result.available || result.busy;
    hint.textContent = result.busy ? t('undo.busy')
      : result.available ? t('undo.available', { n: result.paths.length })
        : t('undo.none');
  }).catch(error => { hint.textContent = error.message; });
  button.addEventListener('click', async () => {
    button.disabled = true;
    hint.textContent = t('undo.running');
    try {
      const result = await api.post('/api/chats/vault/undo', {});
      hint.textContent = result.undone ? t('undo.done', { n: result.paths.length }) : t('undo.nothing');
      toast(hint.textContent);
      await refreshFileIndex();
    } catch (error) {
      hint.textContent = error.message;
      button.disabled = false;
    }
  });
  return wrapper;
}
