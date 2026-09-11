"""Vault-Zugriff: sichere Pfadauflösung, Ordnerbaum, Datei-Lesen/Schreiben.

Sicherheitsgrundsatz: Es wird ausschließlich innerhalb der freigegebenen
Vault-Wurzel gearbeitet. Jeder Pfad wird aufgelöst und gegen die Wurzel geprüft,
bevor irgendetwas gelesen oder geschrieben wird.
"""
from __future__ import annotations

import ntpath
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable, List, Optional

# Ordner, die nie im Baum auftauchen (Obsidian-Interna, VCS, Papierkorb).
IGNORED_DIRS = {
    ".obsidian", ".git", ".svn", ".hg", ".trash", ".idea", ".vscode",
    "__pycache__", "node_modules", ".DS_Store", ".stfolder", ".stversions",
}

NOTE_EXT = {".md", ".markdown"}
TEXT_EXT = {".txt", ".json", ".csv", ".tsv", ".yaml", ".yml", ".xml", ".ini",
            ".cfg", ".toml", ".log", ".srt", ".rst"}
CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".html", ".htm",
            ".css", ".scss", ".java", ".cs", ".cpp", ".cc", ".c", ".h", ".hpp",
            ".go", ".rs", ".rb", ".php", ".sh", ".bash", ".ps1", ".psm1", ".sql",
            ".bat", ".cmd", ".lua", ".r", ".swift", ".kt", ".vue", ".svelte"}
DOC_EXT = {".pdf", ".docx", ".doc", ".rtf", ".odt", ".pptx", ".xlsx", ".epub"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".svg"}

SUPPORTED_EXT = NOTE_EXT | TEXT_EXT | CODE_EXT | DOC_EXT | IMAGE_EXT

# Obergrenze für das Einlesen von Textdateien in den Editor.
MAX_TEXT_BYTES = 4 * 1024 * 1024


class VaultError(Exception):
    """Fehler bei Vault-Zugriffen (ungültiger Pfad, kein Vault gesetzt, ...)."""


