// Zugriff auf das lokale Backend. Alle Anfragen gehen an denselben Ursprung.

export class ApiError extends Error {
  constructor(message, { status = 0, kind = 'error', payload = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.kind = kind;
    this.payload = payload;
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
  } catch (error) {
    throw new ApiError('Das lokale Backend antwortet nicht. Läuft die App noch?', { kind: 'offline' });
  }

  if (response.status === 204) return null;

  let data = null;
  const text = await response.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = { detail: text }; }
  }

  if (!response.ok) {
    const detail = data?.detail;
    const message = typeof detail === 'string'
      ? detail
      : detail?.message || `Anfrage fehlgeschlagen (${response.status}).`;
    throw new ApiError(message, {
      status: response.status,
      kind: (typeof detail === 'object' && detail?.kind) || 'error',
      payload: detail,
    });
  }
  return data;
}

const qs = (params) => {
  const search = new URLSearchParams(
    Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  ).toString();
  return search ? `?${search}` : '';
};

export const api = {
  get: (path, params) => request(path + qs(params)),
  post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body ?? {}) }),
  patch: (path, body) => request(path, { method: 'PATCH', body: JSON.stringify(body ?? {}) }),
  del: (path) => request(path, { method: 'DELETE' }),

  // System
  status: () => api.get('/api/system/status'),
  models: () => api.get('/api/system/models'),
  modelInfo: (name) => api.get('/api/system/model-info', { name }),
  startOllama: () => api.post('/api/system/start-ollama'),
  browseFolder: () => api.post('/api/system/browse-folder'),
  reveal: (path) => api.post('/api/system/reveal', { path }),
  vaultStats: () => api.get('/api/system/stats'),

  // Chats
  listChats: (purpose = '', search = '') => api.get('/api/chats', { purpose, search }),
  createChat: (title = 'Neuer Chat', purpose = 'vault') => api.post('/api/chats', { title, purpose }),
  getChat: (id) => api.get(`/api/chats/${id}`),
  renameChat: (id, title) => api.patch(`/api/chats/${id}`, { title }),
  updateChat: (id, patch) => api.patch(`/api/chats/${id}`, patch),
  deleteChat: (id) => api.del(`/api/chats/${id}`),

  // Chat-Ordner
  listChatFolders: (purpose = '') => api.get('/api/chats/folders', { purpose }),
  createChatFolder: (name, purpose = 'vault') => api.post('/api/chats/folders', { name, purpose }),
  updateChatFolder: (id, patch) => api.patch(`/api/chats/folders/${id}`, patch),
  deleteChatFolder: (id) => api.del(`/api/chats/folders/${id}`),

  // Dateien
  tree: (path = '', depth = 2) => api.get('/api/files/tree', { path, depth }),
  listFolder: (path = '') => api.get('/api/files/list', { path }),
  readFile: (path) => api.get('/api/files/read', { path }),
  writeFile: (path, content, overwrite = true) => api.post('/api/files/write', { path, content, overwrite }),
  mkdir: (path) => api.post('/api/files/mkdir', { path }),
  renameEntry: (path, name) => api.post('/api/files/rename', { path, name }),
  moveEntry: (path, target_dir) => api.post('/api/files/move', { path, target_dir }),
  deleteEntry: (path) => api.post('/api/files/delete', { path, confirm: true }),
  uniquePath: (path) => api.get('/api/files/unique-path', { path }),
  recentFiles: (limit = 8, kind = '') => api.get('/api/files/recent', { limit, kind }),
  fileChanges: (since = 0) => api.get('/api/files/changes', { since }),
  rawUrl: (path) => `/api/files/raw?path=${encodeURIComponent(path)}`,

  // Anhänge
  listAttachments: (chatId) => api.get(`/api/attachments/${chatId}`),
  deleteAttachment: (chatId, name) =>
    api.del(`/api/attachments/${chatId}/datei?name=${encodeURIComponent(name)}`),
  clearAttachments: (chatId) => api.del(`/api/attachments/${chatId}`),
  attachmentUrl: (chatId, name) =>
    `/api/attachments/${chatId}/datei?name=${encodeURIComponent(name)}`,

  // Suche
  search: (q, limit = 40) => api.get('/api/search', { q, limit }),

  // Wissensindex und Vorlagen
  knowledgeStatus: () => api.get('/api/knowledge/status'),
  knowledgeSearch: (q, limit = 8) => api.get('/api/knowledge/search', { q, limit }),
  reindexKnowledge: () => api.post('/api/knowledge/reindex'),
  templates: () => api.get('/api/templates'),
  installTemplates: () => api.post('/api/templates/install'),

  // Backups
  backups: () => api.get('/api/backups'),
  createBackup: () => api.post('/api/backups'),
  backupUrl: (name) => `/api/backups/${encodeURIComponent(name)}`,

  // Einstellungen
  settings: () => api.get('/api/settings'),
  updateProfile: (id, patch) => api.patch(`/api/settings/profile/${id}`, { patch }),
  updateUI: (theme) => api.patch('/api/settings/ui', { theme }),
  createProfile: (name) => api.post('/api/settings/profiles', { name }),
  activateProfile: (id) => api.post(`/api/settings/profiles/${id}/activate`),
  deleteProfile: (id) => api.del(`/api/settings/profiles/${id}`),
};

/** Lädt mehrere Dateien auf einmal hoch (multipart, kein JSON-Header). */
export async function uploadFiles(chatId, files) {
  const form = new FormData();
  for (const file of files) form.append('files', file, file.name);

  let response;
  try {
    response = await fetch(`/api/attachments/${chatId}`, { method: 'POST', body: form });
  } catch {
    throw new ApiError('Der Upload ist fehlgeschlagen. Läuft das Backend noch?', { kind: 'offline' });
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new ApiError(typeof detail === 'string' ? detail : detail?.message || 'Upload fehlgeschlagen.',
      { status: response.status, kind: detail?.kind || 'error' });
  }
  return data;
}

/**
 * Liest einen Server-Sent-Events-Stream aus einer POST-Antwort.
 * onEvent bekommt jedes geparste JSON-Objekt; Rückgabe: Abbruchfunktion.
 */
export function streamPost(path, body, { onEvent, onError, onDone } = {}) {
  const controller = new AbortController();

  (async () => {
    let response;
    try {
      response = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body ?? {}),
        signal: controller.signal,
      });
    } catch (error) {
      if (error.name !== 'AbortError') onError?.(new ApiError('Verbindung zum Backend verloren.', { kind: 'offline' }));
      return;
    }

    if (!response.ok) {
      let detail = null;
      try { detail = (await response.json())?.detail; } catch { /* ignorieren */ }
      const message = typeof detail === 'string' ? detail : detail?.message || `Fehler ${response.status}.`;
      onError?.(new ApiError(message, { status: response.status, kind: detail?.kind || 'error' }));
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() ?? '';
        for (const part of parts) {
          const line = part.split('\n').find((l) => l.startsWith('data: '));
          if (!line) continue;
          try { onEvent?.(JSON.parse(line.slice(6))); } catch { /* unvollständige Zeile */ }
        }
      }
    } catch (error) {
      if (error.name !== 'AbortError') onError?.(new ApiError(`Stream abgebrochen: ${error.message}`));
      return;
    }
    onDone?.();
  })();

  return () => controller.abort();
}
