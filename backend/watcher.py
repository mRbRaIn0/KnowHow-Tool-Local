"""Beobachtet den aktiven Vault und meldet externe Obsidian-Änderungen."""
from __future__ import annotations

import logging
import os
import threading
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .tools import invalidate_overview
from .vault import IGNORED_DIRS

log = logging.getLogger(__name__)


class _Handler(FileSystemEventHandler):
    def __init__(self, manager: "VaultWatcher", root: Path):
        self.manager = manager
        self.root = root

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.event_type in {"opened", "closed", "closed_no_write"}:
            return
        source = Path(event.src_path)
        destination = Path(getattr(event, "dest_path", "")) if getattr(event, "dest_path", "") else None
        source_ignored = _ignored(self.root, source)
        destination_ok = destination is not None and not _ignored(self.root, destination)
        if source_ignored and not destination_ok:
            return
        if source_ignored and destination_ok:
            source = destination
            destination = None
        self.manager.record(event.event_type, source, destination, event.is_directory)


class VaultWatcher:
    """Genau ein Observer für den gerade aktiven Profil-Vault."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._observer: Optional[Observer] = None
        self._root: Optional[Path] = None
        self._profile_id = ""
        self._revision = 0
        self._events: Deque[Dict[str, Any]] = deque(maxlen=300)

    def ensure(self, profile_id: str, root: Optional[Path]) -> None:
        resolved = root.resolve() if root and root.is_dir() else None
        with self._lock:
            if self._profile_id == profile_id and self._root == resolved and self._observer:
                return
            self._stop_locked()
            self._profile_id = profile_id
            self._root = resolved
            self._events.clear()
            self._revision += 1
            if resolved is None:
                return
            observer = Observer()
            observer.schedule(_Handler(self, resolved), str(resolved), recursive=True)
            observer.daemon = True
            observer.start()
            self._observer = observer
            log.info("Vault-Watcher aktiv: %s", resolved)

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        observer, self._observer = self._observer, None
        if observer:
            observer.stop()
            observer.join(timeout=3)

    def record(self, event_type: str, source: Path, destination: Optional[Path],
               is_directory: bool) -> None:
        with self._lock:
            if self._root is None:
                return
            self._revision += 1
            event = {
                "revision": self._revision,
                "type": event_type,
                "path": _relative(self._root, source),
                "is_dir": bool(is_directory),
            }
            if destination and not _ignored(self._root, destination):
                event["destination"] = _relative(self._root, destination)
            self._events.append(event)
            invalidate_overview(self._root)

    def changes(self, since: int = 0) -> Dict[str, Any]:
        with self._lock:
            events = [dict(item) for item in self._events if item["revision"] > since]
            return {
                "revision": self._revision,
                "changed": self._revision > since,
                "events": events,
                "watching": self._observer is not None,
            }


def _relative(root: Path, path: Path) -> str:
    try:
        return os.path.relpath(str(path), str(root)).replace("\\", "/")
    except ValueError:
        return path.name


def _ignored(root: Path, path: Path) -> bool:
    rel = _relative(root, path)
    parts = Path(rel).parts
    if any(part.startswith(".") or part in IGNORED_DIRS for part in parts):
        return True
    return path.name.endswith((".tmp-lka", ".tmp"))


watcher = VaultWatcher()
