"""Lokale Obsidian-Vorlagen und automatische Auswahl für Schreibaufträge."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from .config import BUNDLED_TEMPLATES
from .vault import VaultError, safe_join, to_relative


@dataclass(frozen=True)
class NoteTemplate:
    id: str
    name: str
    content: str
    source: str
    path: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "content": self.content,
            "source": self.source, "path": self.path,
        }


RULES = {
    "vokabeln": ("vokabel", "wortschatz", "sprache", "spanisch", "englisch", "französisch"),
    "it-wissen": ("it", "server", "windows", "linux", "azure", "docker", "netzwerk", "code", "fehler"),
    "projekt": ("projekt", "roadmap", "meilenstein", "planung"),
    "meeting": ("meeting", "besprechung", "termin", "protokoll"),
    "lernzettel": ("lernen", "lernzettel", "prüfung", "klausur", "zusammenfassung", "grammatik"),
}


def list_templates(root: Optional[Path] = None, templates_dir: str = "") -> List[NoteTemplate]:
    """Eigene Vault-Vorlagen überschreiben gleichnamige mitgelieferte Vorlagen."""
    found: dict[str, NoteTemplate] = {}
    if BUNDLED_TEMPLATES.is_dir():
        for path in sorted(BUNDLED_TEMPLATES.glob("*.md")):
            template = _read(path, "mitgeliefert", path.name)
            found[template.id] = template

    if root is not None and templates_dir.strip():
        try:
            folder = safe_join(root, templates_dir)
        except VaultError:
            folder = None
        if folder and folder.is_dir():
            for path in sorted(folder.glob("*.md")):
                rel = to_relative(root, path)
                template = _read(path, "vault", rel)
                found[template.id] = template
    return sorted(found.values(), key=lambda item: (item.id != "standard", item.name.lower()))


def select_template(text: str, templates: Iterable[NoteTemplate]) -> Optional[NoteTemplate]:
    items = list(templates)
    if not items:
        return None
    lower = (text or "").lower()
    scores = {
        template.id: sum(1 for word in RULES.get(template.id, ()) if word in lower)
        for template in items
    }
    best = max(items, key=lambda item: scores.get(item.id, 0))
    if scores.get(best.id, 0) > 0:
        return best
    return next((item for item in items if item.id == "standard"), items[0])


def template_instruction(template: Optional[NoteTemplate]) -> str:
    if template is None:
        return ""
    return (
        f"PASSENDE NOTIZVORLAGE: {template.name}\n"
        "Übernimm die sinnvolle Struktur, ersetze alle {{Platzhalter}}, lasse "
        "unpassende Abschnitte weg und ergänze fehlende Abschnitte, wenn die "
        "Anforderung sie braucht. Schreibe keinen Hinweis auf die Vorlage.\n\n"
        + template.content[:5000]
    )


def install_bundled(root: Path, templates_dir: str) -> List[str]:
    """Kopiert fehlende Standardvorlagen in den konfigurierten Vault-Ordner."""
    folder = safe_join(root, templates_dir or "00 Templates")
    folder.mkdir(parents=True, exist_ok=True)
    installed: List[str] = []
    for source in sorted(BUNDLED_TEMPLATES.glob("*.md")):
        target = folder / source.name
        if target.exists():
            continue
        shutil.copy2(source, target)
        installed.append(to_relative(root, target))
    return installed


def _read(path: Path, source: str, display_path: str) -> NoteTemplate:
    content = path.read_text(encoding="utf-8", errors="replace")
    return NoteTemplate(
        id=_slug(path.stem), name=path.stem.replace("-", " ").title(),
        content=content, source=source, path=display_path,
    )


def _slug(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")
