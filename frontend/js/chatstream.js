// Laufende Antworten und unfertige Entwürfe.
//
// Beides liegt bewusst außerhalb der Chat-Ansicht: Wer den Chat verlässt,
// soll die Antwort nicht abbrechen und seinen angefangenen Text nicht
// verlieren. Die Ansicht liest hier nur den aktuellen Stand ab.

import { api, streamPost } from './api.js';
import { emit } from './store.js';

const runs = new Map();    // chatId -> laufende Antwort
const drafts = new Map();  // chatId -> noch nicht abgeschickter Text

/* --------------------------------------------------------- Entwürfe */

export function getDraft(chatId) {
  return drafts.get(chatId) || '';
}

export function setDraft(chatId, text) {
  if (text && text.trim()) drafts.set(chatId, text);
  else drafts.delete(chatId);
}

export function clearDraft(chatId) {
  drafts.delete(chatId);
}

/* ---------------------------------------------------- Laufende Antwort */

export function getRun(chatId) {
  return runs.get(chatId) || null;
}

export function isRunning(chatId) {
  return runs.has(chatId);
}

export function runningChatIds() {
  return [...runs.keys()];
}

/**
 * Schickt eine Nachricht ab und streamt die Antwort.
 * Der Stream läuft weiter, auch wenn die Ansicht gewechselt wird.
 */
export function send(chatId, content, selection = {}) {
  if (runs.has(chatId)) return runs.get(chatId);

  const run = {
    chatId,
    content: '',
    thinking: '',
    messageId: null,
    model: selection.model || '',
    thinkingEnabled: selection.thinking,
    userMessage: null,
    steps: [],
    changedFiles: [],
    progress: null,
    analyses: {},
    error: null,
    abort: null,
  };
  runs.set(chatId, run);
  emit('chat:running', { running: true, chatId });

  run.abort = streamPost(`/api/chats/${chatId}/message`, { content, ...selection }, {
    onEvent: (event) => {
      if (event.type === 'user_message') run.userMessage = event.message;
      else if (event.type === 'start') { run.messageId = event.message_id; run.model = event.model; run.thinkingEnabled = event.thinking; run.execution = event.execution; }
      else if (event.type === 'thinking') run.thinking += event.delta;
      else if (event.type === 'content') run.content += event.delta;
      else if (event.type === 'tool_result') run.steps.push(event);
      else if (event.type === 'write_preview') run.preview = event.preview;
      else if (event.type === 'attachment_progress') {
        run.progress = event;
        if (event.text || event.error) run.analyses[event.name] = event;
      }
      else if (event.type === 'attachments_ready') run.progress = null;
      else if (event.type === 'done') {
        run.content = event.content || run.content;
        run.changedFiles = event.changed_files || [];
      }
      else if (event.type === 'error') run.error = event.message;

      emit('chat:event', { chatId, event, run });
      if (event.type === 'done' || event.type === 'error') finish(chatId);
    },
    onError: (error) => {
      if (run.stopping) return;
      run.error = error.message;
      emit('chat:event', { chatId, event: { type: 'error', message: error.message, kind: error.kind }, run });
      finish(chatId);
    },
    onDone: () => {
      emit('vault:action-finished', { chatId });
      if (runs.get(chatId) === run && !run.stopping) {
        emit('chat:event', { chatId, run, event: { type: 'error', message: 'Die Verbindung endete ohne Abschluss. Gespeicherte Arbeitsnotizen bleiben im Chat verfügbar.' } });
        finish(chatId);
      }
    },
  });

  return run;
}

/** Antwort abbrechen. Der bereits erzeugte Text bleibt gespeichert. */
export async function stop(chatId) {
  const run = runs.get(chatId);
  if (!run || run.stopping) return false;
  run.stopping = true;
  emit('chat:event', { chatId, event: { type: 'stopping' }, run });
  try {
    const result = await api.post(`/api/chats/${chatId}/stop`, {});
    if (!result.stopped) throw new Error('Der Server hat den Stopp noch nicht bestätigt.');
    run.abort?.();
    run.content += '\n\nAntwort gestoppt. Gespeicherte Arbeitsnotizen bleiben erhalten. Die Hintergrundindizierung ist bis zum nächsten App-Start pausiert; manuelles Neuindizieren bleibt möglich.';
    emit('chat:event', { chatId, event: { type: 'stopped' }, run });
    finish(chatId);
    return true;
  } catch (error) {
    run.stopping = false;
    emit('chat:event', { chatId, event: { type: 'stop_failed', message: error.message }, run });
    return false;
  }
}

function finish(chatId) {
  if (!runs.has(chatId)) return;
  runs.delete(chatId);
  emit('chat:running', { running: runs.size > 0, chatId });
  emit('chat:finished', { chatId });
}
