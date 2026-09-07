"""Durable per-profile queues and optional SMB polling. Work never changes profile."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from .config import store
from .database import registry, new_id, now_iso
from .library_store import LibraryStore, dump
from .library_paths import digest, IGNORED

log = logging.getLogger(__name__)


class Paused(Exception):
    pass


def enqueue(catalog, kind, data):
    # The caller may already hold an approval transaction. Never commit it here.
    with catalog.db._lock:
        nested = catalog.db._conn.in_transaction
        result = _enqueue(catalog, kind, data)
        if not nested:
            catalog.db._conn.commit()
        return result


def _enqueue(catalog, kind, data):
    if kind in {"scan", "backup"}:
        for row in catalog.rows(
            "SELECT * FROM library_jobs WHERE kind=? AND status='queued'", (kind,)):
            if kind == "backup" or json.loads(row["data"]).get("source_id") == data.get("source_id"):
                return row
    jid = new_id()
    stamp = now_iso()
    catalog.db._conn.execute(
        "INSERT INTO library_jobs(id,kind,data,total,created_at,updated_at) VALUES(?,?,?,?,?,?)",
        (jid, kind, dump(data), len(data.get("items", [])), stamp, stamp))
    return catalog.one("SELECT * FROM library_jobs WHERE id=?", (jid,))


def run_job(catalog, job, stopped=lambda: False):
    from .library_content import analyze, index_item
    from .library_backup import snapshot
    from .library_operations import execute_one
    jid, kind = job["id"], job["kind"]
    data = json.loads(job["data"])
    cursor = job["cursor"]
    last_check = [0.0]
    def checkpoint():
        if stopped():
            raise Paused()
        if time.monotonic() - last_check[0] > .25:
            last_check[0] = time.monotonic()
            if catalog.one("SELECT status FROM library_jobs WHERE id=?", (jid,))["status"] != "running":
                raise Paused()
    catalog.db.execute("UPDATE library_jobs SET status='running',error='',updated_at=? WHERE id=?",
                       (now_iso(), jid))
    try:
        if kind == "scan":
            catalog.scan(data["source_id"], checkpoint, lambda n: catalog.db.execute(
                "UPDATE library_jobs SET cursor=?,updated_at=? WHERE id=?", (n, now_iso(), jid)))
            selected = catalog.index_candidates(data["source_id"])
            if selected:
                enqueue(catalog, "index", {"items": selected})
        elif kind == "backup":
            snapshot(catalog)
        else:
            proposal = catalog.get_proposal(data["proposal_id"]) if kind == "execute" else None
            items = proposal["data"]["items"] if proposal else data.get("items", [])
            for index in range(cursor, len(items)):
                checkpoint()
                try:
                    if kind == "execute":
                        execute_one(catalog, proposal, items[index], checkpoint)
                    else:
                        item = catalog.item(items[index])
                        if kind == "hash":
                            value = digest(catalog.path(item), checkpoint)
                            with catalog.lock:
                                catalog.checked([item])
                                catalog.db.execute("UPDATE library_items SET sha256=? WHERE id=?", (value, item["id"]))
                                catalog.dirty()
                        elif kind == "analyze":
                            asyncio.run(analyze(catalog, item))
                        elif kind == "index":
                            warning = asyncio.run(index_item(catalog, item))
                            if warning:
                                data.setdefault("warnings", []).append({"id": item["id"], "error": warning})
                except Paused:
                    raise
                except Exception as exc:
                    if kind == "execute":
                        raise
                    data.setdefault("failures", []).append({"id": items[index], "error": str(exc)})
                catalog.db.execute("UPDATE library_jobs SET cursor=?,data=?,updated_at=? WHERE id=?",
                                   (index + 1, dump(data), now_iso(), jid))
            if proposal:
                catalog.db.execute("UPDATE library_proposals SET status='applied' WHERE id=?", (proposal["id"],))
                if proposal["data"].get("undo_of"):
                    catalog.db.execute("UPDATE library_proposals SET status='undone' WHERE id=?",
                                       (proposal["data"]["undo_of"],))
        catalog.db.execute("UPDATE library_jobs SET status='done',error=?,updated_at=? WHERE id=?",
                           (f"{len(data.get('failures', []))} Datei(en) nicht verarbeitet."
                            if data.get("failures") else "", now_iso(), jid))
        if kind != "backup" and any(s["backup_pending"] for s in catalog.sources()):
            enqueue(catalog, "backup", {})
    except Paused:
        catalog.db.execute("UPDATE library_jobs SET status='paused',updated_at=? WHERE id=?", (now_iso(), jid))
    except Exception as exc:
        log.warning("Bibliotheksauftrag %s: %s", jid, exc)
        catalog.db.execute("UPDATE library_jobs SET status='failed',error=?,updated_at=? WHERE id=?",
                           (str(exc), now_iso(), jid))


class Handler(FileSystemEventHandler):
    def __init__(self, catalog, source_id):
        self.catalog, self.source_id = catalog, source_id

    def on_any_event(self, event):
        if event.event_type in {"opened", "closed", "closed_no_write"}:
            return
        if any(p.casefold() in IGNORED or p.startswith(".lka-") for p in Path(event.src_path).parts):
            return
        enqueue(self.catalog, "scan", {"source_id": self.source_id})


class LibraryManager:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = None
        self.observers = {}
        self.recovered = set()
        self.retry_backup_at = {}

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="nas-library")
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        for observer in list(self.observers.values()):
            observer.stop()
        if self.thread:
            self.thread.join(timeout=5)
        for observer in list(self.observers.values()):
            observer.join(timeout=3)
        self.observers.clear()

    def _loop(self):
        while not self.stop_event.wait(1):
            try:
                enabled = {p.id: p for p in list(store.config.profiles) if p.library.enabled}
                for key, observer in list(self.observers.items()):
                    pid, sid, revision = key
                    outdated = pid not in enabled or not observer.is_alive()
                    if not outdated:
                        lib = LibraryStore(enabled[pid], registry.get(pid, enabled[pid].db_path))
                        rows = lib.rows("SELECT watch,revision FROM library_sources WHERE id=?", (sid,))
                        outdated = not rows or not rows[0]["watch"] or rows[0]["revision"] != revision
                    if outdated:
                        observer.stop()
                        observer.join(timeout=2)
                        del self.observers[key]
                for profile in enabled.values():
                    if self.stop_event.is_set():
                        return
                    catalog = LibraryStore(profile, registry.get(profile.id, profile.db_path))
                    if profile.id not in self.recovered:
                        catalog.db.execute("UPDATE library_jobs SET status='paused' WHERE status='running'")
                        self.recovered.add(profile.id)
                    for source in catalog.sources():
                        key = (profile.id, source["id"], source["revision"])
                        if source["watch"] and key not in self.observers and Path(source["root"]).is_dir():
                            remote = source["kind"] == "nas" or source["root"].startswith("\\\\")
                            observer = PollingObserver(timeout=profile.library.poll_seconds) if remote else Observer()
                            observer.schedule(Handler(catalog, source["id"]), source["root"], recursive=True)
                            observer.daemon = True
                            observer.start()
                            self.observers[key] = observer
                    job = catalog.rows("SELECT * FROM library_jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1")
                    if job:
                        run_job(catalog, job[0], lambda: self.stop_event.is_set() or
                                not (store.get_profile(profile.id) and store.get_profile(profile.id).library.enabled)
                                or store.get_profile(profile.id).vault.path != catalog.profile.vault.path)
                    elif time.monotonic() >= self.retry_backup_at.get(profile.id, 0):
                        if any(s["backup_pending"] for s in catalog.sources()):
                            enqueue(catalog, "backup", {})
                        self.retry_backup_at[profile.id] = time.monotonic() + 60
            except Exception:
                log.exception("Bibliotheks-Hintergrunddienst")


manager = LibraryManager()