def kind_for(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in NOTE_EXT:
        return "note"
    if ext in IMAGE_EXT:
        return "image"
    if ext in DOC_EXT:
        return "doc"
    if ext in CODE_EXT:
        return "code"
    if ext in TEXT_EXT:
        return "text"
    return "other"


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXT


def _normcase(path: Path) -> str:
    return os.path.normcase(os.path.realpath(str(path)))


def require_root(vault_path: Optional[Path]) -> Path:
    """Stellt sicher, dass ein gültiger Vault konfiguriert und erreichbar ist."""
    if vault_path is None or not str(vault_path):
        raise VaultError("Es ist kein Vault konfiguriert.")
    if not vault_path.exists():
        raise VaultError(f"Der Vault-Pfad existiert nicht: {vault_path}")
    if not vault_path.is_dir():
        raise VaultError(f"Der Vault-Pfad ist kein Ordner: {vault_path}")
    return vault_path


def safe_join(root: Path, relative: str) -> Path:
    """Löst einen relativen Vault-Pfad auf und verhindert Ausbrüche aus der Wurzel."""
    rel = (relative or "").replace("\\", "/")
    if rel.startswith("/"):
        raise VaultError(f"Absoluter Pfad ist nicht erlaubt: {relative}")
    rel = rel.rstrip("/")
    if not rel:
        return root
    # Laufwerksangaben ("C:/..." oder "C:...") früh abweisen: pathlib würde sie
    # unter Windows je nach Laufwerk unterschiedlich behandeln.
    if ntpath.splitdrive(rel)[0] or ":" in rel:
        raise VaultError(f"Ungültiger Pfad: {relative}")
    candidate = PurePosixPath(rel)
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        raise VaultError(f"Ungültiger Pfad: {relative}")
    target = (root / Path(*candidate.parts))
    root_real = _normcase(root)
    target_real = _normcase(target)
    if target_real != root_real and not target_real.startswith(root_real + os.sep):
        raise VaultError(f"Pfad liegt außerhalb des Vaults: {relative}")
    return target


def to_relative(root: Path, path: Path) -> str:
    """Vault-relativer Pfad mit Forward-Slashes (plattformunabhängig speicherbar)."""
    try:
        rel = os.path.relpath(str(path), str(root))
    except ValueError as exc:  # z. B. anderes Laufwerk
        raise VaultError(str(exc)) from exc
    if rel == ".":
        return ""
    if rel.startswith(".."):
        raise VaultError("Pfad liegt außerhalb des Vaults.")
    return rel.replace("\\", "/")


def _mtime_iso(entry: os.DirEntry | Path) -> str:
    try:
        stat = entry.stat()
    except OSError:
        return ""
    return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()


@dataclass
class TreeNode:
    name: str
    path: str
    type: str  # "dir" | "file"
    kind: str = ""
    size: int = 0
    modified: str = ""
    children: Optional[List["TreeNode"]] = None

    def to_dict(self) -> dict:
        out = {
            "name": self.name,
            "path": self.path,
            "type": self.type,
            "kind": self.kind,
            "size": self.size,
            "modified": self.modified,
        }
        if self.children is not None:
            out["children"] = [c.to_dict() for c in self.children]
        return out


def list_dir(root: Path, relative: str = "", include_unsupported: bool = False) -> List[TreeNode]:
    """Ein Verzeichnis auflisten (Ordner zuerst, dann Dateien, jeweils alphabetisch)."""
    target = safe_join(root, relative)
    if not target.is_dir():
        raise VaultError(f"Kein Ordner: {relative}")

    dirs: List[TreeNode] = []
    files: List[TreeNode] = []
    try:
        entries = list(os.scandir(target))
    except OSError as exc:
        raise VaultError(f"Ordner nicht lesbar: {exc}") from exc

    for entry in entries:
        name = entry.name
        if name.startswith(".") or name in IGNORED_DIRS:
            continue
        rel = f"{relative.strip('/')}/{name}".strip("/")
        try:
            if entry.is_dir(follow_symlinks=False):
                dirs.append(TreeNode(name=name, path=rel, type="dir", children=None))
            elif entry.is_file(follow_symlinks=False):
                p = Path(entry.path)
                if not include_unsupported and not is_supported(p):
                    continue
                files.append(TreeNode(
                    name=name, path=rel, type="file", kind=kind_for(p),
                    size=entry.stat().st_size, modified=_mtime_iso(entry),
                ))
        except OSError:
            continue

    dirs.sort(key=lambda n: n.name.lower())
    files.sort(key=lambda n: n.name.lower())
    return dirs + files


def build_tree(root: Path, relative: str = "", max_depth: int = 2) -> List[TreeNode]:
    """Baum bis zu einer bestimmten Tiefe; tiefer wird bei Bedarf nachgeladen."""
    nodes = list_dir(root, relative)
    if max_depth > 1:
        for node in nodes:
            if node.type == "dir":
                try:
                    node.children = build_tree(root, node.path, max_depth - 1)
                except VaultError:
                    node.children = []
    return nodes


def iter_files(root: Path, kinds: Optional[Iterable[str]] = None) -> Iterable[Path]:
    """Rekursiv alle unterstützten Dateien des Vaults (ignorierte Ordner ausgelassen)."""
    wanted = set(kinds) if kinds else None
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in IGNORED_DIRS]
        for filename in filenames:
            if filename.startswith("."):
                continue
            path = Path(dirpath) / filename
            if path.is_symlink():
                continue
            if not is_supported(path):
                continue
            if wanted and kind_for(path) not in wanted:
                continue
            yield path


def read_text_file(root: Path, relative: str) -> dict:
    """Textdatei aus dem Vault lesen (mit Encoding-Fallback)."""
    target = safe_join(root, relative)
    if not target.is_file():
        raise VaultError(f"Datei nicht gefunden: {relative}")
    size = target.stat().st_size
    if size > MAX_TEXT_BYTES:
        raise VaultError(f"Datei ist zu groß für den Editor ({size // 1024} KB).")
    data = target.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            content = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise VaultError("Datei konnte nicht als Text gelesen werden.")
    return {
        "path": to_relative(root, target),
        "name": target.name,
        "kind": kind_for(target),
        "size": size,
        "modified": _mtime_iso(target),
        "content": content,
    }


