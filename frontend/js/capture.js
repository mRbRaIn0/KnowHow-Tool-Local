// Schnelles Erfassen für die Tabs Notizen, Bilder und Dateien:
// Ablegen ohne Rückfrage, gleiche Namen nummeriert der Server.

import { api, uploadToVault } from './api.js';
import { setDraft } from './chatstream.js';
import { t } from './i18n.js';
import { h, icon, toast } from './util.js';
import { navigate, refreshFileIndex } from './store.js';

/** Ablagefläche für Drag-and-drop, Einfügen (Strg+V) und Dateiauswahl. */
export function dropZone({ label, accept = '', folder = () => null, onSaved = () => {} }) {
  const picker = h('input', { type: 'file', multiple: true, accept, hidden: true });
  const zone = h('div', { class: 'dropzone', tabindex: '0', role: 'button',
    'aria-label': t('capture.zoneLabel', { label }) },
    icon('clip'), h('span', { text: label }),
    h('small', { text: t('capture.zoneHint') }), picker);

  const save = async (files) => {
    if (!files.length) return;
    zone.classList.add('is-busy');
    try {
      const result = await uploadToVault(files, folder());
      for (const problem of result.fehler || []) toast(`${problem.name}: ${problem.grund}`, 'bad');
      const saved = result.gespeichert || [];
      if (saved.length) {
        toast(saved.length === 1 ? t('chat.savedInVault', { path: saved[0].path }) : t('chat.filesSavedInVault', { n: saved.length }), 'ok');
        await refreshFileIndex();
        onSaved(saved);
      }
    } catch (error) {
      toast(error.message, 'bad');
    } finally {
      zone.classList.remove('is-busy');
    }
  };

  zone.addEventListener('click', () => picker.click());
  zone.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); picker.click(); }
  });
  picker.addEventListener('change', () => { save([...picker.files]); picker.value = ''; });
  zone.addEventListener('dragover', (event) => {
    if (![...(event.dataTransfer?.types || [])].includes('Files')) return;
    event.preventDefault();
    zone.classList.add('is-drop');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('is-drop'));
  zone.addEventListener('drop', (event) => {
    zone.classList.remove('is-drop');
    const files = [...(event.dataTransfer?.files || [])];
    if (!files.length) return;
    event.preventDefault();
    save(files);
  });
  zone.pasteHandler = (event) => {
    if (event.target.closest?.('input, textarea')) return;
    const files = [...(event.clipboardData?.files || [])];
    if (files.length) { event.preventDefault(); save(files); }
  };
  return zone;
}

/** Öffnet einen neuen Arbeitschat mit vorbereitetem Auftrag (Erfassen → KI bearbeiten). */
export function askAI(text) {
  navigate(`/chat?draft=${encodeURIComponent(text)}`);
}

/** Neuer Arbeitschat mit einer Vault-Datei als Anhang (keine zweite Kopie im Vault). */
export async function askAIWithFile(path, text) {
  try {
    const created = await api.createChat(t('mode.vault.newTitle'), 'vault');
    await api.post(`/api/attachments/${created.id}/from-vault`, { path });
    setDraft(created.id, text);
    navigate(`/chat/${created.id}`);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

export function wikiTarget(path) {
  return path.toLowerCase().endsWith('.md') ? path.slice(0, -3) : path;
}
