// Dateien: Vault-Baum links, Editor bzw. Betrachter in der Mitte.

import { api, uploadToVault } from '../api.js';
import { t } from '../i18n.js';
import { collectLinks, renderMarkdown, splitFrontmatter } from '../markdown.js';
import {
  baseName, confirmDialog, fill, fmtBytes, fmtDate, h, icon, kv, parentDir,
  promptDialog, toast,
} from '../util.js';
import {
  markdownOptions, navigate, on, refreshFileIndex, resolveLink, state, vaultReady,
} from '../store.js';

let elements = {};
let editor = { path: '', original: '', dirty: false, mode: 'split' };
const openFolders = new Set();
let offVaultChange = null;

export function unmount() {
  window.removeEventListener('keydown', onKeyDown);
  offVaultChange?.();
  offVaultChange = null;
  elements = {};
}

export async function mount({ route, el }) {
  elements = { rail: el.rail, main: el.main, context: el.context };
  window.addEventListener('keydown', onKeyDown);
  offVaultChange = on('vault:changed', handleVaultChange);

  if (!vaultReady()) {
    el.main.append(noVaultState());
    return;
  }

  await renderTree();

  if (route.params.new) {
    await createNote(route.params.path || '');
    return;
  }
  const path = route.params.path || '';
  if (path) await openFile(path);
  else el.main.append(pickState());
}

function noVaultState() {
  return h('div', { class: 'empty', style: 'height:100%' },
    icon('folder-open'),
    h('h3', { text: t('common.noVault') }),
    h('p', { text: t('files.noVaultText') }),
    h('button', {
      class: 'btn btn--primary',
      onclick: async () => {
        const picked = await api.browseFolder().catch((error) => { toast(error.message, 'bad'); return null; });
        if (!picked || picked.cancelled) return;
        await api.updateProfile(state.status.profile.id, { vault: { path: picked.path } });
        location.reload();
      },
    }, t('dash.chooseFolder')));
}

function pickState() {
  return h('div', { class: 'empty', style: 'height:100%' },
    icon('files'),
    h('h3', { text: t('files.noFile') }),
    h('p', { text: t('files.noFileText') }),
    h('button', { class: 'btn btn--primary', onclick: () => createNote('') }, icon('plus'), t('dash.newNote')));
}

/* ----------------------------------------------------- Dateibaum */

async function renderTree() {
  const head = h('div', { class: 'rail-head' },
    h('span', { class: 'label', text: state.status?.vault?.name || 'Vault' }),
    h('button', { class: 'icon-btn', title: t('dash.newNote'), onclick: () => createNote(currentFolder()) }, icon('plus')),
    h('button', { class: 'icon-btn', title: t('files.newFolder'), onclick: () => createFolder(currentFolder()) }, icon('folder-open')),
    h('button', { class: 'icon-btn', title: t('files.uploadHint'), onclick: () => pickUpload(currentFolder()) }, icon('clip')),
    h('button', { class: 'icon-btn', title: t('files.showInExplorer'), onclick: () => reveal('') }, icon('external')));
  const tree = h('div', { class: 'tree' });
  tree.addEventListener('dragover', (event) => {
    const types = Array.from(event.dataTransfer?.types || []);
    if (types.includes('application/x-vault-path') || types.includes('Files')) event.preventDefault();
  });
  tree.addEventListener('drop', (event) => {
    if (event.target.closest('.tree__row')) return;
    if (droppedFiles(event, '')) return;
    moveDropped(event, '');
  });
  elements.rail.replaceChildren(head, tree);
  elements.tree = tree;

  try {
    const data = await api.tree('', 2);
    tree.replaceChildren(...data.nodes.map((node) => renderNode(node, 0)));
  } catch (error) {
    tree.append(h('p', { class: 'field__hint', style: 'padding:8px', text: error.message }));
  }
}

function renderNode(node, depth) {
  if (node.type === 'dir') return renderFolder(node, depth);
  return renderFileRow(node);
}

