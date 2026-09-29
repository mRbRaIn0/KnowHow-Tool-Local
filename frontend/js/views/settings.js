// Einstellungen: Ollama, Daten, KI, Datenschutz, Oberfläche, Profile, Sprache.

import { api } from '../api.js';
import { LANGUAGES, getLanguage, t } from '../i18n.js';
import { confirmDialog, fill, fmtBytes, h, icon, kv, promptDialog, toast } from '../util.js';
import {
  applyTheme, navigate, profileTone, refreshFileIndex, refreshStatus, state,
} from '../store.js';
import { pullModel } from './dashboard.js';

let settings = null;
let models = [];

export async function mount({ el }) {
  const view = h('div', { class: 'view' });
  el.main.append(view);
  view.append(h('p', { class: 'field__hint', text: t('common.loading') }));

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
      h('span', { class: 'label', text: t('nav.settings') }),
      h('h1', { text: t('settings.title') }),
      h('p', { text: t('settings.lead', { profile: profile.name }) })),
    profilesCard(view, contextHost),
    ollamaCard(profile, view),
    dataCard(profile, view),
    h('details', { class: 'settings-advanced' },
      h('summary', { text: t('nav.advanced') }),
      aiCard(profile),
      privacyCard(profile),
      appearanceCard()),
    languageCard(),
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
        h('span', { class: 'list__sub', text: profile.vault.path || t('settings.noVaultSet') })),
      active
        ? h('span', { class: 'chip chip--accent', text: t('settings.active') })
        : h('button', { class: 'btn btn--sm', onclick: () => activate(profile.id) }, t('settings.switch')),
      !active && settings.profiles.length > 1
        ? h('button', { class: 'icon-btn', title: t('settings.deleteProfile'), onclick: () => removeProfile(profile, view, contextHost) }, icon('trash'))
        : null);
  });

  return h('div', { class: 'card', style: 'margin-bottom:14px' },
    h('div', { class: 'card__title' },
      h('span', { class: 'label', text: t('settings.profiles') }),
      h('button', { class: 'btn btn--sm', onclick: () => addProfile(view, contextHost) }, icon('plus'), t('settings.addProfile'))),
    h('p', { class: 'field__hint', style: 'margin:0 0 10px', text: t('settings.profilesHint') }),
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
    title: t('settings.newProfile'),
    description: t('settings.newProfileHint'),
    label: t('folder.nameLabel'), value: '', confirmLabel: t('common.create'),
  });
  if (!name) return;
  try {
    await api.createProfile(name);
    settings = await api.settings();
    render(view, contextHost);
    toast(t('settings.profileCreated', { name }), 'ok');
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function removeProfile(profile, view, contextHost) {
  const ok = await confirmDialog({
    title: t('settings.deleteProfile'),
    message: t('settings.deleteProfileText', { name: profile.name }),
    confirmLabel: t('common.delete'), danger: true,
  });
  if (!ok) return;
  try {
    await api.deleteProfile(profile.id);
    settings = await api.settings();
    render(view, contextHost);
    toast(t('settings.profileDeleted'), 'ok');
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
    field(t('settings.chatModel'), t('settings.chatModelHint'),
      h('div', { class: 'row' }, chatSelect,
        missing
          ? h('button', { class: 'btn btn--sm btn--primary', onclick: () => pullModel(profile.ollama.chat_model, view) },
            t('common.download'))
          : null)),
    h('details', { class: 'settings-advanced' },
      h('summary', { text: t('settings.modelOptions') }),
      field(t('settings.server'), t('settings.serverHint'),
        h('input', {
          class: 'input input--mono', value: profile.ollama.base_url,
          onchange: (event) => patch({ ollama: { base_url: event.target.value.trim() } }),
        })),
      field(t('settings.keepAlive'), t('settings.keepAliveHint'),
        h('input', { class: 'input input--mono', value: profile.ollama.keep_alive || '10m',
          placeholder: '10m', pattern: '0|[1-9][0-9]*[smh]',
          onchange: (event) => {
            if (event.target.reportValidity()) patch({ ollama: { keep_alive: event.target.value } });
          } })),
      field(t('settings.embedModel'), t('settings.embedModelHint'),
        h('div', { class: 'row' }, embedSelect,
          h('button', {
            class: 'btn btn--sm',
            onclick: () => pullModel(profile.ollama.embed_model || 'nomic-embed-text', view),
          }, t('common.download')))),
      models.length
        ? h('p', { class: 'field__hint', text: t('settings.modelsInstalled', { n: models.length }) })
        : h('p', { class: 'field__hint', text: t('settings.noModels') }),
      h('p', { class: 'field__hint', style: 'margin-top:10px', text: t('settings.modelTip') })));
}

function modelSelect(value, onChange, allowEmpty = false) {
  const select = h('select', { class: 'select', onchange: (event) => onChange(event.target.value) });
  if (allowEmpty) select.append(h('option', { value: '', text: t('settings.none') }));
  const names = models.map((model) => model.name);
  if (value && !names.includes(value)) {
    select.append(h('option', { value, text: `${value} (${t('settings.notInstalled')})` }));
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
    placeholder: t('settings.vaultPlaceholder'),
    onchange: (event) => patch({ vault: { path: event.target.value.trim() } }, true),
  });

  return h('div', { class: 'card', style: 'margin-bottom:14px' },
    h('div', { class: 'card__title' }, h('span', { class: 'label', text: t('settings.data') })),
    field(t('settings.vaultFolder'), t('settings.vaultFolderHint'),
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
        }, icon('folder-open'), t('settings.choose')))),
    h('details', { class: 'settings-advanced' },
      h('summary', { text: t('settings.vaultOptions') }),
      field(t('settings.guide'), t('settings.guideHint'),
        h('input', {
          class: 'input input--mono', value: '00 Inhalt.md', disabled: true,
        })),
      field(t('settings.attachments'), t('settings.attachmentsHint'),
        h('input', {
          class: 'input input--mono', value: profile.vault.attachments_dir,
          onchange: (event) => patch({ vault: { attachments_dir: event.target.value.trim() } }),
        })),
      field(t('settings.templates'), t('settings.templatesHint'),
        h('input', {
          class: 'input input--mono', value: profile.vault.templates_dir,
          onchange: (event) => patch({ vault: { templates_dir: event.target.value.trim() } }),
        })),
      field(t('settings.backup'), t('settings.backupHint'),
        backupControl())));
}

