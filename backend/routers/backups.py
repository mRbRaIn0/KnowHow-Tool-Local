"""Lokale Backup-Endpunkte."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..backups import create_backup, list_backups, resolve_backup
from ..deps import current_db, current_profile, current_vault

router = APIRouter(prefix="/api/backups", tags=["backups"])


@router.get("")
async def listing() -> Dict[str, Any]:
    profile = current_profile()
    return {"backups": await asyncio.to_thread(list_backups, profile)}


@router.post("")
async def create() -> Dict[str, Any]:
    profile = current_profile()
    return await asyncio.to_thread(
        create_backup, profile, current_vault(), current_db(profile)
    )


@router.get("/{name}")
async def download(name: str) -> FileResponse:
    try:
        path = resolve_backup(current_profile(), name)
    except FileNotFoundError as exc:
        raise HTTPException(404, {"message": "Backup nicht gefunden.", "kind": "not_found"}) from exc
    return FileResponse(path, media_type="application/zip", filename=path.name)
