// Separate NAS catalog. Every request captures the originating profile.
import { api } from '../api.js';
import { h as element, toast, openModal, fmtBytes, fmtNumber } from '../util.js';
import { state, navigate } from '../store.js';

let current = null;
const h = (tag, props, ...children) => element(tag, props, ...children.filter(c => c != null));
const labels = {
  pending: 'Zu prüfen', approved: 'Freigegeben', applied: 'Angewendet', rejected: 'Abgelehnt',
  undone: 'Zurückgenommen', queued: 'Wartend', running: 'Läuft', paused: 'Pausiert',
  failed: 'Fehlgeschlagen', done: 'Abgeschlossen', metadata: 'Metadaten', operation: 'Ablage',
  mkdir: 'Ordner anlegen', note: 'Obsidian-Notiz', restore: 'Wiederherstellung',
  reconcile: 'Datei zuordnen', scan: 'Bestand erfassen', analyze: 'KI-Vorschläge',
  hash: 'Duplikate prüfen', index: 'Inhalte indexieren', backup: 'JSON sichern', execute: 'Dateien ablegen',
};
const field = (label, input) => h('label', { class: 'library-field' }, h('span', { text: label }), input);
const input = (value = '', placeholder = '') => h('input', { class: 'input', value, placeholder });
const select = (options, value = '') => {
  const node = h('select', { class: 'input' }, ...options.map(([id, name]) =>
    h('option', { value: id, text: name })));
  node.value = options.some(([id]) => String(id) === String(value)) ? value : (options[0]?.[0] ?? '');
  return node;
};
const tagsOf = value => value.split(',').map(t => t.trim()).filter(Boolean);

export async function mount(context) {
  current = new LibraryView(context);
  await current.init();
}

export function unmount() {
  if (current) {
    current.alive = false;
    clearInterval(current.timer);
    current.dialog?.close();
  }
  current = null;
}

class LibraryView {
  constructor({ route, el }) {
    this.el = el;
    this.route = route;
    this.profile = state.status?.profile?.id;
    this.alive = true;
    this.selected = new Map();
    this.offset = 0;
    this.filters = { q: route.params.q || '' };
    this.tab = route.params.tab || 'catalog';
    this.root = h('div', { class: 'view library-view' });
    el.main.append(this.root);
    el.context.replaceChildren(h('p', { class: 'field__hint', text: 'Datei auswählen, um Vorschau und Tags zu prüfen.' }));
  }

  url(path, params = {}) {
    return '/api/library' + path + '?' + new URLSearchParams({ ...params, profile_id: this.profile });
  }

  async get(path, params = {}) {
    const result = await api.get(this.url(path, params));
    if (!this.alive) throw new Error('Ansicht wurde gewechselt.');
    return result;
  }

  async post(path, body = {}) {
    if (!this.alive) throw new Error('Ansicht wurde gewechselt.');
    const result = await api.post(this.url(path), body);
    if (!this.alive) throw new Error('Ansicht wurde gewechselt.');
    return result;
  }

  button(text, action, primary = false) {
    const button = h('button', { type: 'button', class: 'btn btn--sm' + (primary ? ' btn--primary' : ''), text });
    button.onclick = async () => {
      button.disabled = true;
      try { if (this.alive) await action(); }
      catch (error) { if (this.alive) toast(error.message, 'bad'); }
      finally { button.disabled = false; }
    };
    return button;
  }

  modal(title, body, action, confirm = 'Vorschau erstellen') {
    this.dialog?.close();
    this.dialog = openModal({
      title, body,
      actions: [
        { label: 'Schließen', onClick: close => close() },
        ...(action ? [{ label: confirm, variant: 'primary', onClick: async close => {
          if (!this.alive) return close();
          try { await action(close); }
          catch (error) { toast(error.message, 'bad'); }
        }}] : []),
      ],
    });
    this.dialog.modal.setAttribute('role', 'dialog');
    this.dialog.modal.setAttribute('aria-modal', 'true');
    this.dialog.modal.setAttribute('aria-label', title);
    this.dialog.modal.addEventListener('keydown', event => {
      if (event.key !== 'Tab') return;
      const controls = [...this.dialog.modal.querySelectorAll('button,input,textarea,select,a[href]')]
        .filter(n => !n.disabled && !n.hidden);
      if (!controls.length) return;
      if (event.shiftKey && document.activeElement === controls[0]) {
        event.preventDefault(); controls.at(-1).focus();
      } else if (!event.shiftKey && document.activeElement === controls.at(-1)) {
        event.preventDefault(); controls[0].focus();
      }
    });
  }

