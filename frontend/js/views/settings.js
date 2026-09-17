// Einstellungen: Ollama, Daten, KI, Datenschutz, Oberfläche, Profile.

import { api } from '../api.js';
import { confirmDialog, fmtBytes, h, icon, promptDialog, toast } from '../util.js';
import {
  applyTheme, navigate, profileTone, refreshFileIndex, refreshStatus, state,
} from '../store.js';
import { pullModel } from './dashboard.js';

let settings = null;
let models = [];

export async function mount({ el }) {
  const view = h('div', { class: 'view' });
  el.main.append(view);
  view.append(h('p', { class: 'field__hint', text: 'wird geladen …' }));

  try {
    settings = await api.settings();
  } catch (error) {
    view.replaceChildren(h('p', { class: 'field__hint', text: error.message }));
    return;
  }
  try {
    models = (await api.models()).models;
  } catch {
    models = [];
  }

  render(view, el.context);
}

function render(view, contextHost) {
  const profile = settings.profile;

  view.replaceChildren(
    h('div', { class: 'page-head' },
      h('span', { class: 'label', text: 'Einstellungen' }),
      h('h1', { text: 'Konfiguration' }),
      h('p', { text: `Alle Angaben gelten für das Profil „${profile.name}" und werden lokal in data/config.json gespeichert.` })),
    profilesCard(view, contextHost),
    ollamaCard(profile, view),
    dataCard(profile, view),
    aiCard(profile),
    privacyCard(profile),
    appearanceCard(),
  );
  renderContext(contextHost);
}

/* -------------------------------------------------------- Profile */

function profilesCard(view, contextHost) {
  const rows = settings.profiles.map((profile) => {
    const active = profile.id === settings.active_profile;
    return h('div', {
      class: 'list__item',
      style: `border-left:3px solid ${profileTone(profile.id, settings.profiles)};border-radius:0 var(--r-sm) var(--r-sm) 0`,
    },
      h('span', { class: 'list__main' },
        h('span', { class: 'list__title', text: profile.name }),
        h('span', { class: 'list__sub', text: profile.vault.path || 'kein Vault gesetzt' })),
      active
        ? h('span', { class: 'chip chip--accent', text: 'aktiv' })
        : h('button', { class: 'btn btn--sm', onclick: () => activate(profile.id) }, 'Wechseln'),
      !active && settings.profiles.length > 1
        ? h('button', { class: 'icon-btn', title: 'Profil löschen', onclick: () => removeProfile(profile, view, contextHost) }, icon('trash'))
        : null);
  });

  return h('div', { class: 'card', style: 'margin-bottom:14px' },
    h('div', { class: 'card__title' },
      h('span', { class: 'label', text: 'Profile' }),
      h('button', { class: 'btn btn--sm', onclick: () => addProfile(view, contextHost) }, icon('plus'), 'Profil anlegen')),
    h('p', { class: 'field__hint', style: 'margin:0 0 10px',
      text: 'Jedes Profil hat einen eigenen Vault und eine eigene Datenbank. Chats und Wissen werden nie zwischen Profilen geteilt.' }),
    h('div', { class: 'list' }, ...rows));
}

