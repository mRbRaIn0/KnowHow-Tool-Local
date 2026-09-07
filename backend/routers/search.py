"""Lokale Volltextsuche über Dateinamen, Notizinhalte und Chatverläufe.

Phase 1 durchsucht Dateinamen, Ordner und Textinhalte direkt im Dateisystem.
Der persistente Index und die semantische Suche folgen in Phase 3.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from ..config import Profile
from ..deps import current_db, current_profile
from ..vault import (
    IGNORED_DIRS, VaultError, kind_for, iter_files, require_root, to_relative,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])

# Inhaltssuche nur in Textdateien und nur bis zu dieser Größe.
CONTENT_KINDS = {"note", "text", "code"}
MAX_CONTENT_BYTES = 1_500_000
SNIPPET_RADIUS = 70


@router.get("")
async def search(q: str = "", limit: int = 40) -> Dict[str, Any]:
    term = (q or "").strip()
    if len(term) < 2:
        return _empty(term)

    profile = current_profile()
    database = current_db(profile)
    limit = max(5, min(limit, 200))

    groups: Dict[str, List[dict]] = {
        "notes": [], "documents": [], "images": [], "folders": [], "chats": [],
    }

    try:
        root = require_root(profile.vault_path)
        file_hits = await asyncio.to_thread(_search_vault, root, term, limit)
        groups.update(file_hits)
    except VaultError as exc:
        log.info("Suche ohne Vault: %s", exc)

    for message in database.search_messages(term, limit):
        groups["chats"].append({
            "chat_id": message["chat_id"],
            "chat_title": message["chat_title"],
            "role": message["role"],
            "snippet": _snippet(message["content"], term),
            "created_at": message["created_at"],
        })

    if profile.library.enabled:
        from ..library_store import LibraryStore
        library = LibraryStore(profile.model_copy(deep=True), database)
        catalog_hits = await asyncio.to_thread(library.listing, q=term, limit=limit)
        groups["library"] = [{**item, "snippet": item["description"], "kind": "library"}
                             for item in catalog_hits["items"]]

    total = sum(len(items) for items in groups.values())
    return {"query": term, "groups": groups, "total": total}


def _empty(term: str) -> Dict[str, Any]:
    return {"query": term,
            "groups": {"notes": [], "documents": [], "images": [], "folders": [], "chats": []},
            "total": 0}


def _search_vault(root: Path, term: str, limit: int) -> Dict[str, List[dict]]:
    needle = term.lower()
    notes: List[dict] = []
    documents: List[dict] = []
    images: List[dict] = []
    folders: List[dict] = []

    # Ordnernamen
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in IGNORED_DIRS]
        for name in dirnames:
            if needle in name.lower() and len(folders) < limit:
                folders.append({"name": name, "path": to_relative(root, Path(dirpath) / name),
                                "kind": "folder"})

    for path in iter_files(root):
        kind = kind_for(path)
        name_hit = needle in path.name.lower()
        snippet, line_no = "", 0

        if not name_hit and kind in CONTENT_KINDS:
            snippet, line_no = _search_content(path, needle)
            if not snippet:
                continue
        elif not name_hit:
            continue

        item = {
            "name": path.name,
            "path": to_relative(root, path),
            "kind": kind,
            "snippet": snippet,
            "line": line_no,
            "match": "name" if name_hit else "content",
        }
        # Markdown zählt als Notiz, alles andere Lesbare als Dokument.
        target = notes if kind == "note" else images if kind == "image" else documents
        if len(target) < limit:
            target.append(item)

    notes.sort(key=lambda item: (item["match"] != "name", item["path"].lower()))
    return {"notes": notes, "documents": documents, "images": images, "folders": folders}


def _search_content(path: Path, needle: str) -> tuple[str, int]:
    try:
        if path.stat().st_size > MAX_CONTENT_BYTES:
            return "", 0
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "", 0
    lower = text.lower()
    position = lower.find(needle)
    if position < 0:
        return "", 0
    line_no = text.count("\n", 0, position) + 1
    return _snippet_at(text, position, len(needle)), line_no


def _snippet(text: str, term: str) -> str:
    position = (text or "").lower().find(term.lower())
    if position < 0:
        return (text or "")[:160]
    return _snippet_at(text, position, len(term))


def _snippet_at(text: str, position: int, length: int) -> str:
    start = max(0, position - SNIPPET_RADIUS)
    end = min(len(text), position + length + SNIPPET_RADIUS)
    snippet = text[start:end].replace("\n", " ").strip()
    return f"{'…' if start > 0 else ''}{snippet}{'…' if end < len(text) else ''}"
