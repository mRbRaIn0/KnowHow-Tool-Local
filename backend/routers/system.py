"""Systemstatus: Ollama, Modelle, Vault-Zustand, lokale Windows-Helfer."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config import APP_ROOT, DATA_DIR, store
from ..deps import current_db, current_ollama, current_profile
from ..ollama_client import OllamaError
from ..vault import VaultError, require_root, vault_stats

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/system", tags=["system"])

# Kleine, gut geeignete Embedding-Modelle für die lokale RAG-Suche.
EMBEDDING_SUGGESTIONS = [
    {"name": "nomic-embed-text", "size": "274 MB", "note": "Guter Allrounder, sehr schnell"},
    {"name": "mxbai-embed-large", "size": "670 MB", "note": "Etwas genauer, mehr Speicherbedarf"},
    {"name": "bge-m3", "size": "1.2 GB", "note": "Stark bei mehrsprachigen Texten (DE/EN)"},
]


@router.get("/status")
async def status() -> Dict[str, Any]:
    """Gesamtstatus für Dashboard und Statusleiste. Wirft bewusst keine Fehler."""
    profile = current_profile()
    client = current_ollama(profile)
    health = await client.health()

    models: list = []
    model_info: Optional[dict] = None
    model_installed = False
    if health.get("online"):
        try:
            models = await client.list_models()
            names = {m["name"] for m in models}
            wanted = profile.ollama.chat_model
            model_installed = wanted in names or f"{wanted}:latest" in names
            if model_installed:
                try:
                    model_info = await client.show(wanted)
                except OllamaError:
                    model_info = None
        except OllamaError as exc:
            log.info("Modelliste nicht abrufbar: %s", exc.message)

    embed_installed = False
    if models:
        names = {m["name"] for m in models}
        embed = profile.ollama.embed_model
        embed_installed = bool(embed) and (embed in names or f"{embed}:latest" in names)

    vault_state: Dict[str, Any] = {"configured": bool(profile.vault.path),
                                   "path": profile.vault.path, "ok": False, "error": ""}
    try:
        root = require_root(profile.vault_path)
        vault_state.update(ok=True, name=root.name)
    except VaultError as exc:
        vault_state["error"] = str(exc)

    database = current_db(profile)
    return {
        "profile": {"id": profile.id, "name": profile.name},
        "profiles": [{"id": p.id, "name": p.name} for p in store.config.profiles],
        "ollama": {
            "online": health.get("online", False),
            "version": health.get("version", ""),
            "base_url": profile.ollama.base_url,
            "error": health.get("error", ""),
        },
        "model": {
            "name": profile.ollama.chat_model,
            "installed": model_installed,
            "info": model_info,
            "vision": bool(model_info and "vision" in (model_info.get("capabilities") or [])),
            "thinking": bool(model_info and "thinking" in (model_info.get("capabilities") or [])),
        },
        "embedding": {"name": profile.ollama.embed_model, "installed": embed_installed},
        "models": models,
        "vault": vault_state,
        "paths": {"app_root": str(APP_ROOT), "data_dir": str(DATA_DIR)},
        "ai": {"thinking": bool(profile.ai.thinking),
               "preview_writes": profile.ai.preview_writes, "source_notes": profile.ai.source_notes,
               "separate_vision": profile.ai.separate_vision, "vision_model": profile.ollama.vision_model},
        "privacy": profile.privacy.model_dump(),
        "ui": store.config.ui.model_dump(),
        "counts": {"chats": database.count("chats"), "messages": database.count("messages")},
    }


@router.get("/models")
async def models() -> Dict[str, Any]:
    client = current_ollama()
    try:
        return {"models": await client.list_models(), "suggestions": EMBEDDING_SUGGESTIONS}
    except OllamaError as exc:
        raise HTTPException(exc.status, {"message": exc.message, "kind": exc.kind}) from exc


@router.get("/model-info")
async def model_info(name: str) -> Dict[str, Any]:
    client = current_ollama()
    try:
        return await client.show(name)
    except OllamaError as exc:
        raise HTTPException(exc.status, {"message": exc.message, "kind": exc.kind}) from exc


class PullRequest(BaseModel):
    model: str


@router.post("/pull")
async def pull(request: PullRequest) -> StreamingResponse:
    """Lädt ein Modell über Ollama. Wird immer bewusst vom Benutzer ausgelöst."""
    client = current_ollama()

    async def event_stream():
        try:
            async for chunk in client.pull_stream(request.model):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'status': 'success', 'done': True})}\n\n"
        except OllamaError as exc:
            yield f"data: {json.dumps({'error': exc.message, 'kind': exc.kind})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/start-ollama")
async def start_ollama() -> Dict[str, Any]:
    """Versucht, den lokalen Ollama-Dienst zu starten (nur Windows/lokal)."""
    profile = current_profile()
    client = current_ollama(profile)
    if (await client.health()).get("online"):
        return {"started": False, "online": True, "message": "Ollama läuft bereits."}

    executable = _find_ollama()
    if not executable:
        raise HTTPException(404, {
            "message": "ollama.exe wurde nicht gefunden. Bitte Ollama manuell starten.",
            "kind": "not_found"})

    try:
        creationflags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        subprocess.Popen([executable, "serve"], creationflags=creationflags,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        raise HTTPException(500, {"message": f"Start fehlgeschlagen: {exc}", "kind": "error"}) from exc

    for _ in range(15):  # bis zu ~7,5 s auf den Dienst warten
        await asyncio.sleep(0.5)
        if (await client.health()).get("online"):
            return {"started": True, "online": True, "message": "Ollama wurde gestartet."}
    return {"started": True, "online": False,
            "message": "Ollama wurde gestartet, antwortet aber noch nicht. Bitte kurz warten."}


def _find_ollama() -> Optional[str]:
    found = shutil.which("ollama")
    if found:
        return found
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Ollama" / "ollama.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


@router.post("/browse-folder")
async def browse_folder() -> Dict[str, Any]:
    """Öffnet den nativen Windows-Ordnerdialog (läuft lokal im Backend)."""
    path = await asyncio.to_thread(_pick_folder)
    if not path:
        return {"path": "", "cancelled": True}
    return {"path": path, "cancelled": False}


def _pick_folder() -> str:
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError:
        raise HTTPException(501, {
            "message": "Der Ordnerdialog ist nicht verfügbar (tkinter fehlt). "
                       "Bitte den Pfad manuell eintragen.",
            "kind": "no_dialog"})
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(title="Vault- bzw. Ordner auswählen")
    finally:
        root.destroy()
    return str(Path(selected)) if selected else ""


class RevealRequest(BaseModel):
    path: str = ""


@router.post("/reveal")
async def reveal(request: RevealRequest) -> Dict[str, Any]:
    """Zeigt eine Vault-Datei im Windows Explorer an."""
    from ..vault import safe_join

    profile = current_profile()
    try:
        root = require_root(profile.vault_path)
        target = safe_join(root, request.path) if request.path else root
    except VaultError as exc:
        raise HTTPException(400, {"message": str(exc), "kind": "vault"}) from exc
    if not target.exists():
        raise HTTPException(404, {"message": "Datei nicht gefunden.", "kind": "not_found"})

    if sys.platform == "win32":
        if target.is_dir():
            os.startfile(str(target))  # noqa: S606 - lokal gewollt
        else:
            subprocess.Popen(["explorer", "/select,", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target.parent)])
    return {"ok": True}


@router.get("/stats")
async def stats() -> Dict[str, Any]:
    """Zählt Notizen, Dokumente und Bilder im Vault (für das Dashboard)."""
    profile = current_profile()
    try:
        root = require_root(profile.vault_path)
    except VaultError as exc:
        raise HTTPException(409, {"message": str(exc), "kind": "no_vault"}) from exc
    return await asyncio.to_thread(vault_stats, root)