async function activate(id) {
  try {
    await api.activateProfile(id);
    await refreshStatus();
    await refreshFileIndex();
    location.hash = '#/dashboard';
    location.reload();
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function addProfile(view, contextHost) {
  const name = await promptDialog({
    title: 'Neues Profil',
    description: 'Zum Beispiel „Unternehmen" mit einem eigenen, getrennten Vault.',
    label: 'Name', value: '', confirmLabel: 'Anlegen',
  });
  if (!name) return;
  try {
    await api.createProfile(name);
    settings = await api.settings();
    render(view, contextHost);
    toast(`Profil „${name}" angelegt.`, 'ok');
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function removeProfile(profile, view, contextHost) {
  const ok = await confirmDialog({
    title: 'Profil löschen',
    message: `Die Konfiguration von „${profile.name}" wird entfernt. Vault-Ordner und lokale Chatdatenbank bleiben unverändert erhalten.`,
    confirmLabel: 'Löschen', danger: true,
  });
  if (!ok) return;
  try {
    await api.deleteProfile(profile.id);
    settings = await api.settings();
    render(view, contextHost);
    toast('Profil gelöscht.', 'ok');
  } catch (error) {
    toast(error.message, 'bad');
  }
}

/* --------------------------------------------------------- Ollama */

function ollamaCard(profile, view) {
  const chatSelect = modelSelect(profile.ollama.chat_model, (value) =>
    patch({ ollama: { chat_model: value } }));
  const embedSelect = modelSelect(profile.ollama.embed_model, (value) =>
    patch({ ollama: { embed_model: value } }), true);

  const missing = profile.ollama.chat_model
    && !models.some((m) => m.name === profile.ollama.chat_model);

  return h('div', { class: 'card', style: 'margin-bottom:14px' },
    h('div', { class: 'card__title' }, h('span', { class: 'label', text: 'Ollama' })),
    field('Server', 'Nur lokale Adressen, solange der Offline-Modus aktiv ist.',
      h('input', {
        class: 'input input--mono', value: profile.ollama.base_url,
        onchange: (event) => patch({ ollama: { base_url: event.target.value.trim() } }),
      })),
    field('Chat-Modell', 'Wird für Chats, Zusammenfassungen und Bildanalyse verwendet.',
      h('div', { class: 'row' }, chatSelect,
        missing
          ? h('button', { class: 'btn btn--sm btn--primary', onclick: () => pullModel(profile.ollama.chat_model, view) },
            'Herunterladen')
          : null)),
    field('Modell im Speicher halten', 'Vermeidet erneutes Laden zwischen Anfragen. Datei-Direktaktionen benötigen kein Modell.',
      h('input', { class: 'input input--mono', value: profile.ollama.keep_alive || '10m',
        placeholder: '10m', pattern: '0|[1-9][0-9]*[smh]',
        onchange: (event) => {
          if (event.target.reportValidity()) patch({ ollama: { keep_alive: event.target.value } });
        } })),
    field('Embedding-Modell', 'Erzeugt die lokalen Vektoren für die semantische Wissenssuche.',
      h('div', { class: 'row' }, embedSelect,
        h('button', {
          class: 'btn btn--sm',
          onclick: () => pullModel(profile.ollama.embed_model || 'nomic-embed-text', view),
        }, 'Herunterladen'))),
    models.length
      ? h('p', { class: 'field__hint', text: `${models.length} Modelle lokal installiert.` })
      : h('p', { class: 'field__hint', text: 'Keine Modelle gefunden — läuft Ollama?' }),
    h('p', { class: 'field__hint', style: 'margin-top:10px',
      text: 'Stand 11.09.2026: Standard ist qwen3.5:9b (neue Profile: Thinking aus für schnellere Antworten) — Allrounder mit Deutsch, Werkzeugen und Bildern, braucht etwa 8 GB. qwen3.5:4b ist schneller, aber schwächer. qwen3-vl:8b eignet sich extra für Fotos und Scans, ersetzt den 9B-Allrounder nicht. nomic-embed-text ist nur die Suche, kein Chat. Chats liegen im Ordner data neben der EXE; bei Updates diesen Ordner behalten.' }));
}

function modelSelect(value, onChange, allowEmpty = false) {
  const select = h('select', { class: 'select', onchange: (event) => onChange(event.target.value) });
  if (allowEmpty) select.append(h('option', { value: '', text: '– keines –' }));
  const names = models.map((model) => model.name);
  if (value && !names.includes(value)) {
    select.append(h('option', { value, text: `${value} (nicht installiert)` }));
  }
  for (const model of models) {
    select.append(h('option', {
      value: model.name,
      text: `${model.name}${model.parameters ? ` · ${model.parameters}` : ''} · ${fmtBytes(model.size)}`,
    }));
  }
  select.value = value || '';
  return select;
}

/* ---------------------------------------------------------- Daten */

function dataCard(profile, view) {
  const pathInput = h('input', {
    class: 'input input--mono', value: profile.vault.path,
        placeholder: 'z. B. C:\\Vault',
    onchange: (event) => patch({ vault: { path: event.target.value.trim() } }, true),
  });

  return h('div', { class: 'card', style: 'margin-bottom:14px' },
    h('div', { class: 'card__title' }, h('span', { class: 'label', text: 'Daten' })),
    field('Vault-Ordner', 'Die App arbeitet ausschließlich in diesem ausdrücklich ausgewählten Ordner und legt dort die Hauptseite „00 Inhalt.md“ an.',
      h('div', { class: 'row' }, pathInput,
        h('button', {
          class: 'btn', onclick: async () => {
            try {
              const picked = await api.browseFolder();
              if (picked.cancelled) return;
              pathInput.value = picked.path;
              await patch({ vault: { path: picked.path } }, true);
            } catch (error) { toast(error.message, 'bad'); }
          },
        }, icon('folder-open'), 'Auswählen'))),
    field('Vault-Hauptseite', 'Steuert Stil, Emoji-Nutzung, Ablage, Links und enthält den automatisch gepflegten Ordner- und Dateiüberblick.',
      h('input', {
        class: 'input input--mono', value: '00 Inhalt.md', disabled: true,
      })),
    field('Anhänge', 'Zielordner für Bilder und Dateien, die die App ablegt.',
      h('input', {
        class: 'input input--mono', value: profile.vault.attachments_dir,
        onchange: (event) => patch({ vault: { attachments_dir: event.target.value.trim() } }),
      })),
    field('Vorlagen', 'Ordner mit deinen Markdown-Vorlagen.',
      h('input', {
        class: 'input input--mono', value: profile.vault.templates_dir,
        onchange: (event) => patch({ vault: { templates_dir: event.target.value.trim() } }),
      })),
    field('Backup', 'Erstellt eine lokale ZIP-Datei mit Vault, Profil und konsistenter Chatdatenbank.',
      backupControl()));
}

function backupControl() {
  const info = h('span', { class: 'field__hint' });
  const button = h('button', {
    class: 'btn',
    onclick: async () => {
      button.disabled = true;
      button.textContent = 'Backup läuft …';
      try {
        const result = await api.createBackup();
        info.replaceChildren(h('a', {
          href: api.backupUrl(result.name), text: `${result.name} · ${fmtBytes(result.size)}`,
        }));
        toast('Backup vollständig erstellt.', 'ok');
      } catch (error) {
        toast(error.message, 'bad');
      } finally {
        button.disabled = false;
        button.replaceChildren(icon('save'), ' Backup erstellen');
      }
    },
  }, icon('save'), ' Backup erstellen');
  return h('div', { class: 'row row--wrap' }, button, info);
}

/* ------------------------------------------------------------- KI */

function aiCard(profile) {
  const temperature = h('input', {
    type: 'range', min: '0', max: '1.5', step: '0.05', value: String(profile.ai.temperature),
    style: 'flex:1',
  });
  const temperatureValue = h('span', { class: 'chip', text: profile.ai.temperature.toFixed(2) });
  temperature.addEventListener('input', () => { temperatureValue.textContent = Number(temperature.value).toFixed(2); });
  temperature.addEventListener('change', () => patch({ ai: { temperature: Number(temperature.value) } }));

  return h('div', { class: 'card', style: 'margin-bottom:14px' },
    h('div', { class: 'card__title' }, h('span', { class: 'label', text: 'KI' })),
    field('Temperatur', 'Niedrig = sachlich und wiederholbar, hoch = kreativer.',
      h('div', { class: 'row' }, temperature, temperatureValue)),
    field('Kontextgröße (Token)', 'Mehr Kontext braucht mehr VRAM. 8192 ist für 12 GB ein guter Start.',
      h('input', {
        class: 'input input--mono', type: 'number', min: '1024', max: '262144', step: '1024',
        value: String(profile.ai.num_ctx),
        onchange: (event) => patch({ ai: { num_ctx: Number(event.target.value) } }),
      })),
    field('Treffer für Wissensfragen', 'Wie viele passende Textabschnitte die lokale RAG-Suche heranzieht.',
      h('input', {
        class: 'input input--mono', type: 'number', min: '1', max: '20',
        value: String(profile.ai.rag_top_k),
        onchange: (event) => patch({ ai: { rag_top_k: Number(event.target.value) } }),
      })),
    toggle('Gedankengang anzeigen', 'Zeigt den Denkprozess des Modells, sofern es ihn unterstützt.',
      profile.ai.thinking, (checked) => patch({ ai: { thinking: checked } })),
    toggle('Schreibvorschau', 'Notizen vor dem Speichern als Alt → Neu prüfen, anpassen oder abbrechen.',
      profile.ai.preview_writes, (checked) => patch({ ai: { preview_writes: checked } })),
    toggle('Bild- und Scanwissen suchbar speichern', 'Erstellt Quellennotizen in 91 Quellenwissen mit Original-Link, OCR und Seitenangaben. „Nur ansehen“ bleibt ohne Vault-Ablage.',
      profile.ai.source_notes, (checked) => patch({ ai: { source_notes: checked } })),
    toggle('Separates Vision-Modell verwenden', 'Nur falls installiert: alle Bild-/Scanseiten nacheinander auswerten, dann zum Chatmodell wechseln. Kein paralleles Laden; spätere Bildwerkzeuge verwenden das Chatmodell.',
      profile.ai.separate_vision, (checked) => patch({ ai: { separate_vision: checked } })),
    field('Optionales Vision-Modell', 'Wird nicht automatisch installiert. Ohne verfügbares Vision-Modell nutzt die App das Chatmodell, sofern dieses Bilder unterstützt.',
      h('select', { class: 'input', value: profile.ollama.vision_model, 'aria-label': 'Optionales Vision-Modell',
        onchange: (event) => patch({ ollama: { vision_model: event.target.value } }) },
        ...[...new Set([profile.ollama.vision_model, ...models.filter(m => !/embed/i.test(m.name)).map(m => m.name)])].filter(Boolean).map(name =>
          h('option', { value: name, selected: name === profile.ollama.vision_model,
            text: name + (models.some(m => m.name === name) ? '' : ' (nicht installiert)') })))),
    field('System-Anweisung', 'Gilt für jeden neuen Chat.',
      h('textarea', {
        class: 'textarea', rows: 4,
        onchange: (event) => patch({ ai: { system_prompt: event.target.value } }),
      }, profile.ai.system_prompt)));
}

/* ------------------------------------------------------ Datenschutz */

function privacyCard(profile) {
  return h('div', { class: 'card', style: 'margin-bottom:14px' },
    h('div', { class: 'card__title' }, h('span', { class: 'label', text: 'Datenschutz' })),
    toggle('Offline-Modus', 'Erlaubt ausschließlich Verbindungen zu 127.0.0.1 und localhost.',
      profile.privacy.offline_mode, (checked) => patch({ privacy: { offline_mode: checked } })),
    toggle('Externe Links blockieren', 'Links auf http(s)-Adressen in Notizen werden nicht anklickbar dargestellt.',
      profile.privacy.block_external_urls, (checked) => patch({ privacy: { block_external_urls: checked } })),
    h('div', { class: 'switch', style: 'opacity:.6;cursor:default' },
      h('span', { class: 'switch__track' }),
      h('span', { class: 'switch__text' },
        h('span', { text: 'Telemetrie' }),
        h('small', { text: 'Dauerhaft aus. Die App sendet keine Nutzungsdaten — es gibt keinen Empfänger.' }))));
}

/* ------------------------------------------------------- Oberfläche */

function appearanceCard() {
  const current = settings.ui.theme;
  const options = [['light', 'Hell'], ['dark', 'Dunkel'], ['system', 'System']];
  const row = h('div', { class: 'row' });
  for (const [value, label] of options) {
    row.append(h('button', {
      class: `btn btn--sm ${current === value ? 'btn--primary' : ''}`,
      onclick: async () => {
        applyTheme(value);
        settings.ui.theme = value;
        try { await api.updateUI(value); } catch (error) { toast(error.message, 'bad'); }
        for (const [index, button] of [...row.children].entries()) {
          button.className = `btn btn--sm ${options[index][0] === value ? 'btn--primary' : ''}`;
        }
      },
    }, label));
  }
  return h('div', { class: 'card' },
    h('div', { class: 'card__title' }, h('span', { class: 'label', text: 'Oberfläche' })),
    field('Design', 'Hell, dunkel oder passend zur Windows-Einstellung.', row));
}

/* --------------------------------------------------------- Helfer */

function field(label, hint, control) {
  return h('div', { class: 'field' },
    h('span', { class: 'label', text: label }),
    control,
    hint ? h('span', { class: 'field__hint', text: hint }) : null);
}

function toggle(label, hint, checked, onChange) {
  const input = h('input', { type: 'checkbox', onchange: (event) => onChange(event.target.checked) });
  input.checked = checked;
  return h('label', { class: 'switch' },
    input,
    h('span', { class: 'switch__track' }),
    h('span', { class: 'switch__text' },
      h('span', { text: label }),
      h('small', { text: hint })));
}

async function patch(body, reloadFiles = false) {
  try {
    settings.profile = await api.updateProfile(settings.active_profile, body);
    await refreshStatus();
    if (reloadFiles) await refreshFileIndex();
    toast('Gespeichert.', 'ok');
  } catch (error) {
    toast(error.message, 'bad');
  }
}

function renderContext(host) {
  const status = state.status;
  host.replaceChildren(
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: 'Wo liegt was' }),
      h('dl', { class: 'ctx-kv' },
        h('dt', { text: 'Konfig' }), h('dd', { text: 'data/config.json' }),
        h('dt', { text: 'Datenbank' }), h('dd', { text: `data/profiles/${settings.active_profile}/app.db` }),
        h('dt', { text: 'Protokoll' }), h('dd', { text: 'data/logs/app.log' }),
        h('dt', { text: 'Vault' }), h('dd', { text: settings.profile.vault.path || '–' }))),
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: 'Update' }),
      h('p', { class: 'field__hint', style: 'margin:0',
        text: 'Neue EXE in denselben Ordner legen und den Ordner data behalten. Chats überleben das, solange data nicht in einen neuen leeren Ordner wandert.' })),
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: 'Trennung' }),
      h('p', { class: 'field__hint', style: 'margin:0',
        text: 'Profile teilen weder Datenbank noch Chats noch Wissensindex. Auf einem Firmenrechner kann ausschließlich das Unternehmensprofil eingerichtet werden.' })),
    status?.ollama?.online
      ? null
      : h('div', { class: 'ctx-block' },
        h('span', { class: 'label', text: 'Hinweis' }),
        h('p', { class: 'field__hint', style: 'margin:0', text: 'Ollama antwortet gerade nicht. Modelllisten bleiben leer, bis der Dienst läuft.' })),
  );
}