function renderFolder(node, depth) {
  const caret = icon('chevron', 'tree__caret');
  const children = h('div', { class: 'tree__children', style: 'display:none' });
  const row = h('button', { class: 'tree__row', title: node.path },
    caret, h('span', { class: 'tree__name', text: node.name }));

  const toggle = async () => {
    const open = children.style.display !== 'none';
    if (open) {
      children.style.display = 'none';
      caret.classList.remove('is-open');
      openFolders.delete(node.path);
      return;
    }
    caret.classList.add('is-open');
    children.style.display = '';
    openFolders.add(node.path);
    if (!children.dataset.loaded) {
      const items = node.children ?? (await api.tree(node.path, 1).then((d) => d.nodes).catch(() => []));
      children.replaceChildren(...items.map((child) => renderNode(child, depth + 1)));
      children.dataset.loaded = '1';
    }
  };
  row.addEventListener('click', toggle);
  row.addEventListener('contextmenu', (event) => { event.preventDefault(); folderMenu(node); });
  makeDraggable(row, node);
  row.addEventListener('dragover', (event) => {
    const types = Array.from(event.dataTransfer?.types || []);
    if (!types.includes('application/x-vault-path') && !types.includes('Files')) return;
    event.preventDefault();
    event.stopPropagation();
    row.classList.add('is-drop-target');
  });
  row.addEventListener('dragleave', () => row.classList.remove('is-drop-target'));
  row.addEventListener('drop', (event) => {
    row.classList.remove('is-drop-target');
    if (droppedFiles(event, node.path)) return;
    moveDropped(event, node.path);
  });

  if (openFolders.has(node.path)) setTimeout(toggle, 0);
  return h('div', {}, row, children);
}

function renderFileRow(node) {
  const row = h('button', {
    class: `tree__row ${node.path === editor.path ? 'is-active' : ''}`,
    title: node.path,
    onclick: () => navigate(`/files?path=${encodeURIComponent(node.path)}`),
  },
    h('span', { class: 'tree__kind', dataset: { kind: node.kind } }),
    h('span', { class: 'tree__name', text: node.name }));
  row.addEventListener('contextmenu', (event) => { event.preventDefault(); fileMenu(node); });
  makeDraggable(row, node);
  row.dataset.path = node.path;
  return row;
}

function makeDraggable(row, node) {
  row.draggable = true;
  row.addEventListener('dragstart', (event) => {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('application/x-vault-path', node.path);
    event.dataTransfer.setData('text/plain', node.path);
    row.classList.add('is-dragging');
  });
  row.addEventListener('dragend', () => row.classList.remove('is-dragging'));
}

/** Dateien aus dem Explorer: sofort in den Zielordner, gleiche Namen nummeriert. */
function droppedFiles(event, targetDir) {
  const files = [...(event.dataTransfer?.files || [])];
  if (!files.length) return false;
  event.preventDefault();
  event.stopPropagation();
  uploadInto(files, targetDir);
  return true;
}

function pickUpload(targetDir) {
  const picker = h('input', { type: 'file', multiple: true });
  picker.addEventListener('change', () => uploadInto([...picker.files], targetDir));
  picker.click();
}