  async init() {
    this.root.replaceChildren(h('p', { text: 'Bibliothek wird geladen …', role: 'status' }));
    try {
      this.status = await this.get('/status');
      this.header();
      if (!this.status.enabled) {
        this.root.append(h('div', { class: 'card library-welcome' },
          h('span', { class: 'label', text: 'Deine Dateien. Deine Ordnung.' }),
          h('h2', { text: 'Ein Katalog für PC und NAS' }),
          h('p', { text: 'Erfassen, taggen und wiederfinden. Erst nach deiner Prüfung wird etwas abgelegt. Dein Obsidian-Vault bleibt ein eigener Wissensordner.' }),
          h('p', { class: 'field__hint', text: 'Beim Aktivieren werden noch keine Ordner erfasst oder Dateien verändert.' }),
          this.button('Für dieses Profil aktivieren', async () => {
            await this.post('/enabled', { enabled: true }); await this.init();
          }, true)));
        return;
      }
      this.sources = this.status.sources;
      this.body = h('div');
      this.root.append(this.body);
      await this.renderTab();
      clearInterval(this.timer);
      this.timer = setInterval(() => {
        if (this.alive && this.tab === 'jobs') this.renderJobs().catch(() => {});
      }, 2500);
      if (this.route.params.item && this.tab === 'catalog') await this.detail(this.route.params.item);
    } catch (error) {
      if (this.alive) this.root.replaceChildren(h('p', { text: error.message }),
        this.button('Erneut laden', () => this.init()));
    }
  }

  header() {
    this.root.replaceChildren(h('div', { class: 'page-head' },
      h('span', { class: 'label', text: 'Lokal · geprüft · unabhängig vom Vault' }),
      h('h1', { text: 'NAS-Bibliothek' }),
      h('p', { text: 'Erst verstehen und taggen. Dann bewusst ablegen.' })));
    if (!this.status.enabled) return;
    const tabs = h('div', { class: 'library-tabs', role: 'navigation', 'aria-label': 'Bibliotheksbereiche' });
    for (const [key, label] of [['catalog', 'Bibliothek'], ['reviews', 'Prüfen'],
      ['structure', 'Struktur & Tags'], ['sources', 'Quellen & Sicherung'], ['jobs', 'Aufträge']]) {
      const button = this.button(label, async () => {
        this.tab = key; this.header();
        this.body = h('div'); this.root.append(this.body);
        await this.renderTab();
      }, key === this.tab);
      button.setAttribute('aria-current', key === this.tab ? 'page' : 'false');
      tabs.append(button);
    }
    this.root.append(tabs);
  }

  async renderTab() {
    if (this.tab === 'catalog') await this.catalog();
    if (this.tab === 'reviews') await this.reviews();
    if (this.tab === 'structure') await this.structure();
    if (this.tab === 'sources') await this.sourcePage();
    if (this.tab === 'jobs') await this.renderJobs();
  }

  refs() { return [...this.selected.values()].map(i => ({ id: i.id, revision: i.revision })); }
  requireSelection() {
    if (!this.selected.size) throw new Error('Bitte zuerst Dateien auswählen.');
    if (this.selected.size > 500) throw new Error('Bitte höchstens 500 Dateien je Freigabe auswählen.');
    return this.refs();
  }

  async catalog() {
    this.body.replaceChildren();
    const search = input(this.filters.q || '', 'Name, Tags oder Beschreibung');
    const source = select([['', 'Alle Quellen'], ...this.sources.map(s => [s.id, s.name])], this.filters.source_id);
    const review = select([['', 'Jeder Prüfstatus'], ['unreviewed', 'Ungeprüft'], ['reviewed', 'Geprüft'],
      ['missing', 'Nicht mehr am bisherigen Ort']], this.filters.review);
    const tag = input(this.filters.tag || '', 'Tag');
    const folder = input(this.filters.folder || '', 'Relativer Ordner');
    const ext = input(this.filters.extension || '', 'Dateityp, z. B. .pdf');
    const duplicates = h('input', { type: 'checkbox', checked: this.filters.duplicates === 'true' });
    const form = h('form', { class: 'library-filters' },
      field('Suche', search), field('Quelle', source), field('Status', review),
      field('Tag', tag), field('Ordner', folder), field('Dateityp', ext),
      field('Nur exakte Duplikate', duplicates), h('button', { class: 'btn', type: 'submit', text: 'Filtern' }));
    form.onsubmit = event => {
      event.preventDefault(); this.offset = 0;
      this.filters = { q: search.value, source_id: source.value, review: review.value,
        tag: tag.value, folder: folder.value, extension: ext.value, duplicates: String(duplicates.checked) };
      this.loadItems().catch(e => toast(e.message, 'bad'));
    };
    this.body.append(form);
    const collections = (await this.get('/entries/collection')).items;
    this.body.append(h('div', { class: 'library-actions' },
      ...collections.map(c => this.button(c.name, async () => {
        this.filters = c.data; this.offset = 0; await this.catalog();
      })), this.button('Filter als Sammlung sichern', () => this.saveCollection())));
    this.selectionText = h('span', { class: 'field__hint', role: 'status', text: 'Keine Auswahl' });
    this.body.append(h('div', { class: 'library-actions library-selection' },
      this.selectionText,
      this.button('Tags bearbeiten', () => this.editMetadata()),
      this.button('KI-Vorschläge', () => this.startSelected('analyze')),
      this.button('Duplikate prüfen', () => this.startSelected('hash')),
      this.button('Ablage planen', () => this.operationDialog(), true),
      this.button('Inhaltssuche', () => this.indexDialog()),
      this.button('Obsidian-Notiz', () => this.noteDialog()),
      this.button('Inhalte durchsuchen', () => this.contentSearch()),
      this.button('Auswahl leeren', () => { this.selected.clear(); return this.loadItems(); })));
    this.list = h('div', { 'aria-live': 'polite' });
    this.body.append(this.list);
    if (!this.sources.length) {
      this.list.append(h('div', { class: 'empty' }, h('h3', { text: 'Noch keine Quelle' }),
        h('p', { text: 'Füge einen PC-Ordner oder eine NAS-Freigabe hinzu. Beim Erfassen bleibt alles an seinem Platz.' }),
        this.button('Quelle hinzufügen', () => this.sourceDialog(), true)));
    } else await this.loadItems();
  }

