// Notizvorlagen: Standardbibliothek und eigene Markdown-Vorlagen im Vault.

import { api } from '../api.js';
import { h, icon, promptDialog, toast } from '../util.js';
import { navigate, refreshFileIndex } from '../store.js';

let view = null;

export async function mount({ el }) {
  view = h('div', { class: 'view' });
  el.main.append(view);
  await render();
}

async function render() {
  view.replaceChildren(h('p', { class: 'field__hint', text: 'Vorlagen werden geladen …' }));
  try {
    const data = await api.templates();
    view.replaceChildren(
      h('div', { class: 'page-head' },
        h('span', { class: 'label', text: 'Obsidian-Vorlagen' }),
        h('h1', { text: 'Vorlagen' }),
        h('p', { text: 'Die KI wählt bei Schreibaufträgen automatisch die passende Struktur und passt sie an den Inhalt an.' })),
      h('div', { class: 'row', style: 'margin-bottom:14px' },
        h('button', { class: 'btn btn--primary', disabled: !data.vault_ready, onclick: install },
          icon('plus'), 'Standardvorlagen im Vault installieren'),
        h('span', { class: 'field__hint', text: data.directory || '00 Templates' })),
      h('div', { class: 'grid grid--2' }, ...data.templates.map(templateCard)));
  } catch (error) {
    view.replaceChildren(h('p', { style: 'color:var(--bad)', text: error.message }));
  }
}

function templateCard(template) {
  const preview = template.content.replace(/^---[\s\S]*?---\s*/m, '').slice(0, 260);
  return h('div', { class: 'card' },
    h('div', { class: 'card__title' },
      h('span', { class: 'label', text: template.source === 'vault' ? 'Eigene Vorlage' : 'Mitgeliefert' }),
      h('span', { class: 'chip', text: template.name })),
    h('pre', { style: 'white-space:pre-wrap;color:var(--text-2);font:inherit;margin:0 0 12px', text: preview }),
    h('button', { class: 'btn btn--sm', onclick: () => createFrom(template) }, icon('note'), 'Notiz daraus anlegen'));
}

async function install() {
  try {
    const result = await api.installTemplates();
    toast(result.count ? `${result.count} Vorlagen installiert.` : 'Alle Vorlagen sind bereits vorhanden.', 'ok');
    await refreshFileIndex();
    await render();
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function createFrom(template) {
  const title = await promptDialog({
    title: `Neue Notiz · ${template.name}`,
    description: 'Titel eingeben; die Platzhalter bleiben zur weiteren Bearbeitung sichtbar.',
    label: 'Titel', value: 'Neue Notiz', confirmLabel: 'Anlegen',
  });
  if (!title) return;
  const safe = title.replace(/[\\/:*?"<>|]/g, '-');
  const wanted = `02 KI-Notizen/${safe}.md`;
  try {
    const path = (await api.uniquePath(wanted)).path;
    const date = new Date().toISOString().slice(0, 10);
    const content = template.content
      .replaceAll('{{datum}}', date)
      .replace(/{{(?:titel|thema|projektname|meetingtitel)}}/g, title);
    await api.writeFile(path, content, false);
    await refreshFileIndex();
    navigate(`/files?path=${encodeURIComponent(path)}`);
    toast(`Notiz angelegt: ${path}`, 'ok');
  } catch (error) {
    toast(error.message, 'bad');
  }
}
