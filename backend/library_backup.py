"""Portable snapshots of accepted metadata only; never a live network database."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .database import new_id, now_iso
from .library_models import LibraryError, Metadata
from .library_paths import safe_path, is_link
from .library_store import dump


def backup_folder(catalog, source):
    if not source["backup"] or not source["writable"]:
        raise LibraryError("Diese Quelle ist nicht als Sicherungsziel freigegeben.")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", catalog.profile.id):
        raise LibraryError("Ungültige Profil-ID.")
    root = safe_path(source["root"], "", catalog.profile.vault_path)
    folder = root
    for part in (".wissens-ki", catalog.profile.id):
        folder = folder / part
        if is_link(folder):
            raise LibraryError("Sicherungsordner darf kein Symlink/Junction sein.")
    return folder


def snapshot(catalog):
    with catalog.lock:
        payload = {
            "format": "lokale-wissens-ki", "version": 1, "profile_id": catalog.profile.id,
            "created_at": now_iso(), "sources": [
                {"id": s["id"], "name": s["name"], "kind": s["kind"]} for s in catalog.sources()],
            "items": [],
            "entries": [entry for kind in ("target", "group", "collection", "rule", "index_scope")
                        for entry in catalog.entries(kind)],
        }
        for row in catalog.rows(
            "SELECT id,source_id,path,size,modified_ns,sha256,tags,description FROM library_items WHERE reviewed=1"):
            row["tags"] = json.loads(row["tags"])
            payload["items"].append(row)
        successes = 0
        for source in catalog.sources():
            if not source["backup"] or not source["backup_pending"]:
                continue
            try:
                folder = backup_folder(catalog, source)
                folder.mkdir(parents=True, exist_ok=True)
                temp = folder / f"catalog-{new_id()}.tmp"
                current, previous = folder / "catalog.json", folder / "catalog.previous.json"
                if is_link(current) or is_link(previous):
                    raise LibraryError("Sicherungsdatei darf kein Link sein.")
                with temp.open("x", encoding="utf-8") as stream:
                    for fragment in json.JSONEncoder(ensure_ascii=False, indent=2).iterencode(payload):
                        stream.write(fragment)
                    stream.flush()
                    os.fsync(stream.fileno())
                with temp.open(encoding="utf-8") as stream:
                    verified = json.load(stream)
                if verified != payload:
                    raise LibraryError("JSON-Prüfung der Sicherung fehlgeschlagen.")
                if current.exists():
                    current.replace(previous)
                temp.replace(current)
                catalog.db.execute(
                    "UPDATE library_sources SET backup_pending=0,backup_at=?,error='' WHERE id=?",
                    (now_iso(), source["id"]))
                successes += 1
            except (OSError, LibraryError, ValueError) as exc:
                catalog.db.execute("UPDATE library_sources SET backup_pending=1,error=? WHERE id=?",
                                   (f"Sicherung ausstehend: {exc}", source["id"]))
        return successes


def read_snapshot(catalog, source_id, previous=False):
    source = catalog.source(source_id)
    path = backup_folder(catalog, source) / ("catalog.previous.json" if previous else "catalog.json")
    if is_link(path) or path.stat().st_size > 512 * 1024 * 1024:
        raise LibraryError("Ungültige oder zu große Sicherung.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != "lokale-wissens-ki" or data.get("version") != 1:
        raise LibraryError("Unbekanntes Sicherungsformat.")
    if data.get("profile_id") != catalog.profile.id:
        raise LibraryError("Die Sicherung gehört zu einem anderen Profil.")
    return data


def restore_preview(catalog, source_id, mapping, previous=False):
    payload = read_snapshot(catalog, source_id, previous)
    changes, unresolved = [], []
    for saved in payload["items"]:
        source = catalog.source(mapping.get(saved["source_id"], saved["source_id"]))
        safe_path(source["root"], saved["path"], catalog.profile.vault_path)
        rows = catalog.rows("SELECT id FROM library_items WHERE source_id=? AND path=? AND missing=0",
                            (source["id"], saved["path"]))
        if not rows:
            unresolved.append(saved["path"])
            continue
        item = catalog.item(rows[0]["id"])
        if not re.fullmatch(r"[a-f0-9]{16}", saved["id"]):
            raise LibraryError("Ungültige Datei-ID in Sicherung.")
        if saved["id"] != item["id"] and catalog.rows("SELECT id FROM library_items WHERE id=?", (saved["id"],)):
            unresolved.append(saved["path"] + " (Datei-ID bereits anderweitig belegt)")
            continue
        catalog.path(item)
        if item["size"] != saved["size"] or (
                item["sha256"] and saved["sha256"] and item["sha256"] != saved["sha256"]):
            unresolved.append(saved["path"])
            continue
        if not (item["sha256"] and saved["sha256"]) and item["modified_ns"] != saved["modified_ns"]:
            unresolved.append(saved["path"])
            continue
        changes.append({
            "id": item["id"], "revision": item["revision"], "path": item["path"],
            "restore_id": saved["id"],
            "before": {"tags": item["tags"], "description": item["description"], "reviewed": item["reviewed"]},
            "after": Metadata(tags=saved["tags"], description=saved["description"]).model_dump(),
        })
    entries = []
    for entry in payload.get("entries", []):
        # Search scopes must be opted into again; restoring metadata never exposes content.
        if entry["kind"] not in {"target", "group", "collection", "rule"}:
            continue
        data = entry["data"]
        if entry["kind"] == "target":
            data["source_id"] = mapping.get(data["source_id"], data["source_id"])
            source = catalog.source(data["source_id"])
            path = safe_path(source["root"], data["path"], catalog.profile.vault_path)
            if not path.is_dir() or not source["writable"]:
                unresolved.append("Zielordner: " + data["path"])
                continue
        if entry["kind"] == "collection" and data.get("source_id"):
            data["source_id"] = mapping.get(data["source_id"], data["source_id"])
        entries.append(entry)
    return catalog.proposal("restore", {"items": changes, "entries": entries, "unresolved": unresolved})


def apply_restore(catalog, proposal):
    with catalog.lock:
        catalog.checked(proposal["data"]["items"])
        pending_entries = []
        # Existing structures are never overwritten. Keep IDs so restored rules refer to restored targets.
        for entry in proposal["data"]["entries"]:
            if catalog.rows("SELECT id FROM library_entries WHERE id=?", (entry["id"],)):
                continue
            data = entry["data"]
            if entry["kind"] == "target":
                source = catalog.source(data["source_id"])
                if not safe_path(source["root"], data["path"], catalog.profile.vault_path).is_dir():
                    raise LibraryError("Zielstruktur seit der Vorschau geändert.")
            if entry["kind"] in {"group", "rule"}:
                Metadata(tags=data.get("tags", []))
            pending_entries.append((entry["id"], entry["kind"], entry["name"], dump(data)))
        for change in proposal["data"]["items"]:
            if change["restore_id"] != change["id"]:
                catalog.db.search.remove("library", change["id"])
        with catalog.db._lock, catalog.db._conn:
            conn = catalog.db._conn
            conn.execute("PRAGMA defer_foreign_keys=ON")
            conn.executemany("INSERT INTO library_entries(id,kind,name,data) VALUES(?,?,?,?)", pending_entries)
            for change in proposal["data"]["items"]:
                catalog._metadata(change["id"], change["after"], True)
                if change["restore_id"] != change["id"]:
                    conn.execute("UPDATE library_items SET id=?,indexed_revision=0 WHERE id=?",
                                 (change["restore_id"], change["id"]))
                    conn.execute("UPDATE library_tags SET item_id=? WHERE item_id=?",
                                 (change["restore_id"], change["id"]))
            conn.execute("UPDATE library_proposals SET status='applied' WHERE id=?", (proposal["id"],))
        catalog.dirty()
        return catalog.get_proposal(proposal["id"])
