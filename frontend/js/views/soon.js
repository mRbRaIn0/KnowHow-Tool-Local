// Platzhalter für die Bereiche, die in späteren Phasen folgen.

import { h, icon } from '../util.js';
import { navigate } from '../store.js';

const PLAN = {
  knowledge: {
    phase: 3,
    title: 'Wissen',
    lead: 'Fragen an dein gesamtes Wissen stellen — mit Quellenangabe.',
    points: [
      'Text aus Markdown, PDF und DOCX extrahieren',
      'Lokale Embeddings über Ollama, keine Cloud',
      'Hybride Suche: Stichwort und Bedeutung kombiniert',
      'Antworten mit Verweis auf Datei, Seite und Chat',
    ],
  },
  images: {
    phase: 4,
    title: 'Bilder',
    lead: 'Screenshots, Fotos und iPhone-Scans lokal auswerten.',
    points: [
      'Bild per Drag & Drop oder aus dem Vault auswählen',
      'Analyse durch qwen3.5:9b direkt über Ollama',
      'Tabellen und Fehlermeldungen aus Bildern auslesen',
      'Ergebnis als neue Notiz oder Ergänzung speichern',
    ],
  },
  notes: {
    phase: 5,
    title: 'Notizen',
    lead: 'Strukturierte Notizen automatisch erzeugen lassen.',
    points: [
      'Aus Chat, Dokument oder Scan eine Notiz erstellen',
      'Vorlage wählen, Inhalt einordnen, im Vault ablegen',
      'Bestehende Dateien nur nach Bestätigung überschreiben',
    ],
  },
  templates: {
    phase: 5,
    title: 'Vorlagen',
    lead: 'Deine Notiztypen als normale Markdown-Dateien.',
    points: [
      'Standard und Vokabeln von Anfang an dabei',
      'Eigene Vorlagen im Ordner 00 Templates ergänzen',
      'Weitere Typen: IT-Wissen, Ticket, Coding, Projekt, Meeting, Lernzettel',
    ],
  },
};

export async function mount({ route, el }) {
  const plan = PLAN[route.view] || PLAN.knowledge;
  el.main.append(h('div', { class: 'view' },
    h('div', { class: 'page-head' },
      h('span', { class: 'label', text: `Phase ${plan.phase}` }),
      h('h1', { text: plan.title }),
      h('p', { text: plan.lead })),
    h('div', { class: 'card' },
      h('div', { class: 'card__title' }, h('span', { class: 'label', text: 'Was hier entsteht' })),
      h('ul', { style: 'margin:0;padding-left:1.1em;color:var(--text-2)' },
        ...plan.points.map((point) => h('li', { text: point }))),
      h('div', { class: 'row', style: 'margin-top:14px' },
        h('button', { class: 'btn btn--sm', onclick: () => navigate('/chat') }, icon('chat'), 'Zum Chat'),
        h('button', { class: 'btn btn--sm', onclick: () => navigate('/files') }, icon('files'), 'Zu den Dateien'))),
  ));

  el.context.append(h('div', { class: 'ctx-block' },
    h('span', { class: 'label', text: 'Stand' }),
    h('p', { class: 'field__hint', style: 'margin:0',
      text: 'Phase 1 ist fertig: Chat, Vault, Editor und Suche laufen. Dieser Bereich folgt in einer der nächsten Phasen.' })));
}
