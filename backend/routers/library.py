"""Explicit profile-bound library API. Propose and approve are separate operations."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import Field

from ..config import store
from ..database import registry, new_id
from ..library_models import (StrictModel, LibrarySource, Metadata, ChangeProposal, FileOperation,
                              Approval, Job, LibraryError, LibraryItem)
from ..library_store import LibraryStore, dump
from ..library_paths import safe_path, relative_path
from ..library_jobs import enqueue
from .. import library_operations, library_backup

router = APIRouter(prefix="/api/library", tags=["library"])


def catalog(profile_id: str):
    profile = store.get_profile(profile_id)
    if not profile or store.config.active_profile != profile_id:
        raise HTTPException(409, "Profil wurde gewechselt. Ansicht bitte neu laden.")
    if not profile.library.enabled:
        raise HTTPException(409, "NAS-Bibliothek ist für dieses Profil deaktiviert.")
    return LibraryStore(profile.model_copy(deep=True), registry.get(profile.id, profile.db_path))


@router.get("/status")
def status(profile_id: str):
    profile = store.get_profile(profile_id)
    if not profile or store.config.active_profile != profile_id:
        raise HTTPException(409, "Profil wurde gewechselt.")
    if not profile.library.enabled:
        return {"enabled": False}
    lib = catalog(profile_id)
    return {"enabled": True, "sources": lib.sources(),
            "stats": lib.one("SELECT count(*) files,coalesce(sum(reviewed),0) reviewed,"
                            "coalesce(sum(missing),0) missing FROM library_items"),
            "vectors": lib.db.search.vec, "vector_error": lib.db.search.vector_error,
            "docling": profile.library.model_dump()}


class Enable(StrictModel):
    enabled: bool


@router.post("/enabled")
def enabled(body: Enable, profile_id: str):
    if store.config.active_profile != profile_id:
        raise HTTPException(409, "Profil wurde gewechselt.")
    store.update_profile(profile_id, {"library": {"enabled": body.enabled}})
    return status(profile_id)


@router.post("/sources")
def source_create(body: LibrarySource, lib=Depends(catalog)):
    with lib.lock:
        return lib.add_source(body)


class SourceUpdate(StrictModel):
    revision: int
    name: str = Field(min_length=1, max_length=150)
    writable: bool
    backup: bool
    watch: bool


@router.patch("/sources/{source_id}")
def source_update(source_id: str, body: SourceUpdate, lib=Depends(catalog)):
    with lib.lock:
        if lib.source(source_id)["revision"] != body.revision:
            raise LibraryError("Quelle wurde verändert.")
        if body.backup and not body.writable:
            raise LibraryError("Sicherung erfordert Schreibfreigabe.")
        lib.db.execute("UPDATE library_sources SET name=?,writable=?,backup=?,watch=?,revision=revision+1,"
                       "backup_pending=? WHERE id=?",
                       (body.name, body.writable, body.backup, body.watch, body.backup, source_id))
        return lib.source(source_id)


@router.get("/items")
def items(source_id: str = "", folder: str = "", extension: str = "", tag: str = "",
          review: str = "", q: str = "", duplicates: bool = False, offset: int = 0,
          limit: int = 100, lib=Depends(catalog)):
    return lib.listing(source_id, folder, extension, tag, review, q, duplicates, offset, limit)


@router.get("/items/{item_id}")
def item(item_id: str, lib=Depends(catalog)):
    value = lib.item(item_id)
    value["source_name"] = lib.source(value["source_id"])["name"]
    value["proposals"] = [
        {"id": p["id"], "kind": p["kind"], "data": json.loads(p["data"])}
        for p in lib.rows(
            "SELECT * FROM library_proposals WHERE status='pending' AND "
            "EXISTS(SELECT 1 FROM json_each(library_proposals.data,'$.items') j "
            "WHERE json_extract(j.value,'$.id')=?) ORDER BY created_at DESC LIMIT 20", (item_id,))]
    value["rules"] = [r for r in lib.entries("rule")
                      if {t.casefold() for t in r["data"]["tags"]}.issubset(
                          {t.casefold() for t in value["tags"]})]
    return value


@router.get("/items/{item_id}/preview")
def preview(item_id: str, lib=Depends(catalog)):
    from ..library_content import TEXT
    path = lib.path(lib.item(item_id))
    if path.suffix.lower() in TEXT:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            return {"kind": "text", "text": stream.read(40000)}
    return {"kind": "image" if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
            else "pdf" if path.suffix.lower() == ".pdf" else "unsupported"}


@router.get("/items/{item_id}/raw")
def raw(item_id: str, lib=Depends(catalog)):
    path = lib.path(lib.item(item_id))
    if path.suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        raise LibraryError("Dieser Dateityp wird nicht im Browser ausgeführt.")
    return FileResponse(path, headers={"Content-Security-Policy": "sandbox",
                                      "X-Content-Type-Options": "nosniff"})


@router.post("/items/{item_id}/reveal")
def reveal(item_id: str, lib=Depends(catalog)):
    path = lib.path(lib.item(item_id))
    if os.name != "nt":
        raise LibraryError("Im Explorer anzeigen ist nur unter Windows verfügbar.")
    subprocess.Popen(["explorer.exe", "/select,", str(path)])
    return {"ok": True}


@router.post("/metadata/preview")
def metadata_preview(body: ChangeProposal, lib=Depends(catalog)):
    if body.metadata is None:
        raise LibraryError("Metadaten fehlen.")
    return lib.metadata_proposal(body.items, body.metadata.model_dump())


@router.post("/operations/preview")
def operation_preview(body: FileOperation, lib=Depends(catalog)):
    return library_operations.prepare(lib, body)


@router.get("/proposals")
def proposals(status: str = "pending", offset: int = 0, lib=Depends(catalog)):
    return {"items": lib.rows("SELECT id,kind,status,revision,created_at FROM library_proposals "
                             "WHERE status=? ORDER BY created_at DESC LIMIT 100 OFFSET ?",
                             (status, max(0, offset)))}


@router.get("/proposals/{pid}")
def proposal(pid: str, offset: int = 0, lib=Depends(catalog)):
    result = lib.get_proposal(pid)
    changes = result["data"].get("items", [])
    result["total"] = len(changes)
    result["data"]["items"] = changes[max(0, offset):max(0, offset) + 100]
    return result


@router.post("/proposals/{pid}/reject")
def reject(pid: str, body: Approval, lib=Depends(catalog)):
    with lib.lock:
        value = lib.get_proposal(pid)
        if value["status"] != "pending" or value["revision"] != body.revision:
            raise LibraryError("Vorschlag ist nicht mehr offen.")
        lib.db.execute("UPDATE library_proposals SET status='rejected' WHERE id=?", (pid,))
        return {"ok": True}


@router.post("/proposals/{pid}/approve")
def approve(pid: str, body: Approval, lib=Depends(catalog)):
    with lib.lock:
        value = lib.get_proposal(pid)
        if value["revision"] != body.revision or value["status"] != "pending":
            raise LibraryError("Vorschlag wurde bereits bearbeitet oder verändert.")
        if value["kind"] == "metadata":
            result = lib.apply_metadata(value)
        elif value["kind"] == "restore":
            result = library_backup.apply_restore(lib, value)
        elif value["kind"] == "operation":
            lib.checked(value["data"]["items"])
            with lib.db._lock, lib.db._conn:
                lib.db._conn.execute("UPDATE library_proposals SET status='approved' WHERE id=?", (pid,))
                result = enqueue(lib, "execute", {"proposal_id": pid, "items": value["data"]["items"]})
        elif value["kind"] == "mkdir":
            data = value["data"]
            source = lib.source(data["source_id"])
            if not source["writable"] or source["revision"] != data["source_revision"]:
                raise LibraryError("Schreibfreigabe wurde verändert.")
            path = safe_path(source["root"], data["path"], lib.profile.vault_path)
            path.mkdir(parents=False, exist_ok=False)
            result = lib.save_entry("target", data["name"], {"source_id": source["id"], "path": data["path"]})
            lib.db.execute("UPDATE library_proposals SET status='applied' WHERE id=?", (pid,))
        elif value["kind"] == "note":
            result = apply_note(lib, value)
        elif value["kind"] == "reconcile":
            from ..library_reconcile import apply
            result = apply(lib, value)
        else:
            raise LibraryError("Unbekannter Vorschlag.")
        enqueue(lib, "backup", {})
        return result


@router.post("/proposals/{pid}/undo")
def undo(pid: str, body: Approval, lib=Depends(catalog)):
    value = lib.get_proposal(pid)
    if value["revision"] != body.revision:
        raise LibraryError("Veraltete Auswahl.")
    if value["kind"] == "metadata":
        lib.undo_metadata(value)
        enqueue(lib, "backup", {})
        return {"ok": True}
    return library_operations.undo_proposal(lib, value)


@router.get("/entries/{kind}")
def entries(kind: str, lib=Depends(catalog)):
    return {"items": lib.entries(kind)}


class Entry(StrictModel):
    name: str
    data: dict
    id: str = ""
    revision: int = 0


@router.post("/entries/{kind}")
def save_entry(kind: str, body: Entry, lib=Depends(catalog)):
    result = lib.save_entry(kind, body.name, body.data, body.id, body.revision)
    if kind == "index_scope":
        lib.purge_excluded()
        index_ids = lib.index_candidates(body.data["source_id"])
        enqueue(lib, "index", {"items": index_ids})
    enqueue(lib, "backup", {})
    return result


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: str, lib=Depends(catalog)):
    with lib.lock:
        row = lib.one("SELECT * FROM library_entries WHERE id=?", (entry_id,))
        lib.db.execute("DELETE FROM library_entries WHERE id=?", (entry_id,))
        if row["kind"] == "index_scope":
            lib.purge_excluded()
        lib.dirty()
        enqueue(lib, "backup", {})
        return {"ok": True}


class Folder(StrictModel):
    source_id: str
    path: str
    name: str


@router.post("/folders/preview")
def folder_preview(body: Folder, lib=Depends(catalog)):
    source = lib.source(body.source_id)
    path = safe_path(source["root"], relative_path(body.path, False), lib.profile.vault_path)
    if not source["writable"] or path.exists() or not path.parent.is_dir():
        raise LibraryError("Schreibfreigabe fehlt, Ziel existiert oder Elternordner fehlt.")
    return lib.proposal("mkdir", {**body.model_dump(), "source_revision": source["revision"]})


@router.post("/jobs")
def create_job(body: Job, lib=Depends(catalog)):
    data = body.model_dump()
    if body.kind == "scan":
        lib.source(body.source_id)
    for item_id in body.items:
        lib.item(item_id)
    if body.kind == "index" and any(not lib.allow_index(lib.item(i)) for i in body.items):
        raise LibraryError("Inhaltssuche muss für diese Dateien ausdrücklich freigegeben werden.")
    return enqueue(lib, body.kind, data)


@router.get("/jobs")
def jobs(lib=Depends(catalog)):
    rows = lib.rows("SELECT id,kind,status,cursor,total,error,created_at,updated_at "
                    "FROM library_jobs ORDER BY created_at DESC LIMIT 50")
    return {"items": rows}


@router.get("/jobs/{jid}")
def job_detail(jid: str, lib=Depends(catalog)):
    value = lib.one("SELECT * FROM library_jobs WHERE id=?", (jid,))
    value["data"] = json.loads(value["data"])
    return value


class Control(StrictModel):
    action: Literal["pause", "resume", "retry"]


@router.post("/jobs/{jid}/control")
def control_job(jid: str, body: Control, lib=Depends(catalog)):
    # Do not acquire the operation lock: pause must interrupt a streaming transfer.
    value = lib.one("SELECT * FROM library_jobs WHERE id=?", (jid,))
    if body.action == "pause" and value["status"] in {"running", "queued"}:
        lib.db.execute("UPDATE library_jobs SET status='paused' WHERE id=?", (jid,))
    elif body.action in {"resume", "retry"} and value["status"] in {"paused", "failed"}:
        lib.db.execute("UPDATE library_jobs SET status='queued',error='' WHERE id=?", (jid,))
    elif body.action == "retry" and value["status"] == "done":
        data = json.loads(value["data"])
        return enqueue(lib, value["kind"], {"items": [f["id"] for f in data.get("failures", [])]})
    else:
        raise LibraryError("Auftrag kann in diesem Zustand nicht geändert werden.")
    return {"ok": True}


class IndexSelection(StrictModel):
    items: list[LibraryItem] = Field(min_length=1, max_length=500)
    enabled: bool


@router.post("/index-selection")
def index_selection(body: IndexSelection, lib=Depends(catalog)):
    with lib.lock:
        items = lib.checked(body.items)
        for item in items:
            lib.db.execute("UPDATE library_items SET index_enabled=?,indexed_revision=0,revision=revision+1 WHERE id=?",
                           (1 if body.enabled else -1, item["id"]))
            if not body.enabled:
                lib.db.search.remove("library", item["id"])
        if body.enabled:
            return enqueue(lib, "index", {"items": [i["id"] for i in items]})
        return {"ok": True}


@router.get("/search")
async def search(q: str, lib=Depends(catalog)):
    from ..ollama_client import OllamaClient
    vector = []
    try:
        client = OllamaClient(lib.profile.ollama.base_url, True)
        vector = (await client.embed(lib.profile.ollama.embed_model, [q]))[0]
    except Exception:
        pass
    results = await asyncio.to_thread(lib.db.search.search, q, vector,
                                      lib.profile.ollama.embed_model, ("library",), 20)
    return {"results": results}


class Restore(StrictModel):
    source_id: str
    mapping: dict[str, str] = Field(default_factory=dict)
    previous: bool = False


@router.post("/restore/inspect")
def restore_inspect(body: Restore, lib=Depends(catalog)):
    data = library_backup.read_snapshot(lib, body.source_id, body.previous)
    return {"sources": data["sources"], "items": len(data["items"]), "created_at": data["created_at"]}


@router.post("/restore/preview")
def restore_preview(body: Restore, lib=Depends(catalog)):
    result = library_backup.restore_preview(lib, body.source_id, body.mapping, body.previous)
    return {"id": result["id"]}


class Note(StrictModel):
    items: list[LibraryItem] = Field(min_length=1, max_length=100)
    path: str


@router.post("/notes/preview")
def note_preview(body: Note, lib=Depends(catalog)):
    from ..vault import require_root, safe_join
    root = require_root(lib.profile.vault_path)
    relative_path(body.path, False)
    target = safe_join(root, body.path)
    if target.suffix.lower() != ".md" or target.exists() or not target.parent.is_dir():
        raise LibraryError("Neue Markdown-Notiz in einem vorhandenen Vault-Ordner wählen.")
    items = lib.checked(body.items)
    lines = ["---", "type: nas-sammlung", "library_ids: " + dump([i["id"] for i in items]), "---",
             "", "# " + target.stem, ""]
    for item in items:
        uri = lib.path(item).as_uri()
        label = item["name"].replace("[", r"\[").replace("]", r"\]")
        lines += ["## " + label, "", item["description"] or "(Keine bestätigte Beschreibung.)", "",
                  "Tags: " + ", ".join(item["tags"]), "", f"[Originaldatei: {label}]({uri})",
                  f"\nBibliotheks-ID: {item['id']}", ""]
    return lib.proposal("note", {"items": [{"id": i["id"], "revision": i["revision"],
                                           "path": i["path"]} for i in items],
                                  "vault": str(root.resolve()), "path": body.path,
                                  "content": "\n".join(lines)})


def apply_note(lib, proposal):
    from ..vault import require_root, safe_join
    root = require_root(lib.profile.vault_path)
    data = proposal["data"]
    if str(root.resolve()) != data["vault"]:
        raise LibraryError("Vault wurde seit der Vorschau gewechselt.")
    lib.checked(data["items"])
    path = safe_join(root, data["path"])
    with path.open("x", encoding="utf-8") as stream:
        stream.write(data["content"])
    lib.db.execute("UPDATE library_proposals SET status='applied' WHERE id=?", (proposal["id"],))
    return {"path": data["path"]}


class Reconcile(StrictModel):
    old_id: str
    new_id: str


@router.post("/reconcile/preview")
def reconcile_preview(body: Reconcile, lib=Depends(catalog)):
    from ..library_reconcile import prepare
    return prepare(lib, body.old_id, body.new_id)
