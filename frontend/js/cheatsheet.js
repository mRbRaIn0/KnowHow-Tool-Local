// Obsidian-/Markdown-Spickzettel für die rechte Seitenleiste des Notizen-Bereichs.
// Der Zweck: Syntax sehen → kopieren (oder per Klick einfügen) → Notiz schreiben.
// Die Beispieltexte stehen in den Sprachdateien (cheat.<gruppe>.code).

import { copyText, fill, h, icon, toast } from './util.js';
import { t } from './i18n.js';

export const CHEAT_GROUPS = [
  'headings', 'emphasis', 'lists', 'tasks', 'quote', 'code',
  'links', 'tag', 'table', 'rule', 'callouts',
];

export const cheatCode = (group) => t(`cheat.${group}.code`);
export const cheatSheetText = () => CHEAT_GROUPS.map(cheatCode).join('\n\n');

/**
 * Füllt die Seitenleiste. onInsert(text) fügt einen Ausschnitt in die aktuelle
 * Notiz ein; ohne onInsert gibt es nur „Kopieren“.
 */
export function renderCheatSheet(host, { onInsert = null } = {}) {
  const groups = CHEAT_GROUPS.map((group) => {
    const code = cheatCode(group);
    return h('section', { class: 'cheat__group' },
      h('div', { class: 'cheat__head' },
        h('span', { class: 'label', text: t(`cheat.${group}.title`) }),
        h('span', { class: 'spacer' }),
        h('button', { class: 'icon-btn', type: 'button', title: t('cheat.copy'), 'aria-label': `${t('cheat.copy')}: ${t(`cheat.${group}.title`)}`,
          onclick: () => copyText(code) }, icon('copy')),
        onInsert
          ? h('button', { class: 'icon-btn', type: 'button', title: t('cheat.insert'), 'aria-label': `${t('cheat.insert')}: ${t(`cheat.${group}.title`)}`,
            onclick: () => { onInsert(code); toast(t('cheat.inserted'), 'ok'); } }, icon('plus'))
          : null),
      h('pre', { class: 'cheat__code', tabindex: '0', title: t('cheat.clickToCopy'),
        onclick: () => copyText(code) }, h('code', { text: code })));
  });

  fill(host,
    h('div', { class: 'ctx-block cheat' },
      h('div', { class: 'cheat__head' },
        h('span', { class: 'label', text: t('cheat.title') }),
        h('span', { class: 'spacer' }),
        h('button', { class: 'btn btn--sm', type: 'button', onclick: () => copyText(cheatSheetText()) },
          icon('copy'), t('cheat.copyAll'))),
      h('p', { class: 'field__hint', style: 'margin:6px 0 12px',
        text: onInsert ? t('cheat.hintInsert') : t('cheat.hint') }),
      ...groups));
}
