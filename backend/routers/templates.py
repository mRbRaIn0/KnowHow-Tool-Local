"""Obsidian-Notizvorlagen: mitgelieferte und eigene im Vault."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from ..deps import current_profile, current_vault
from ..note_templates import install_bundled, list_templates
from ..vault import VaultError, require_root

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
async def templates() -> Dict[str, Any]:
    profile = current_profile()
    try:
        root = require_root(profile.vault_path)
    except VaultError:
        root = None
    items = list_templates(root, profile.vault.templates_dir)
    return {
        "templates": [item.to_dict() for item in items],
        "directory": profile.vault.templates_dir,
        "vault_ready": root is not None,
    }


@router.post("/install")
async def install() -> Dict[str, Any]:
    profile = current_profile()
    paths = install_bundled(current_vault(), profile.vault.templates_dir)
    return {"installed": paths, "count": len(paths)}
