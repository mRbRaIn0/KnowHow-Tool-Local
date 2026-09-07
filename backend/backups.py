"""Konsistente lokale ZIP-Backups für Vault, Profil und Chatdatenbank."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .config import DATA_DIR, Profile
from .database import Database


def backup_dir(profile: Profile) -> Path:
    target = DATA_DIR / "backups" / profile.id
    target.mkdir(parents=True, exist_ok=True)
    return target


def create_backup(profile: Profile, root: Path, database: Database) -> Dict[str, Any]:
    stamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S")
    target = backup_dir(profile) / f"{profile.id}_{stamp}.zip"
    counter = 2
    while target.exists():
        target = target.with_name(f"{profile.id}_{stamp}_{counter}.zip")
        counter += 1

    temp = profile.data_dir / f".backup-{uuid.uuid4().hex}"
    temp.mkdir(parents=True)
    try:
        database.backup_to(temp / "app.db")
        (temp / "profile.json").write_text(
            json.dumps(profile.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

        file_count = 0
        backups_root = backup_dir(profile).resolve()
        temporary_root = temp.resolve()
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=True) as archive:
            archive.write(temp / "app.db", "app/app.db")
            archive.write(temp / "profile.json", "app/profile.json")
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                dirnames[:] = [
                    name for name in dirnames
                    if name not in {".git", ".trash", "__pycache__"}
                    and not (Path(dirpath) / name).is_symlink()
                    and (Path(dirpath) / name).resolve() != backups_root
                    and (Path(dirpath) / name).resolve() != temporary_root
                ]
                for filename in filenames:
                    path = Path(dirpath) / filename
                    if path.is_symlink() or path.name.endswith(".tmp-lka"):
                        continue
                    try:
                        relative = path.relative_to(root).as_posix()
                        archive.write(path, f"vault/{relative}")
                        file_count += 1
                    except (OSError, ValueError):
                        continue

            manifest = {
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "profile": profile.id,
                "vault_name": root.name,
                "vault_files": file_count,
                "format": 1,
            }
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(temp, ignore_errors=True)

    return describe_backup(target, file_count=file_count)


def list_backups(profile: Profile) -> List[Dict[str, Any]]:
    items = [describe_backup(path) for path in backup_dir(profile).glob("*.zip") if path.is_file()]
    return sorted(items, key=lambda item: item["modified"], reverse=True)


def resolve_backup(profile: Profile, name: str) -> Path:
    if Path(name).name != name or not name.lower().endswith(".zip"):
        raise FileNotFoundError(name)
    target = backup_dir(profile) / name
    if not target.is_file():
        raise FileNotFoundError(name)
    return target


def describe_backup(path: Path, file_count: int = 0) -> Dict[str, Any]:
    stat = path.stat()
    digest = _sha256(path) if stat.st_size <= 200_000_000 else ""
    return {
        "name": path.name,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        "vault_files": file_count,
        "sha256": digest,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
