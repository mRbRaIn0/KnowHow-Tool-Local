"""Persistente Rücknahme genau eines Vault-Auftrags, mit Konfliktprüfung."""
from __future__ import annotations

from contextvars import ContextVar
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import threading
import uuid

active_action: ContextVar = ContextVar("vault_action", default=None)
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


async def vault_io(function, *args):
    """Nach Stopp laufende Dateischreibvorgänge vor Freigabe der Sperre beenden."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await task
        except Exception:
            pass
        raise


def vault_lock(root: Path):
    key = str(root.resolve()).casefold()
    with _guard:
        return _locks.setdefault(key, threading.Lock())


def fingerprint(path: Path):
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Kein reguläres Dateiziel: {path.name}")
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


class VaultAction:
    def __init__(self, root: Path, data_dir: Path, chat_id: str):
        self.root = root.resolve()
        key = hashlib.sha256(str(self.root).casefold().encode()).hexdigest()[:24]
        self.directory = data_dir / 'vault-actions' / key
        self.id = uuid.uuid4().hex
        self.folder = self.directory / self.id
        self.entries = {}
        self.chat_id = chat_id
        self.cancelled = False
        self.previous = None

    def before(self, root: Path, relative: str):
        from .vault import safe_join
        if root.resolve() != self.root:
            return
        target = safe_join(root, relative)
        current = fingerprint(target)
        if relative in self.entries:
            if current != self.entries[relative]['after']:
                raise ValueError(f"Datei zwischenzeitlich verändert: {relative}")
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        if not self.entries:
            pointer = self.directory / 'last.json'
            self.previous = json.loads(pointer.read_text(encoding='utf-8')) if pointer.exists() else None
        backup = str(len(self.entries)) + '.bin'
        if current is not None:
            shutil.copyfile(target, self.folder / backup)
        self.entries[relative] = {'before': current, 'after': current, 'backup': backup}
        self.checkpoint()

    def after(self, root: Path, relative: str):
        from .vault import safe_join
        if root.resolve() == self.root and relative in self.entries:
            self.entries[relative]['after'] = fingerprint(safe_join(root, relative))
            self.checkpoint()

    def checkpoint(self):
        if self.entries:
            _save(self.folder / 'manifest.json', {
                'id': self.id, 'root': str(self.root), 'chat_id': self.chat_id,
                'entries': self.entries, 'undone': self.cancelled,
            })
            if not self.cancelled and any(e['before'] != e['after'] for e in self.entries.values()):
                _save(self.directory / 'last.json', {'id': self.id})

    def finish(self):
        self.checkpoint()
        if not any(e['before'] != e['after'] for e in self.entries.values()):
            pointer = self.directory / 'last.json'
            if pointer.exists() and json.loads(pointer.read_text(encoding='utf-8')).get('id') == self.id:
                if self.previous:
                    _save(pointer, self.previous)
                else:
                    pointer.unlink()

    def rollback(self):
        if not any(e['before'] != e['after'] for e in self.entries.values()):
            self.cancelled = True
            return {'undone': False, 'paths': []}
        self.checkpoint()
        result = undo_last(self.root, self.directory.parent.parent, locked=True)
        self.cancelled = True
        return result


def before_change(root: Path, relative: str):
    action = active_action.get()
    if action:
        action.before(root, relative)


def after_change(root: Path, relative: str):
    action = active_action.get()
    if action:
        action.after(root, relative)


def last_action(root: Path, data_dir: Path):
    sample = VaultAction(root, data_dir, '')
    pointer = sample.directory / 'last.json'
    if not pointer.is_file():
        return None
    identifier = json.loads(pointer.read_text(encoding='utf-8')).get('id', '')
    if len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
        raise ValueError('Ungültiges Rücknahmeprotokoll.')
    folder = sample.directory / identifier
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if (manifest['root'] != str(root.resolve()) or manifest.get('undone')
            or not any(e['before'] != e['after'] for e in manifest['entries'].values())):
        return None
    return folder, manifest


def undo_last(root: Path, data_dir: Path, locked=False):
    from .vault import safe_join
    lock = vault_lock(root)
    if not locked and not lock.acquire(blocking=False):
        raise ValueError('Ein Vault-Auftrag läuft noch. Bitte zuerst beenden oder stoppen.')
    try:
        record = last_action(root, data_dir)
        if record is None:
            return {'undone': False, 'paths': []}
        folder, manifest = record
        entries = {p: e for p, e in manifest['entries'].items() if e['before'] != e['after']}
        conflicts = [p for p, e in entries.items() if fingerprint(safe_join(root, p)) != e['after']]
        if conflicts:
            raise ValueError('Rücknahme würde neuere Änderungen überschreiben: ' + ', '.join(conflicts))
        # Alle Originale vor der ersten Mutation auf Integrität prüfen.
        for p, entry in entries.items():
            backup = folder / entry['backup']
            if backup.parent != folder or (entry['before'] is not None and fingerprint(backup) != entry['before']):
                raise ValueError('Rücknahme-Sicherung ist unvollständig: ' + p)
        restored = []
        try:
            for p, entry in entries.items():
                target = safe_join(root, p)
                if target.exists():
                    shutil.copyfile(target, folder / (entry['backup'] + '.redo'))
                if entry['before'] is None:
                    target.unlink(missing_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temp = target.with_name(target.name + '.tmp-lka')
                    shutil.copyfile(folder / entry['backup'], temp)
                    temp.replace(target)
                restored.append(p)
        except OSError:
            for p in reversed(restored):
                entry, target = entries[p], safe_join(root, p)
                if entry['after'] is None:
                    target.unlink(missing_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(folder / (entry['backup'] + '.redo'), target)
            raise
        manifest['undone'] = True
        _save(folder / 'manifest.json', manifest)
        from .tools import invalidate_overview
        invalidate_overview(root)
        return {'undone': True, 'paths': list(entries), 'chat_id': manifest['chat_id']}
    finally:
        if not locked:
            lock.release()
