"""Einstellungen und Profile."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import store
from ..database import registry
from ..ollama_client import LOCAL_HOSTS
from ..vault_guide import ensure_vault_guide
from urllib.parse import urlparse

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings() -> Dict[str, Any]:
    config = store.config
    return {
        "active_profile": config.active_profile,
        "ui": config.ui.model_dump(),
        "server": config.server.model_dump(),
        "profiles": [p.model_dump() for p in config.profiles],
        "profile": store.active_profile().model_dump(),
    }


class ProfilePatch(BaseModel):
    patch: Dict[str, Any]


@router.patch("/profile/{profile_id}")
async def update_profile(profile_id: str, request: ProfilePatch) -> Dict[str, Any]:
    patch = dict(request.patch)

    # Vault-Pfad prüfen, bevor er gespeichert wird — sonst läuft der Nutzer ins Leere.
    vault_patch = patch.get("vault") or {}
    if "path" in vault_patch and vault_patch["path"]:
        candidate = Path(str(vault_patch["path"])).expanduser()
        if not candidate.exists():
            raise HTTPException(400, {"message": f"Der Ordner existiert nicht: {candidate}",
                                      "kind": "no_vault"})
        if not candidate.is_dir():
            raise HTTPException(400, {"message": f"Kein Ordner: {candidate}", "kind": "no_vault"})
        vault_patch["path"] = str(candidate.resolve())
        patch["vault"] = vault_patch
        try:
            await asyncio.to_thread(ensure_vault_guide, candidate.resolve(), True)
        except OSError as exc:
            raise HTTPException(400, {
                "message": (
                    "Der Vault ist lesbar, aber die Hauptdatei '00 Inhalt.md' "
                    f"konnte nicht angelegt werden: {exc}"
                ),
                "kind": "vault",
            }) from exc

    # Im Offline-Modus darf kein entfernter Ollama-Server konfiguriert werden.
    ollama_patch = patch.get("ollama") or {}
    if "base_url" in ollama_patch:
        profile = store.get_profile(profile_id)
        offline = (patch.get("privacy") or {}).get(
            "offline_mode", profile.privacy.offline_mode if profile else True)
        host = (urlparse(str(ollama_patch["base_url"])).hostname or "").lower()
        if offline and host not in LOCAL_HOSTS:
            raise HTTPException(400, {
                "message": "Im Offline-Modus sind nur lokale Ollama-Adressen erlaubt "
                           "(localhost / 127.0.0.1).",
                "kind": "blocked"})

    try:
        profile = store.update_profile(profile_id, patch)
    except KeyError:
        raise HTTPException(404, {"message": "Profil nicht gefunden.", "kind": "not_found"})
    return profile.model_dump()


class UIPatch(BaseModel):
    theme: str


@router.patch("/ui")
async def update_ui(request: UIPatch) -> Dict[str, Any]:
    if request.theme not in ("light", "dark", "system"):
        raise HTTPException(400, {"message": "Unbekanntes Thema.", "kind": "invalid"})
    return store.update_ui({"theme": request.theme}).model_dump()


class ProfileCreate(BaseModel):
    name: str


@router.post("/profiles")
async def create_profile(request: ProfileCreate) -> Dict[str, Any]:
    name = request.name.strip()
    if not name:
        raise HTTPException(400, {"message": "Bitte einen Profilnamen angeben.", "kind": "invalid"})
    return store.add_profile(name).model_dump()


@router.post("/profiles/{profile_id}/activate")
async def activate_profile(profile_id: str) -> Dict[str, Any]:
    try:
        profile = store.set_active_profile(profile_id)
    except KeyError:
        raise HTTPException(404, {"message": "Profil nicht gefunden.", "kind": "not_found"})
    if profile.vault_path is not None and profile.vault_path.is_dir():
        try:
            await asyncio.to_thread(ensure_vault_guide, profile.vault_path, True)
        except OSError as exc:
            log.warning("00 Inhalt für Profil %s konnte nicht gepflegt werden: %s", profile.id, exc)
    log.info("Profil gewechselt: %s", profile.id)
    return profile.model_dump()


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str) -> Dict[str, Any]:
    """Entfernt ein Profil aus der Konfiguration.

    Die Datenbank des Profils bleibt unter data/profiles/<id> liegen — so geht
    kein Chatverlauf verloren, wenn das Profil versehentlich gelöscht wurde.
    """
    try:
        store.delete_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(400, {"message": str(exc), "kind": "invalid"})
    registry.close(profile_id)
    return {"deleted": True, "id": profile_id}
