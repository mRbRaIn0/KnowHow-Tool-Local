"""Anhänge hochladen, auflisten und wieder entfernen.

Die Dateien landen in einem Zwischenbereich je Chat. In den Vault kommen sie
erst, wenn das Modell sie ausdrücklich übernimmt.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import attachments
from ..attachments import AttachmentError
from ..deps import current_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/attachments", tags=["attachments"])


def eigener_chat(chat_id: str) -> Dict[str, Any]:
    """Nur Chats des aktiven Profils.

    Die Zwischenablage liegt für alle Profile unter derselben Wurzel; erst
    diese Prüfung bindet einen Anhang an sein Profil. Ohne sie wären die
    Anhänge eines Geschäftschats aus dem privaten Profil lesbar.
    """
    chat = current_db().get_chat(chat_id)
    if not chat:
        raise HTTPException(404, {"message": "Chat nicht gefunden.", "kind": "not_found"})
    return chat


@router.post("/{chat_id}")
async def upload(chat_id: str, files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    """Nimmt mehrere Dateien auf einmal entgegen."""
    chat = eigener_chat(chat_id)
    if chat.get("purpose") == "ask":
        raise HTTPException(400, {
            "message": (
                "Anhänge gehören in ‚Wissen erweitern‘. Der Fragen-Chat bleibt "
                "ein reiner Lesezugriff auf die Wissensbasis."
            ),
            "kind": "wrong_chat_mode",
        })
    if not files:
        raise HTTPException(400, {"message": "Es wurden keine Dateien übergeben.", "kind": "empty"})

    gespeichert: List[dict] = []
    fehler: List[dict] = []

    for upload_file in files:
        try:
            data = await upload_file.read()
            item = await asyncio.to_thread(
                attachments.store, chat_id, upload_file.filename or "datei", data
            )
            gespeichert.append(item)
        except AttachmentError as exc:
            fehler.append({"name": upload_file.filename, "grund": str(exc)})
        except OSError as exc:
            log.warning("Anhang %s konnte nicht gespeichert werden: %s", upload_file.filename, exc)
            fehler.append({"name": upload_file.filename, "grund": str(exc)})
        finally:
            await upload_file.close()

    return {"gespeichert": gespeichert, "fehler": fehler,
            "alle": attachments.pending(chat_id)}


@router.get("/{chat_id}")
async def listing(chat_id: str, alle: bool = False) -> Dict[str, Any]:
    """Standardmaessig nur die Anhaenge der naechsten Eingabe.

    Mit ?alle=1 die gesamte Anhangshistorie des Chats.
    """
    eigener_chat(chat_id)
    return {"attachments": attachments.listing(chat_id, nur_offen=not alle)}


@router.get("/{chat_id}/datei")
async def raw(chat_id: str, name: str) -> FileResponse:
    """Liefert einen Anhang aus — für die Vorschau in der Oberfläche."""
    eigener_chat(chat_id)
    try:
        path = attachments.resolve(chat_id, name)
    except AttachmentError as exc:
        raise HTTPException(404, {"message": str(exc), "kind": "not_found"}) from exc
    import mimetypes
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(path, media_type=media_type or "application/octet-stream",
                        headers={"Content-Disposition": f'inline; filename="{path.name}"'})


@router.delete("/{chat_id}/datei")
async def delete(chat_id: str, name: str) -> Dict[str, Any]:
    eigener_chat(chat_id)
    try:
        await asyncio.to_thread(attachments.remove, chat_id, name)
    except AttachmentError as exc:
        raise HTTPException(404, {"message": str(exc), "kind": "not_found"}) from exc
    return {"deleted": True, "name": name}


@router.delete("/{chat_id}")
async def clear(chat_id: str) -> Dict[str, Any]:
    eigener_chat(chat_id)
    await asyncio.to_thread(attachments.clear, chat_id)
    return {"cleared": True}
