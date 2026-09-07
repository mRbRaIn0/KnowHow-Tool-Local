"""Strict roots, Windows filename validation and streaming fingerprints."""
from __future__ import annotations

import hashlib
import ntpath
import os
import re
import stat
from pathlib import Path

from .library_models import LibraryError

IGNORED = {".wissens-ki", ".git", ".obsidian", ".trash", "$recycle.bin",
           "system volume information", "__pycache__", "node_modules", ".venv"}


def relative_path(value: str, allow_empty=True) -> str:
    value = value.replace("\\", "/")
    if not value and allow_empty:
        return ""
    if (not value or value.startswith("/") or ntpath.splitdrive(value)[0]
            or any(p in {"", ".", ".."} for p in value.split("/"))):
        raise LibraryError("Nur relative Pfade innerhalb der freigegebenen Quelle sind erlaubt.")
    for part in value.split("/"):
        if (part.endswith((".", " ")) or re.search(r'[<>:"|?*\x00-\x1f]', part)
                or re.match(r"(?i)^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)", part)
                or part.casefold() in IGNORED or part.startswith(".lka-")):
            raise LibraryError(f"Ungültiger oder geschützter Pfadbestandteil: {part}")
    return value


def under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def is_link(path: Path) -> bool:
    try:
        info = path.lstat()
        return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0)
                                       & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except FileNotFoundError:
        return False


def safe_path(root: str | Path, relative: str, vault: Path | None = None) -> Path:
    root = Path(root)
    rel = relative_path(relative)
    if not root.is_dir():
        raise LibraryError("Quelle ist nicht erreichbar. Bestand bleibt gespeichert.")
    if is_link(root):
        raise LibraryError("Symlinks/Junctions sind keine freigegebenen Quellen.")
    path = root
    for part in rel.split("/") if rel else []:
        path = path / part
        if is_link(path):
            raise LibraryError("Symlinks und Junctions werden nicht verfolgt.")
    if not under(path, root):
        raise LibraryError("Pfad verlässt die freigegebene Quelle.")
    if vault and under(path, vault):
        raise LibraryError("Der Obsidian-Vault wird ausschließlich im Vault-Bereich verwaltet.")
    return path


def fingerprint(path: Path) -> dict:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise LibraryError("Keine reguläre Datei.")
    return {"size": info.st_size, "modified_ns": info.st_mtime_ns}


def digest(path: Path, checkpoint=lambda: None) -> str:
    before = fingerprint(path)
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            checkpoint()
            sha.update(block)
    if fingerprint(path) != before:
        raise LibraryError("Datei wurde während des Lesens geändert.")
    return sha.hexdigest()