async function uploadInto(files, targetDir) {
  if (!files.length) return;
  try {
    const result = await uploadToVault(files, targetDir);
    for (const problem of result.fehler || []) toast(`${problem.name}: ${problem.grund}`, 'bad');
    const saved = result.gespeichert || [];
    if (saved.length) {
      toast(saved.length === 1 ? t('files.savedPath', { path: saved[0].path }) : t('files.filesSavedIn', { n: saved.length, folder: targetDir || t('files.vaultRoot') }), 'ok');
      await refreshFileIndex();
      if (targetDir) openFolders.add(targetDir);
      await renderTree();
    }
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function moveDropped(event, targetDir) {
  const source = event.dataTransfer?.getData('application/x-vault-path');
  if (!source || source === targetDir || parentDir(source) === targetDir) return;
  event.preventDefault();
  event.stopPropagation();
  try {
    const result = await api.moveEntry(source, targetDir);
    await refreshFileIndex();
    await renderTree();
    if (editor.path === source || editor.path.startsWith(`${source}/`)) {
      const nextPath = editor.path === source
        ? result.path
        : `${result.path}${editor.path.slice(source.length)}`;
      navigate(`/files?path=${encodeURIComponent(nextPath)}`);
    }
    toast(t('files.movedTo', { folder: targetDir || t('files.vaultRoot') }), 'ok');
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function handleVaultChange(change) {
  if (!elements.tree) return;
  await renderTree();
  if (!editor.path || editor.dirty) return;
  const relevant = (change.events || []).some((item) =>
    item.path === editor.path || item.destination === editor.path);
  if (relevant) await openFile(editor.path);
}

function currentFolder() {
  return editor.path ? parentDir(editor.path) : '';
}

function markActive(path) {
  for (const row of elements.tree?.querySelectorAll('.tree__row[data-path]') || []) {
    row.classList.toggle('is-active', row.dataset.path === path);
  }
}

/* -------------------------------------------------- Datei öffnen */

async function openFile(path) {
  let data;
  try {
    data = await api.readFile(path);
  } catch (error) {
    toast(error.message, 'bad');
    elements.main.replaceChildren(pickState());
    return;
  }

  state.activeFilePath = path;
  markActive(path);

  if (data.binary) {
    renderViewer(data);
    renderContext(data, null);
    return;
  }
  renderEditor(data);
  renderContext(data, data.content);
}

function renderViewer(data) {
  const url = api.rawUrl(data.path);
  const body = data.kind === 'image'
    ? h('img', { src: url, alt: data.name })
    : h('iframe', { src: url, title: data.name });

  elements.main.replaceChildren(h('div', { class: 'editor' },
    h('div', { class: 'editor__bar' },
      h('span', { class: 'editor__path', html: `${escapePath(parentDir(data.path))}<b>${escapeHtml(data.name)}</b>` }),
      h('button', { class: 'btn btn--sm', onclick: () => reveal(data.path) }, icon('external'), t('files.inExplorer')),
      h('button', { class: 'btn btn--sm btn--danger', onclick: () => deleteFile(data) }, icon('trash'), t('common.delete'))),
    h('div', { class: 'viewer' }, body)));
  editor = { path: data.path, original: '', dirty: false, mode: editor.mode };
}

function renderEditor(data) {
  editor = { path: data.path, original: data.content, dirty: false, mode: editor.mode };

  const textarea = h('textarea', {
    spellcheck: 'false',
    oninput: () => { setDirty(textarea.value !== editor.original); updatePreview(textarea.value); },
  });
  textarea.value = data.content;

  const preview = h('div', { class: 'md' });
  const panes = h('div', { class: `editor__panes is-${editor.mode}` },
    h('div', { class: 'editor__code' }, textarea),
    h('div', { class: 'editor__preview' }, preview));

  const dirtyDot = h('span', { class: 'dirty-dot', style: 'display:none' });
  const saveButton = h('button', { class: 'btn btn--sm btn--primary', onclick: save }, icon('save'), t('common.save'));

  elements.main.replaceChildren(h('div', { class: 'editor' },
    h('div', { class: 'editor__bar' },
      h('span', { class: 'editor__path', html: `${escapePath(parentDir(data.path))}<b>${escapeHtml(data.name)}</b>` }),
      dirtyDot,
      modeSwitch(panes),
      h('button', { class: 'btn btn--sm', onclick: () => reveal(data.path) }, icon('external'), t('files.explorer')),
      h('button', { class: 'btn btn--sm', onclick: () => renameFile({ path: data.path, name: data.name }) }, icon('pencil'), t('common.rename')),
      h('button', { class: 'btn btn--sm btn--danger', onclick: () => deleteFile(data) }, icon('trash')),
      saveButton),
    panes));

  elements.textarea = textarea;
  elements.preview = preview;
  elements.dirtyDot = dirtyDot;
  updatePreview(data.content);
}

function modeSwitch(panes) {
  const modes = [['single', t('files.modeText')], ['split', t('files.modeSplit')], ['preview', t('files.modePreview')]];
  const wrap = h('div', { class: 'row', style: 'gap:2px' });
  for (const [mode, label] of modes) {
    wrap.append(h('button', {
      class: `btn btn--sm ${editor.mode === mode ? 'btn--primary' : 'btn--ghost'}`,
      onclick: () => {
        editor.mode = mode;
        panes.className = `editor__panes is-${mode}`;
        for (const [index, button] of [...wrap.children].entries()) {
          button.className = `btn btn--sm ${modes[index][0] === mode ? 'btn--primary' : 'btn--ghost'}`;
        }
      },
    }, label));
  }
  return wrap;
}

function setDirty(dirty) {
  editor.dirty = dirty;
  if (elements.dirtyDot) elements.dirtyDot.style.display = dirty ? '' : 'none';
}

function updatePreview(text) {
  if (!elements.preview) return;
  elements.preview.innerHTML = renderMarkdown(text, markdownOptions());
  for (const link of elements.preview.querySelectorAll('a.wikilink')) {
    link.addEventListener('click', onWikiLink);
  }
  renderContext({ path: editor.path, name: baseName(editor.path) }, text);
}

function onWikiLink(event) {
  event.preventDefault();
  const link = event.currentTarget;
  const path = link.dataset.path;
  if (path) { navigate(`/files?path=${encodeURIComponent(path)}`); return; }

  const target = link.dataset.wikilink;
  confirmDialog({
    title: t('files.noteMissing'),
    message: t('files.noteMissingText', { target }),
    confirmLabel: t('common.create'),
  }).then(async (ok) => {
    if (!ok) return;
    const folder = currentFolder();
    const path2 = `${folder ? `${folder}/` : ''}${target}${target.endsWith('.md') ? '' : '.md'}`;
    try {
      await api.writeFile(path2, `# ${target.replace(/\.md$/, '')}\n\n`, false);
      await refreshFileIndex();
      await renderTree();
      navigate(`/files?path=${encodeURIComponent(path2)}`);
    } catch (error) {
      toast(error.message, 'bad');
    }
  });
}

async function save() {
  if (!elements.textarea) return;
  const content = elements.textarea.value;
  try {
    await api.writeFile(editor.path, content, true);
    editor.original = content;
    setDirty(false);
    toast(t('files.savedName', { name: baseName(editor.path) }), 'ok');
    await refreshFileIndex();
  } catch (error) {
    toast(error.message, 'bad');
  }
}

function onKeyDown(event) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault();
    if (editor.dirty) save();
  }
}

/* ------------------------------------------------- Dateiaktionen */

async function createNote(folder) {
  const name = await promptDialog({
    title: t('dash.newNote'),
    description: folder ? t('files.createdIn', { folder }) : t('files.createdInRoot'),
    label: t('chat.titleLabel'), value: t('dash.newNote'), confirmLabel: t('common.create'),
  });
  if (!name) return;
  const clean = name.replace(/[\\/:*?"<>|]/g, '-');
  const path = `${folder ? `${folder}/` : ''}${clean}${clean.endsWith('.md') ? '' : '.md'}`;
  try {
    const target = (await api.uniquePath(path)).path;
    await api.writeFile(target, `# ${clean.replace(/\.md$/, '')}\n\n`, false);
    await refreshFileIndex();
    await renderTree();
    navigate(`/files?path=${encodeURIComponent(target)}`);
    toast(t('files.noteCreated'), 'ok');
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function createFolder(parent) {
  const name = await promptDialog({
    title: t('files.newFolder'),
    description: parent ? t('files.createdIn', { folder: parent }) : t('files.createdInRoot'),
    label: t('files.folderName'), value: '', confirmLabel: t('common.create'),
  });
  if (!name) return;
  try {
    await api.mkdir(`${parent ? `${parent}/` : ''}${name}`);
    await renderTree();
    toast(t('files.folderCreated'), 'ok');
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function renameFile(node) {
  const name = await promptDialog({
    title: t('common.rename'), label: t('files.newName'), value: node.name, confirmLabel: t('common.rename'),
  });
  if (!name || name === node.name) return;
  try {
    const result = await api.renameEntry(node.path, name);
    await refreshFileIndex();
    await renderTree();
    if (editor.path === node.path) navigate(`/files?path=${encodeURIComponent(result.path)}`);
    toast(t('files.renamed'), 'ok');
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function deleteFile(node) {
  const ok = await confirmDialog({
    title: t('files.deleteTitle'),
    message: t('files.deleteText', { path: node.path }),
    confirmLabel: t('common.delete'), danger: true,
  });
  if (!ok) return;
  try {
    await api.deleteEntry(node.path);
    await refreshFileIndex();
    await renderTree();
    toast(t('files.deleted'), 'ok');
    navigate('/files');
  } catch (error) {
    toast(error.message, 'bad');
  }
}

async function reveal(path) {
  try {
    await api.reveal(path);
  } catch (error) {
    toast(error.message, 'bad');
  }
}

function fileMenu(node) {
  navigate(`/files?path=${encodeURIComponent(node.path)}`);
}

function folderMenu(node) {
  promptDialog({
    title: node.name,
    description: t('files.folderMenuText'),
    label: t('files.newNoteName'), value: t('dash.newNote'), confirmLabel: t('files.createNote'),
  }).then(async (name) => {
    if (!name) return;
    const path = `${node.path}/${name}${name.endsWith('.md') ? '' : '.md'}`;
    try {
      const target = (await api.uniquePath(path)).path;
      await api.writeFile(target, `# ${name.replace(/\.md$/, '')}\n\n`, false);
      await refreshFileIndex();
      await renderTree();
      navigate(`/files?path=${encodeURIComponent(target)}`);
    } catch (error) {
      toast(error.message, 'bad');
    }
  });
}

/* --------------------------------------------------------- Kontext */

function renderContext(data, content) {
  const blocks = [
    h('div', { class: 'ctx-block' },
      h('span', { class: 'label', text: t('files.file') }),
      kv([
        [t('ctx.name'), data.name || baseName(data.path)],
        [t('files.folder'), parentDir(data.path) || t('files.rootShort')],
        [t('dash.size'), data.size ? fmtBytes(data.size) : null],
        [t('files.modified'), data.modified ? fmtDate(data.modified) : null],
      ])),
  ];

  if (typeof content === 'string') {
    const { frontmatter } = splitFrontmatter(content);
    if (frontmatter && Object.keys(frontmatter).length) {
      blocks.push(h('div', { class: 'ctx-block' },
        h('span', { class: 'label', text: t('files.metadata') }),
        h('dl', { class: 'ctx-kv' },
          ...Object.entries(frontmatter).flatMap(([key, value]) =>
            [h('dt', { text: key }), h('dd', { text: value })]))));
    }

    const links = collectLinks(content);
    if (links.length) {
      blocks.push(h('div', { class: 'ctx-block' },
        h('span', { class: 'label', text: t('files.links', { n: links.length }) }),
        h('div', { class: 'list' },
          ...links.map((link) => {
            const resolved = resolveLink(link.target);
            return h('button', {
              class: 'list__item',
              onclick: () => resolved
                ? navigate(`/files?path=${encodeURIComponent(resolved)}`)
                : toast(t('files.linkMissing', { target: link.target })),
            },
              icon(link.embed ? 'image' : 'note'),
              h('span', { class: 'list__main' },
                h('span', { class: 'list__title', text: link.alias || link.target }),
                h('span', { class: 'list__sub', text: resolved || t('files.notFound') })));
          }))));
    }

    const backlinks = findBacklinks(data.path);
    if (backlinks.length) {
      blocks.push(h('div', { class: 'ctx-block' },
        h('span', { class: 'label', text: t('files.mentionedIn', { n: backlinks.length }) }),
        h('div', { class: 'list' },
          ...backlinks.map((file) => h('button', {
            class: 'list__item',
            onclick: () => navigate(`/files?path=${encodeURIComponent(file.path)}`),
          }, icon('note'),
            h('span', { class: 'list__main' },
              h('span', { class: 'list__title', text: file.name }),
              h('span', { class: 'list__sub', text: file.path })))))));
    }
  }

  fill(elements.context, ...blocks);
}

// Backlinks über den Dateinamen: günstig und für den Anfang ausreichend.
// Die inhaltsbasierte Variante kommt mit dem Suchindex in Phase 3.
function findBacklinks() {
  return [];
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"]/g, (char) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[char]));
}

function escapePath(path) {
  return path ? `${escapeHtml(path)}/` : '';
}
