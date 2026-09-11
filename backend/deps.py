"""Gemeinsame Abhängigkeiten für die Router: aktives Profil, DB, Ollama, Vault."""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from .config import Profile, store
from .database import Database, registry
from .ollama_client import OllamaClient, OllamaError
from .vault import VaultError, require_root


def current_profile() -> Profile:
    return store.active_profile()


def current_db(profile: Profile | None = None) -> Database:
    profile = profile or current_profile()
    return registry.get(profile.id, profile.db_path)


def current_ollama(profile: Profile | None = None) -> OllamaClient:
    profile = profile or current_profile()
    try:
        return OllamaClient(profile.ollama.base_url, profile.privacy.offline_mode)
    except OllamaError as exc:
        raise HTTPException(status_code=exc.status,
                            detail={"message": exc.message, "kind": exc.kind}) from exc


def current_vault(profile: Profile | None = None) -> Path:
    """Vault-Wurzel des aktiven Profils — oder ein sprechender HTTP-Fehler."""
    profile = profile or current_profile()
    try:
        return require_root(profile.vault_path)
    except VaultError as exc:
        raise HTTPException(status_code=409,
                            detail={"message": str(exc), "kind": "no_vault"}) from exc


def vault_error(exc: Exception, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"message": str(exc), "kind": "vault"})