  async loadItems() {
    const data = await this.get('/items', { ...this.filters, offset: this.offset, limit: 100 });
    this.selectionText.textContent = this.selected.size + ' ausgewählt';
    const all = h('input', { type: 'checkbox', 'aria-label': 'Diese Seite auswählen' });
    all.onchange = () => {
      data.items.forEach(i => all.checked ? this.selected.set(i.id, i) : this.selected.delete(i.id));
      this.loadItems().catch(e => toast(e.message, 'bad'));
    };
    const table = h('table', { class: 'library-table' },
      h('thead', {}, h('tr', {}, h('th', {}, all), ...['Datei', 'Tags', 'Größe', 'Status'].map(t => h('th', { text: t })))),
      h('tbody', {}, ...data.items.map(item => {
        const checked = h('input', { type: 'checkbox', checked: this.selected.has(item.id),
          'aria-label': item.name + ' auswählen' });
        checked.onchange = () => {
          checked.checked ? this.selected.set(item.id, item) : this.selected.delete(item.id);
          this.selectionText.textContent = this.selected.size + ' ausgewählt';
        };
        return h('tr', {}, h('td', {}, checked),
          h('td', {}, this.button(item.name, () => this.detail(item.id)),
            h('div', { class: 'library-path', text: item.source_name + ' / ' + item.path })),
          h('td', {}, ...item.tags.slice(0, 5).map(t => h('span', { class: 'chip', text: t }))),
          h('td', { text: fmtBytes(item.size) }),
          h('td', {}, h('span', { class: 'chip', text: item.missing ? 'Fehlt' : item.reviewed ? 'Geprüft' : 'Ungeprüft' })));
      })));
    this.list.replaceChildren(h('div', { class: 'library-actions' },
      h('strong', { text: fmtNumber(data.total) + ' Dateien' }),
      this.button('Zurück', async () => { this.offset = Math.max(0, this.offset - 100); await this.loadItems(); }),
      h('span', { text: 'Seite ' + (Math.floor(this.offset / 100) + 1) }),
      this.button('Weiter', async () => {
        if (this.offset + 100 < data.total) this.offset += 100; await this.loadItems();
      }), this.button('Aktualisieren', () => this.loadItems())),
      h('div', { class: 'library-table-wrap' }, table),
      ...(!data.items.length ? [h('p', { class: 'field__hint', text: 'Keine Treffer. Nach dem Hinzufügen einer Quelle zuerst „Erfassen“ starten.' })] : []));
  }