function backupControl() {
  const info = h('span', { class: 'field__hint' });
  const button = h('button', {
    class: 'btn',
    onclick: async () => {
      button.disabled = true;
      button.textContent = t('settings.backupRunning');
      try {
        const result = await api.createBackup();
        info.replaceChildren(h('a', {
          href: api.backupUrl(result.name), text: `${result.name} · ${fmtBytes(result.size)}`,
        }));
        toast(t('settings.backupDone'), 'ok');
      } catch (error) {
        toast(error.message, 'bad');
      } finally {
        button.disabled = false;
        button.replaceChildren(icon('save'), ` ${t('settings.backupCreate')}`);
      }
    },
  }, icon('save'), ` ${t('settings.backupCreate')}`);
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
    h('div', { class: 'card__title' }, h('span', { class: 'label', text: t('settings.ai') })),
    field(t('settings.temperature'), t('settings.temperatureHint'),
      h('div', { class: 'row' }, temperature, temperatureValue)),
    field(t('settings.context'), t('settings.contextHint'),
      h('input', {
        class: 'input input--mono', type: 'number', min: '1024', max: '262144', step: '1024',
        value: String(profile.ai.num_ctx),
        onchange: (event) => patch({ ai: { num_ctx: Number(event.target.value) } }),
      })),
    field(t('settings.topK'), t('settings.topKHint'),
      h('input', {
        class: 'input input--mono', type: 'number', min: '1', max: '20',
        value: String(profile.ai.rag_top_k),
        onchange: (event) => patch({ ai: { rag_top_k: Number(event.target.value) } }),
      })),
    toggle(t('settings.previewWrites'), t('settings.previewWritesHint'),
      profile.ai.preview_writes, (checked) => patch({ ai: { preview_writes: checked } })),
    toggle(t('settings.sourceNotes'), t('settings.sourceNotesHint'),
      profile.ai.source_notes, (checked) => patch({ ai: { source_notes: checked } })),
    toggle(t('settings.separateVision'), t('settings.separateVisionHint'),
      profile.ai.separate_vision, (checked) => patch({ ai: { separate_vision: checked } })),
    field(t('settings.visionModel'), t('settings.visionModelHint'),
      h('select', { class: 'input', value: profile.ollama.vision_model, 'aria-label': t('settings.visionModel'),
        onchange: (event) => patch({ ollama: { vision_model: event.target.value } }) },
        ...[...new Set([profile.ollama.vision_model, ...models.filter(m => !/embed/i.test(m.name)).map(m => m.name)])].filter(Boolean).map(name =>
          h('option', { value: name, selected: name === profile.ollama.vision_model,
            text: name + (models.some(m => m.name === name) ? '' : ` (${t('settings.notInstalled')})`) })))),
    field(t('settings.systemPrompt'), t('settings.systemPromptHint'),
      h('textarea', {
        class: 'textarea', rows: 4,
        onchange: (event) => patch({ ai: { system_prompt: event.target.value } }),
      }, profile.ai.system_prompt)));
}