def write_text_file(root: Path, relative: str, content: str, overwrite: bool = True) -> dict:
    """Textdatei im Vault speichern. Schreibt immer UTF-8 (Obsidian-kompatibel)."""
    target = safe_join(root, relative)
    if target.exists() and not overwrite:
        raise FileExistsError(to_relative(root, target))
    if target.is_dir():
        raise VaultError(f"Pfad ist ein Ordner: {relative}")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Atomar schreiben, damit Obsidian nie eine halbe Datei sieht.
    tmp = target.with_name(target.name + ".tmp-lka")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(target)
    return {
        "path": to_relative(root, target),
        "name": target.name,
        "size": target.stat().st_size,
        "modified": _mtime_iso(target),
    }


def create_dir(root: Path, relative: str) -> dict:
    target = safe_join(root, relative)
    target.mkdir(parents=True, exist_ok=True)
    return {"path": to_relative(root, target), "name": target.name, "type": "dir"}


def rename_entry(root: Path, relative: str, new_name: str) -> dict:
    """Datei/Ordner umbenennen (nur innerhalb des gleichen Ordners)."""
    if not new_name or any(ch in new_name for ch in '\\/:*?"<>|'):
        raise VaultError(f"Ungültiger Name: {new_name}")
    source = safe_join(root, relative)
    if not source.exists():
        raise VaultError(f"Nicht gefunden: {relative}")
    target = safe_join(root, to_relative(root, source.parent) + "/" + new_name)
    if target.exists():
        raise FileExistsError(to_relative(root, target))
    source.rename(target)
    return {"path": to_relative(root, target), "name": target.name}


def move_entry(root: Path, relative: str, target_dir: str) -> dict:
    source = safe_join(root, relative)
    if not source.exists():
        raise VaultError(f"Nicht gefunden: {relative}")
    dest_dir = safe_join(root, target_dir)
    source_real = _normcase(source)
    dest_real = _normcase(dest_dir)
    if source.is_dir() and (dest_real == source_real or dest_real.startswith(source_real + os.sep)):
        raise VaultError("Ein Ordner kann nicht in sich selbst verschoben werden.")
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / source.name
    if target.exists():
        raise FileExistsError(to_relative(root, target))
    shutil.move(str(source), str(target))
    return {"path": to_relative(root, target), "name": target.name}


def delete_entry(root: Path, relative: str) -> dict:
    """Löschen — wird ausschließlich nach ausdrücklicher Bestätigung aufgerufen."""
    target = safe_join(root, relative)
    if target == root:
        raise VaultError("Die Vault-Wurzel kann nicht gelöscht werden.")
    if not target.exists():
        raise VaultError(f"Nicht gefunden: {relative}")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"path": relative, "deleted": True}


def unique_path(root: Path, relative: str) -> str:
    """Freien Dateinamen finden: 'Notiz.md' -> 'Notiz 2.md' -> 'Notiz 3.md'."""
    target = safe_join(root, relative)
    if not target.exists():
        return to_relative(root, target)
    stem, suffix = target.stem, target.suffix
    counter = 2
    while True:
        candidate = target.with_name(f"{stem} {counter}{suffix}")
        if not candidate.exists():
            return to_relative(root, candidate)
        counter += 1


def vault_stats(root: Path) -> dict:
    """Kennzahlen für das Dashboard."""
    counts = {"note": 0, "doc": 0, "image": 0, "text": 0, "code": 0, "other": 0}
    total_bytes = 0
    for path in iter_files(root):
        counts[kind_for(path)] = counts.get(kind_for(path), 0) + 1
        try:
            total_bytes += path.stat().st_size
        except OSError:
            pass
    return {"counts": counts, "total_files": sum(counts.values()), "total_bytes": total_bytes}


def recent_files(root: Path, limit: int = 8, kinds: Optional[Iterable[str]] = None) -> List[dict]:
    """Zuletzt geänderte Dateien — Basis für 'Zuletzt bearbeitet' im Dashboard."""
    items: List[tuple[float, Path]] = []
    for path in iter_files(root, kinds=kinds):
        try:
            items.append((path.stat().st_mtime, path))
        except OSError:
            continue
    items.sort(key=lambda pair: pair[0], reverse=True)
    out = []
    for mtime, path in items[:limit]:
        out.append({
            "name": path.name,
            "path": to_relative(root, path),
            "kind": kind_for(path),
            "modified": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
        })
    return out