  async detail(id) {
    const item = await this.get('/items/' + id);
    const host = this.el.context;
    host.replaceChildren(h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: 'Datei prüfen' }),
      h('h2', { text: item.name }), h('p', { class: 'library-path', text: item.source_name + ' / ' + item.path }),
      h('p', { class: 'field__hint', text: 'ID: ' + item.id }),
      h('p', { text: item.description || 'Noch keine bestätigte Beschreibung.' }),
      h('div', { class: 'library-actions' }, ...item.tags.map(t => h('span', { class: 'chip', text: t }))),
      this.button('Tags bearbeiten', () => this.editMetadata([item])),
      this.button('Im Explorer zeigen', () => this.post('/items/' + id + '/reveal')),
      item.missing ? this.button('Verschobene Datei zuordnen', () => this.reconcileDialog(item)) : null));
    for (const proposal of item.proposals) {
      host.append(this.button('Vorschlag prüfen', () => this.showProposal(proposal.id)));
    }
    for (const rule of item.rules) {
      host.append(this.button('Ablageregel prüfen: ' + rule.name, () => this.operationDialog([item], rule.data.target_id)));
    }
    if (!item.missing) {
      try {
        const preview = await this.get('/items/' + id + '/preview');
        if (preview.kind === 'text') host.append(h('pre', { class: 'library-preview', text: preview.text }));
        if (preview.kind === 'image') host.append(h('img', {
          class: 'library-image', src: this.url('/items/' + id + '/raw'), alt: item.name }));
        if (preview.kind === 'pdf') host.append(h('iframe', {
          class: 'library-pdf', sandbox: '', src: this.url('/items/' + id + '/raw'), title: item.name }));
        if (preview.kind === 'unsupported') host.append(h('p', {
          class: 'field__hint', text: 'Für diesen Dateityp gibt es keine Inhaltsvorschau. Die Datei wird nicht ausgeführt.' }));
      } catch (error) { host.append(h('p', { text: error.message })); }
    }
  }

  async editMetadata(explicit = null, initial = null) {
    const refs = explicit ? explicit.map(i => ({ id: i.id, revision: i.revision })) : this.requireSelection();
    const first = initial || (explicit?.length === 1 ? explicit[0] : this.selected.size === 1 ? [...this.selected.values()][0] : {});
    const tags = input((first.tags || []).join(', '));
    const description = h('textarea', { class: 'input', rows: 6 }, first.description || '');
    const groups = (await this.get('/entries/group')).items;
    const groupButtons = h('div', { class: 'library-actions' }, ...groups.map(group =>
      this.button('Tags aus ' + group.name, () => {
        tags.value = [...new Set([...tagsOf(tags.value), ...group.data.tags])].join(', ');
      })));
    this.modal('Metadaten für ' + refs.length + ' Datei(en)',
      h('div', {}, field('Tags, durch Kommas getrennt', tags), groupButtons, field('Beschreibung', description),
        h('p', { class: 'field__hint', text: 'Die Vorschau zeigt die vollständigen neuen Metadaten. Bei mehreren Dateien ersetzt diese Auswahl deren bisherige Tags und Beschreibung.' })),
      async close => {
        const p = await this.post('/metadata/preview', { items: refs,
          metadata: { tags: tagsOf(tags.value), description: description.value } });
        close(); await this.showProposal(p.id);
      });
  }

  async showProposal(id, offset = 0) {
    const p = await this.get('/proposals/' + id, { offset });
    const body = h('div', { class: 'library-review' });
    body.append(h('p', { text: (p.total || 0) + ' Datei(en) · ' + (labels[p.status] || p.status) }),
      h('p', { class: 'field__hint', text: 'Freigabe gilt nur für diesen gespeicherten Stand. Geänderte Dateien oder belegte Ziele stoppen die Aktion.' }));
    if (p.data.ai) {
      body.append(h('p', { text: 'KI-Begründung: ' + p.data.ai.evidence }));
      if (p.data.ai.truncated) body.append(h('p', { text: 'Hinweis: Die KI erhielt einen gekürzten Textauszug.' }));
      if (p.data.ai.target_id) body.append(h('p', { text: 'Vorgeschlagenes Ablageziel: ' +
        ((await this.get('/entries/target')).items.find(t => t.id === p.data.ai.target_id)?.name || 'nicht mehr verfügbar') }));
      if (p.data.ai.suggested_name) body.append(h('p', { text: 'Namensvorschlag: ' + p.data.ai.suggested_name }));
    }
    for (const change of p.data.items || []) {
      body.append(h('div', { class: 'library-review-row' },
        h('strong', { text: change.path }),
        change.source_id ? h('p', { class: 'library-path', text: 'Quelle: ' +
          (this.sources.find(s => s.id === change.source_id)?.root || change.source_id) + ' / ' + change.path }) : null,
        change.before ? h('p', { text: 'Bisher: ' + change.before.tags.join(', ') + ' · ' + change.before.description }) : null,
        change.after ? h('p', { text: 'Vorschlag: ' + change.after.tags.join(', ') + ' · ' + change.after.description }) : null,
        change.destination ? h('p', { text: (p.data.action === 'copy' ? 'Kopieren → ' : 'Verschieben → ') +
          (this.sources.find(s => s.id === change.target_source_id)?.root || '') + ' / ' + change.destination }) : null));
    }
    if (p.kind === 'mkdir') body.append(h('p', { text: 'Neuer Zielordner: ' + p.data.path }));
    if (p.kind === 'reconcile') body.append(h('p', { text: 'Bisheriger Ort: ' + p.data.old_path }),
      h('p', { text: p.data.hash_verified ? 'Dateiinhalt stimmt mit gespeichertem SHA-256 überein.' : p.data.warning }));
    if (p.kind === 'note') body.append(h('p', { text: 'Vault-Notiz: ' + p.data.path }),
      h('pre', { class: 'library-preview', text: p.data.content }));
    if (p.kind === 'restore') body.append(h('p', { text: (p.data.entries || []).length + ' Struktureinträge; ' +
      (p.data.unresolved || []).length + ' nicht zuordenbare Einträge bleiben unverändert.' }),
      h('pre', { class: 'library-preview', text: (p.data.unresolved || []).slice(0, 100).join('\n') }));
    if (p.total > 100) body.append(h('div', { class: 'library-actions' },
      this.button('Vorherige 100', () => this.showProposal(id, Math.max(0, offset - 100))),
      this.button('Nächste 100', () => this.showProposal(id, offset + 100 < p.total ? offset + 100 : offset))));
    if (p.status === 'pending') {
      body.append(this.button('Vorschlag ablehnen', async () => {
        await this.post('/proposals/' + id + '/reject', { revision: p.revision, confirm: true });
        this.dialog.close(); await this.renderTab();
      }));
      if (p.kind === 'metadata' && p.total === 1) body.append(this.button('Vorschlag bearbeiten', () =>
        this.editMetadata(p.data.items, p.data.items[0].after)));
    }
    if (p.status === 'applied' && ['metadata', 'operation'].includes(p.kind)) {
      if (p.data.ai?.target_id && p.total === 1) body.append(this.button('Vorgeschlagene Ablage planen', async () => {
        const item = await this.get('/items/' + p.data.items[0].id);
        await this.operationDialog([item], p.data.ai.target_id, p.data.ai.suggested_name || '');
      }));
      if (p.kind === 'operation' && p.total === 1 && p.data.items[0].target_id) body.append(
        this.button('Zuordnung als Vorschlagsregel speichern', async () => {
          const item = await this.get('/items/' + p.data.items[0].id);
          await this.simpleEntry('rule', { name: '', data: { tags: item.tags, target_id: p.data.items[0].target_id } });
        }));
      if (p.kind !== 'operation' || p.data.action !== 'copy') body.append(this.button('Rückgängig machen', async () => {
        const value = await this.post('/proposals/' + id + '/undo', { revision: p.revision, confirm: true });
        this.dialog.close();
        if (value.id) await this.showProposal(value.id); else await this.renderTab();
      }));
    }
    this.modal((labels[p.kind] || p.kind) + ' prüfen', body, p.status === 'pending' ? async close => {
      await this.post('/proposals/' + id + '/approve', { revision: p.revision, confirm: true });
      close(); this.selected.clear(); toast('Freigabe gespeichert.', 'ok'); await this.renderTab();
    } : null, p.kind === 'operation' ? 'Diese Ablage freigeben' : 'Diesen Vorschlag übernehmen');
  }

  async startSelected(kind) {
    const refs = this.requireSelection();
    await this.post('/jobs', { kind, items: refs.map(i => i.id) });
    toast('Auftrag gestartet. Ergebnisse erscheinen unter Prüfen bzw. Aufträge.', 'ok');
  }

  async operationDialog(explicit = null, proposedTarget = '', proposedName = '') {
    const refs = explicit ? explicit.map(i => ({ id: i.id, revision: i.revision })) : this.requireSelection();
    const targets = (await this.get('/entries/target')).items;
    const action = select([['copy', 'Kopieren – Original behalten'], ['move', 'Verschieben – Quelle nach Prüfung entfernen'],
      ['rename', 'Im selben Ordner umbenennen']]);
    const target = select([['', 'Ziel wählen'], ...targets.map(t => [t.id, t.name + ' / ' + t.data.path])], proposedTarget);
    const name = input(proposedName, 'Leer: bisheriger Dateiname');
    this.modal('Ablage planen', h('div', {}, field('Aktion', action), field('Freigegebener Zielordner', target),
      field('Neuer Name, nur bei einer Datei', name)), async close => {
      const p = await this.post('/operations/preview', { items: refs, action: action.value,
        target_id: target.value, name: name.value });
      close(); await this.showProposal(p.id);
    });
  }

  indexDialog() {
    const refs = this.requireSelection();
    const enabled = select([['yes', 'Inhalt für Suche und Chat freigeben'], ['no', 'Inhalt aus Suche entfernen']]);
    this.modal('Inhaltssuche für ' + refs.length + ' Datei(en)', h('div', {},
      field('Freigabe', enabled), h('p', { text: 'Nur freigegebene Inhalte werden lokal extrahiert und indexiert. Namen und bestätigte Tags bleiben unabhängig davon im Katalog.' })),
    async close => {
      await this.post('/index-selection', { items: refs, enabled: enabled.value === 'yes' });
      close(); this.selected.clear(); await this.loadItems(); toast('Suchfreigabe gespeichert.', 'ok');
    }, 'Suchfreigabe anwenden');
  }

  noteDialog() {
    const refs = this.requireSelection();
    const path = input('NAS-Sammlung.md');
    this.modal('Auswahl mit Obsidian verknüpfen', field('Neue Notiz, relativ zum gewählten Vault', path),
      async close => { const p = await this.post('/notes/preview', { items: refs, path: path.value });
        close(); await this.showProposal(p.id); });
  }

  async contentSearch() {
    const q = input(this.filters.q || '');
    const results = h('div');
    this.modal('Freigegebene Inhalte durchsuchen', h('div', {}, field('Frage oder Suchbegriff', q), results),
      async () => {
        results.replaceChildren(h('p', { text: 'Suche läuft …', role: 'status' }));
        const data = await this.get('/search', { q: q.value });
        results.replaceChildren(...data.results.map(item => this.button(
          item.path + (item.page ? ' · Seite ' + item.page : '') + ': ' + item.snippet,
          async () => { this.dialog.close(); await this.detail(item.item_id); })));
        if (!data.results.length) results.append(h('p', { text: 'Keine freigegebene Quelle gefunden.' }));
      }, 'Suchen');
  }

  async reviews() {
    const stateSelect = select([['pending', 'Zu prüfen'], ['applied', 'Angewendet'], ['approved', 'Freigegebene Ablage'],
      ['rejected', 'Abgelehnt'], ['undone', 'Zurückgenommen']]);
    const list = h('div');
    let offset = 0;
    const page = h('span', { text: 'Seite 1' });
    const next = this.button('Nächste Vorschläge', async () => { offset += 100; await load(); });
    const load = async () => {
      const data = await this.get('/proposals', { status: stateSelect.value, offset });
      page.textContent = 'Seite ' + (Math.floor(offset / 100) + 1);
      next.disabled = data.items.length < 100;
      list.replaceChildren(...data.items.map(p => h('div', { class: 'library-actions card' },
        h('span', { text: (labels[p.kind] || p.kind) + ' · ' + p.created_at }),
        this.button('Ansehen', () => this.showProposal(p.id)))));
      if (!data.items.length) list.append(h('p', { class: 'field__hint', text: 'Keine Vorschläge in diesem Status.' }));
    };
    stateSelect.onchange = () => { offset = 0; load().catch(e => toast(e.message, 'bad')); };
    this.body.replaceChildren(field('Vorschläge', stateSelect), h('div', { class: 'library-actions' },
      this.button('Vorherige Vorschläge', async () => { offset = Math.max(0, offset - 100); await load(); }), page, next), list);
    await load();
  }

  async sourcePage() {
    this.status = await this.get('/status'); this.sources = this.status.sources;
    this.body.replaceChildren(h('div', { class: 'library-actions' },
      this.button('Quelle hinzufügen', () => this.sourceDialog(), true),
      this.button('JSON jetzt sichern', () => this.post('/jobs', { kind: 'backup' })),
      this.button('Wiederherstellen', () => this.restoreDialog()),
      this.button('Docling einrichten', () => this.doclingDialog())));
    for (const s of this.sources) this.body.append(h('div', { class: 'card library-source' },
      h('h3', { text: s.name }), h('p', { class: 'library-path', text: s.root }),
      h('p', { text: (s.kind === 'nas' ? 'NAS / SMB' : 'PC-Ordner') + ' · ' +
        (s.writable ? 'Ablage freigegeben' : 'Nur lesen') + ' · ' + (s.watch ? 'Überwachung an' : 'Manueller Scan') }),
      h('p', { class: 'field__hint', text: s.backup ? (s.backup_pending ? 'JSON-Sicherung ausstehend' :
        'Letzte JSON-Sicherung: ' + (s.backup_at || 'noch keine')) : 'Kein JSON-Sicherungsziel' }),
      s.error ? h('p', { class: 'library-error', text: s.error }) : null,
      h('div', { class: 'library-actions' },
        this.button('Erfassen', () => this.post('/jobs', { kind: 'scan', source_id: s.id })),
        this.button('Freigaben ändern', () => this.sourceDialog(s)))));
    this.body.append(h('p', { class: 'field__hint', text: 'Sicherungen enthalten bestätigte Metadaten und Struktur. Sie ersetzen kein Backup der Originaldateien.' }),
      this.button('Bibliothek für dieses Profil deaktivieren', async () => {
        await this.post('/enabled', { enabled: false }); await this.init();
      }));
  }

  sourceDialog(existing = null) {
    const name = input(existing?.name || '');
    const root = input(existing?.root || '', 'N:\\ oder \\\\NAS\\Freigabe');
    root.disabled = Boolean(existing);
    const kind = select([['pc', 'PC-Ordner'], ['nas', 'NAS / SMB']], existing?.kind || 'nas');
    kind.disabled = Boolean(existing);
    const write = h('input', { type: 'checkbox', checked: existing?.writable });
    const backup = h('input', { type: 'checkbox', checked: existing?.backup });
    const watch = h('input', { type: 'checkbox', checked: existing?.watch });
    const browse = this.button('Ordner auswählen', async () => {
      const data = await api.browseFolder(); if (this.alive && data.path) root.value = data.path;
    });
    this.modal(existing ? 'Quellenfreigaben ändern' : 'Quelle hinzufügen', h('div', {},
      field('Name', name), field('Ordner / UNC-Pfad', root), existing ? null : browse, field('Art', kind),
      field('Geprüfte Dateiablage in dieser Quelle erlauben', write),
      field('JSON-Sicherung in .wissens-ki erlauben', backup),
      field('Änderungen beobachten und Bestand abgleichen', watch),
      h('p', { class: 'field__hint', text: 'Schreibfreigabe erlaubt noch keine automatische Ablage. Die Ordnerstruktur wird nicht kopiert.' })),
    async close => {
      if (existing) await api.patch(this.url('/sources/' + existing.id), {
        name: name.value, revision: existing.revision, writable: write.checked, backup: backup.checked, watch: watch.checked });
      else await this.post('/sources', { name: name.value, root: root.value, kind: kind.value,
        writable: write.checked, backup: backup.checked, watch: watch.checked });
      close(); await this.init();
    }, 'Quelle speichern');
  }

  async structure() {
    this.body.replaceChildren(h('div', { class: 'library-actions' },
      this.button('Zielordner hinzufügen', () => this.targetDialog(), true),
      this.button('Tag-Gruppe', () => this.simpleEntry('group')),
      this.button('Ablageregel', () => this.simpleEntry('rule')),
      this.button('Suchordner freigeben', () => this.simpleEntry('index_scope'))));
    for (const [kind, title] of [['target', 'Deine Zielstruktur'], ['group', 'Tag-Gruppen'],
      ['rule', 'Regeln erzeugen nur Vorschläge'], ['collection', 'Virtuelle Sammlungen'],
      ['index_scope', 'Für Inhaltssuche freigegebene Ordner']]) {
      const data = (await this.get('/entries/' + kind)).items;
      this.body.append(h('h3', { text: title }));
      for (const e of data) this.body.append(h('div', { class: 'card library-actions' },
        h('strong', { text: e.name }), h('span', { class: 'library-path',
          text: e.data.path ?? (e.data.tags || []).join(', ') }),
        this.button('Bearbeiten', () => kind === 'target' ? this.targetDialog(e) :
          kind === 'collection' ? this.saveCollection(e) : this.simpleEntry(kind, e)),
        this.button('Eintrag entfernen', () => this.modal('Einstellung entfernen?',
          h('p', { text: 'Nur die Einstellung wird entfernt. Originaldateien und Ordner bleiben bestehen.' }),
          async close => { await api.del(this.url('/entries/' + e.id)); close(); await this.structure(); }, 'Entfernen'))));
    }
  }

  targetDialog(existing = null) {
    const source = select(this.sources.filter(s => s.writable).map(s => [s.id, s.name]), existing?.data.source_id);
    const path = input(existing?.data.path || '', 'z. B. Dokumente');
    const name = input(existing?.name || '');
    const create = h('input', { type: 'checkbox' });
    this.modal('Zielordner festlegen', h('div', {}, field('Quelle', source), field('Relativer Zielordner', path),
      field('Anzeigename', name), existing ? null : field('Ordner neu anlegen (Elternordner muss bestehen)', create)),
    async close => {
      if (create.checked && !existing) {
        const p = await this.post('/folders/preview', { source_id: source.value, path: path.value, name: name.value });
        close(); await this.showProposal(p.id);
      } else {
        await this.post('/entries/target', { name: name.value, data: { source_id: source.value, path: path.value },
          id: existing?.id || '', revision: existing?.revision || 0 });
        close(); await this.structure();
      }
    }, 'Prüfen / speichern');
  }

  async simpleEntry(kind, existing = null) {
    const name = input(existing?.name || '');
    const tags = input((existing?.data.tags || []).join(', '));
    const sources = select(this.sources.map(s => [s.id, s.name]), existing?.data.source_id);
    const path = input(existing?.data.path || '');
    const targets = select((await this.get('/entries/target')).items.map(t => [t.id, t.name]), existing?.data.target_id);
    const body = h('div', {}, field('Name', name));
    if (kind === 'index_scope') body.append(field('Quelle', sources), field('Relativer Ordner (leer: gesamte Quelle)', path),
      h('p', { text: 'Auch künftig neu erfasste Dokumente dieses Ordners werden für die lokale Inhaltssuche freigegeben.' }));
    else body.append(field('Tags, durch Kommas getrennt', tags));
    if (kind === 'rule') body.append(field('Vorgeschlagener Zielordner', targets),
      h('p', { text: 'Wenn alle Tags passen, erscheint die Regel beim Prüfen der Datei. Sie verschiebt nichts automatisch.' }));
    this.modal(kind === 'index_scope' ? 'Inhaltssuche freigeben' : 'Tags und Regeln', body, async close => {
      const data = kind === 'index_scope' ? { source_id: sources.value, path: path.value } :
        kind === 'rule' ? { tags: tagsOf(tags.value), target_id: targets.value } : { tags: tagsOf(tags.value) };
      await this.post('/entries/' + kind, { name: name.value, data, id: existing?.id || '', revision: existing?.revision || 0 });
      close(); await this.structure();
    }, 'Speichern');
  }

  saveCollection(existing = null) {
    const name = input(existing?.name || '');
    this.modal('Filter als virtuelle Sammlung', h('div', {}, field('Name', name),
      h('p', { text: 'Die aktuellen Bibliotheksfilter werden gespeichert. Dateien bleiben an ihrem Platz.' })),
    async close => { await this.post('/entries/collection', { name: name.value, data: this.filters,
      id: existing?.id || '', revision: existing?.revision || 0 }); close(); await this.renderTab(); }, 'Speichern');
  }

  async renderJobs() {
    const jobs = (await this.get('/jobs')).items;
    this.body.replaceChildren(h('p', { class: 'field__hint', text: 'Aufträge bleiben beim Ansichtswechsel erhalten. Unterbrochene Arbeit kann fortgesetzt werden. Originaldateien werden nie automatisch gelöscht.' }),
      ...jobs.map(j => h('div', { class: 'card library-job' },
        h('strong', { text: (labels[j.kind] || j.kind) + ' · ' + labels[j.status] }),
        h('p', { text: fmtNumber(j.cursor) + (j.total ? ' / ' + fmtNumber(j.total) : '') + ' verarbeitet' }),
        j.error ? h('p', { class: 'library-error', text: j.error }) : null,
        h('div', { class: 'library-actions' },
          ['running', 'queued'].includes(j.status) ? this.button('Pausieren', () =>
            this.post('/jobs/' + j.id + '/control', { action: 'pause' })) : null,
          ['paused', 'failed'].includes(j.status) ? this.button('Fortsetzen', () =>
            this.post('/jobs/' + j.id + '/control', { action: 'resume' })) : null,
          j.status === 'done' && j.error ? this.button('Fehlgeschlagene wiederholen', () =>
            this.post('/jobs/' + j.id + '/control', { action: 'retry' })) : null,
          this.button('Details', async () => {
            const detail = await this.get('/jobs/' + j.id);
            this.modal('Auftragsdetails', h('pre', { class: 'library-preview',
              text: JSON.stringify({ ...j, failures: detail.data.failures, warnings: detail.data.warnings }, null, 2) }));
          })))));
    if (!jobs.length) this.body.append(h('p', { text: 'Noch keine Aufträge.' }));
  }

  async restoreDialog() {
    const source = select(this.sources.filter(s => s.backup).map(s => [s.id, s.name]));
    const previous = h('input', { type: 'checkbox' });
    const mappings = h('div');
    let selections = [];
    const inspect = this.button('Sicherung lesen', async () => {
      const data = await this.post('/restore/inspect', { source_id: source.value, previous: previous.checked });
      mappings.replaceChildren(h('p', { text: data.items + ' bestätigte Dateien · ' + data.created_at }));
      selections = data.sources.map(s => {
        const choice = select(this.sources.map(n => [n.id, n.name]), this.sources.some(n => n.id === s.id) ? s.id : this.sources[0]?.id);
        mappings.append(field('Quelle zuordnen: ' + s.name, choice));
        return [s.id, choice];
      });
    });
    this.modal('JSON-Sicherung wiederherstellen', h('div', {}, field('Sicherungsziel', source),
      field('Vorherige Version verwenden', previous), inspect, mappings),
    async close => {
      if (!selections.length) throw new Error('Bitte zuerst die Sicherung lesen und Quellen zuordnen.');
      const p = await this.post('/restore/preview', { source_id: source.value, previous: previous.checked,
        mapping: Object.fromEntries(selections.map(([id, node]) => [id, node.value])) });
      close(); await this.showProposal(p.id);
    });
  }

  doclingDialog() {
    const python = input(this.status.docling.docling_python);
    const models = input(this.status.docling.docling_models);
    this.modal('Optionale lokale Dokumentanalyse', h('div', {},
      h('p', { text: 'Einmalig setup-docling.ps1 im Projektordner ausführen. Das Skript installiert eine separate Umgebung und lädt OCR-Modelle. Danach werden Python- und Modellpfad hier eingetragen. Die Analyse selbst sperrt Netzwerkzugriffe.' }),
      field('Python der Docling-Umgebung', python), field('Lokaler Modellordner', models)),
    async close => {
      await api.updateProfile(this.profile, { library: { docling_python: python.value, docling_models: models.value } });
      close(); await this.sourcePage();
    }, 'Pfade speichern');
  }

  reconcileDialog(item) {
    const id = input('', 'ID der neu erfassten Datei');
    this.modal('Verschobene Datei zuordnen', h('div', {},
      h('p', { text: 'Die neue Datei zuerst erfassen. Ihre ID steht in der Detailansicht. Tags und stabile ID des alten Eintrags bleiben erhalten.' }),
      field('Neuer Katalogeintrag', id)), async close => {
      const p = await this.post('/reconcile/preview', { old_id: item.id, new_id: id.value });
      close(); await this.showProposal(p.id);
    });
  }
}