/* ------------------------------------------------------ Datenschutz */

function privacyCard(profile) {
  return h('div', { class: 'card', style: 'margin-bottom:14px' },
    h('div', { class: 'card__title' }, h('span', { class: 'label', text: t('dash.privacy') })),
    toggle(t('settings.offlineMode'), t('settings.offlineModeHint'),
      profile.privacy.offline_mode, (checked) => patch({ privacy: { offline_mode: checked } })),
    toggle(t('settings.blockExternal'), t('settings.blockExternalHint'),
      profile.privacy.block_external_urls, (checked) => patch({ privacy: { block_external_urls: checked } })));
}

/* ------------------------------------------------------- Oberfläche */

function appearanceCard() {
  const current = settings.ui.theme;
  const options = [['light', t('settings.themeLight')], ['dark', t('settings.themeDark')], ['system', t('settings.themeSystem')]];
  const row = h('div', { class: 'row' });
  for (const [value, label] of options) {
    row.append(h('button', {
      class: `btn btn--sm ${current === value ? 'btn--primary' : ''}`,
      onclick: async () => {
        applyTheme(value);
        settings.ui.theme = value;
        try { await api.updateUI({ theme: value }); } catch (error) { toast(error.message, 'bad'); }
        for (const [index, button] of [...row.children].entries()) {
          button.className = `btn btn--sm ${options[index][0] === value ? 'btn--primary' : ''}`;
        }
      },
    }, label));
  }
  return h('div', { class: 'card' },
    h('div', { class: 'card__title' }, h('span', { class: 'label', text: t('settings.appearance') })),
    field(t('settings.design'), t('settings.designHint'), row));
}

/* --------------------------------------------------------- Sprache */

/** Die Sprache gilt für die gesamte Oberfläche; nach dem Speichern wird sie komplett neu geladen. */
function languageCard() {
  const select = h('select', { class: 'select', 'aria-label': t('settings.language') },
    ...LANGUAGES.map(([code, name]) => h('option', { value: code, text: name })));
  select.value = getLanguage();
  select.addEventListener('change', async () => {
    select.disabled = true;
    try {
      await api.updateUI({ language: select.value });
      location.reload();
    } catch (error) {
      select.value = getLanguage();
      select.disabled = false;
      toast(error.message, 'bad');
    }
  });
  return h('div', { class: 'card', style: 'margin-top:14px' },
    h('div', { class: 'card__title' }, h('span', { class: 'label', text: t('settings.language') })),
    h('div', { class: 'field' }, select, h('span', { class: 'field__hint', text: t('settings.languageHint') })));
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
    toast(t('common.saved'), 'ok');
  } catch (error) {
    toast(error.message, 'bad');
  }
}

function renderContext(host) {
  const status = state.status;
  fill(host,
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: t('settings.whereIsWhat') }),
      kv([
        [t('settings.ctxConfig'), 'data/config.json'],
        [t('settings.ctxDatabase'), `data/profiles/${settings.active_profile}/app.db`],
        [t('settings.ctxLog'), 'data/logs/app.log'],
        ['Vault', settings.profile.vault.path || '–'],
      ])),
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: t('settings.update') }),
      h('p', { class: 'field__hint', style: 'margin:0', text: t('settings.updateHint') })),
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: t('settings.separation') }),
      h('p', { class: 'field__hint', style: 'margin:0', text: t('settings.separationHint') })),
    status?.ollama?.online
      ? null
      : h('div', { class: 'ctx-block' },
        h('span', { class: 'label', text: t('toast.info') }),
        h('p', { class: 'field__hint', style: 'margin:0', text: t('settings.ollamaSilent') })),
  );
}
