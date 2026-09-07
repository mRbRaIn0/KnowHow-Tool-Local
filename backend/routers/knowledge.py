"""Lokaler Wissensindex und hybride RAG-Suche."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from ..deps import current_db, current_ollama, current_profile, current_vault
from ..knowledge import hybrid_search, sync_index

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/status")
async def status() -> Dict[str, Any]:
    profile = current_profile()
    return {
        **current_db(profile).knowledge_stats(),
        "model": profile.ollama.embed_model,
    }


@router.post("/reindex")
async def reindex() -> Dict[str, Any]:
    profile = current_profile()
    return await sync_index(
        current_vault(), current_db(profile), current_ollama(profile),
        profile.ollama.embed_model, force=True,
        excluded_dirs=(profile.vault.templates_dir,),
    )


@router.get("/search")
async def search(q: str, limit: int = 8) -> Dict[str, Any]:
    profile = current_profile()
    return await hybrid_search(
        profile.vault_path, current_db(profile), q, current_ollama(profile),
        profile.ollama.embed_model, max(1, min(limit, 20)),
        excluded_dirs=(profile.vault.templates_dir,),
        refresh=False, include_library=profile.library.enabled,
    )
