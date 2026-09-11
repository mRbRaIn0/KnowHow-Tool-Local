"""Dateien und Ordner im Vault — lesen, schreiben, verwalten.

Alle Endpunkte arbeiten mit vault-relativen Pfaden. Absolute Pfade oder
'..'-Ausbrüche werden in vault.safe_join abgewiesen.
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..deps import current_vault
from ..deps import current_profile
from ..watcher import watcher
from ..vault_guide import ensure_vault_guide
from ..vault import (
    VaultError, build_tree, create_dir, delete_entry, iter_files, kind_for,
    list_dir, move_entry, read_text_file, recent_files, rename_entry, safe_join,
    to_relative, unique_path, write_text_file,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/files", tags=["files"])


def _fail(exc: Exception, status: int = 400) -> HTTPException:
    return HTTPException(status, {"message": str(exc), "kind": "vault"})


@router.get("/tree")
async def tree(path: str = "", depth: int = 2) -> Dict[str, Any]:
    """Ordnerbaum ab einem Pfad; tiefere Ebenen werden bei Bedarf nachgeladen."""
    root = current_vault()
    depth = max(1, min(depth, 5))
    try:
        nodes = await asyncio.to_thread(build_tree, root, path, depth)
    except VaultError as exc:
        raise _fail(exc) from exc
    return {"root": root.name, "path": path, "nodes": [n.to_dict() for n in nodes]}


@router.get("/list")
async def list_folder(path: str = "") -> Dict[str, Any]:
    root = current_vault()
    try:
        nodes = await asyncio.to_thread(list_dir, root, path)
    except VaultError as exc:
        raise _fail(exc) from exc
    return {"path": path, "nodes": [n.to_dict() for n in nodes]}


@router.get("/read")
async def read_file(path: str) -> Dict[str, Any]:
    """Textdatei einlesen. Binärdateien werden über /raw ausgeliefert."""
    root = current_vault()
    try:
        target = safe_join(root, path)
        if kind_for(target) in ("image", "doc"):
            return {"path": to_relative(root, target), "name": target.name,
                    "kind": kind_for(target), "binary": True,
                    "size": target.stat().st_size if target.exists() else 0, "content": ""}
        data = await asyncio.to_thread(read_text_file, root, path)
        data["binary"] = False
        return data
    except VaultError as exc:
        raise _fail(exc, 404 if "nicht gefunden" in str(exc) else 400) from exc


@router.get("/raw")
async def raw_file(path: str) -> FileResponse:
    """Liefert eine Vault-Datei direkt aus (Bilder, PDFs im Viewer)."""
    root = current_vault()
    try:
        target = safe_join(root, path)
    except VaultError as exc:
        raise _fail(exc) from exc
    if not target.is_file():
        raise HTTPException(404, {"message": "Datei nicht gefunden.", "kind": "not_found"})
    media_type, _ = mimetypes.guess_type(target.name)
    # "inline", damit Bilder und PDFs in der Oberfläche angezeigt und nicht
    # heruntergeladen werden.
    return FileResponse(
        target,
        media_type=media_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{target.name}"'},
    )


class WriteRequest(BaseModel):
    path: str
    content: str
    overwrite: bool = True


@router.post("/write")
async def write_file(request: WriteRequest) -> Dict[str, Any]:
    root = current_vault()
    try:
        result = await asyncio.to_thread(
            write_text_file, root, request.path, request.content, request.overwrite
        )
        await asyncio.to_thread(ensure_vault_guide, root, False)
        return result
    except FileExistsError as exc:
        raise HTTPException(409, {
            "message": f"Die Datei '{exc}' existiert bereits.",
            "kind": "exists", "path": str(exc)}) from exc
    except VaultError as exc:
        raise _fail(exc) from exc
    except OSError as exc:
        raise _fail(exc, 500) from exc


class PathRequest(BaseModel):
    path: str


class RenameRequest(BaseModel):
    path: str
    name: str


class MoveRequest(BaseModel):
    path: str
    target_dir: str


class DeleteRequest(BaseModel):
    path: str
    confirm: bool = False


@router.post("/mkdir")
async def make_dir(request: PathRequest) -> Dict[str, Any]:
    root = current_vault()
    try:
        result = await asyncio.to_thread(create_dir, root, request.path)
        await asyncio.to_thread(ensure_vault_guide, root, False)
        return result
    except (VaultError, OSError) as exc:
        raise _fail(exc) from exc


@router.post("/rename")
async def rename(request: RenameRequest) -> Dict[str, Any]:
    root = current_vault()
    try:
        result = await asyncio.to_thread(rename_entry, root, request.path, request.name)
        await asyncio.to_thread(ensure_vault_guide, root, False)
        return result
    except FileExistsError as exc:
        raise HTTPException(409, {"message": f"'{exc}' existiert bereits.", "kind": "exists"}) from exc
    except (VaultError, OSError) as exc:
        raise _fail(exc) from exc


@router.post("/move")
async def move(request: MoveRequest) -> Dict[str, Any]:
    root = current_vault()
    try:
        result = await asyncio.to_thread(move_entry, root, request.path, request.target_dir)
        await asyncio.to_thread(ensure_vault_guide, root, False)
        return result
    except FileExistsError as exc:
        raise HTTPException(409, {"message": f"'{exc}' existiert bereits.", "kind": "exists"}) from exc
    except (VaultError, OSError) as exc:
        raise _fail(exc) from exc


@router.post("/delete")
async def delete(request: DeleteRequest) -> Dict[str, Any]:
    """Löschen nur mit ausdrücklicher Bestätigung aus der Oberfläche."""
    if not request.confirm:
        raise HTTPException(400, {"message": "Löschen erfordert eine Bestätigung.",
                                  "kind": "confirm"})
    root = current_vault()
    try:
        result = await asyncio.to_thread(delete_entry, root, request.path)
        await asyncio.to_thread(ensure_vault_guide, root, False)
        return result
    except (VaultError, OSError) as exc:
        raise _fail(exc) from exc


@router.get("/unique-path")
async def get_unique_path(path: str) -> Dict[str, Any]:
    root = current_vault()
    try:
        return {"path": await asyncio.to_thread(unique_path, root, path)}
    except VaultError as exc:
        raise _fail(exc) from exc


@router.get("/recent")
async def recent(limit: int = 8, kind: Optional[str] = None) -> Dict[str, Any]:
    root = current_vault()
    kinds = [kind] if kind else None
    try:
        return {"files": await asyncio.to_thread(recent_files, root, limit, kinds)}
    except VaultError as exc:
        raise _fail(exc) from exc


@router.get("/exists")
async def exists(path: str) -> Dict[str, Any]:
    root = current_vault()
    try:
        target = safe_join(root, path)
    except VaultError as exc:
        raise _fail(exc) from exc
    return {"exists": target.exists(), "is_dir": target.is_dir()}


@router.get("/index")
async def file_index() -> Dict[str, Any]:
    """Flache Liste aller Vault-Dateien — Basis für WikiLinks und Suche."""
    root = current_vault()

    def collect():
        items = []
        for path in iter_files(root):
            try:
                items.append({
                    'path': to_relative(root, path),
                    'name': path.name,
                    'stem': path.stem,
                    'kind': kind_for(path),
                })
            except VaultError:
                continue
        items.sort(key=lambda item: item['path'].lower())
        return items

    files = await asyncio.to_thread(collect)
    return {'files': files, 'count': len(files)}


@router.get("/changes")
async def changes(since: int = 0) -> Dict[str, Any]:
    """Änderungen seit einer Revision, auch wenn sie direkt aus Obsidian kamen."""
    profile = current_profile()
    try:
        root = current_vault()
    except HTTPException:
        root = None
    await asyncio.to_thread(watcher.ensure, profile.id, root)
    return watcher.changes(max(0, since))
