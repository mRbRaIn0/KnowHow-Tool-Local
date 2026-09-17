"""Zentrale Hauptdatei eines Vaults: Regeln, Navigation und Strukturkontext.

``00 Inhalt.md`` ist bewusst eine normale Obsidian-Notiz. Der Nutzer kann die
Regeln darin bearbeiten; nur der klar markierte Indexblock wird von der App
aktualisiert. Eine bereits vorhandene gleichnamige Datei wird nie durch die
Standardvorlage ersetzt.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

from .vault import IGNORED_DIRS, is_supported, kind_for, safe_join, to_relative, write_text_file


GUIDE_PATH = "00 Inhalt.md"
INDEX_START = "<!-- VAULT-INDEX:START -->"
INDEX_END = "<!-- VAULT-INDEX:END -->"
MAX_CONTEXT_CHARS = 18_000
MAX_INDEX_ENTRIES = 800


def _default_content(index: str) -> str:
    return f"""---
typ: vault-hauptseite
status: aktiv
---

# 00 Inhalt

Diese Seite ist die zentrale Orientierung für diesen Obsidian-Vault. Sie legt
fest, wie die KI Inhalte gestaltet, einsortiert, verknüpft und ergänzt.

## Gestaltungsregeln

- Sprache: Deutsch
- Emojis: Nein
- Überschriften: klar und sachlich
- WikiLinks: Ja
- Metasätze über die Erstellung oder die verwendeten Eingaben: Nein

`Emojis: Ja` erlaubt passende, sparsam eingesetzte Emojis. `Emojis: Nein`
verbietet Emojis in neu erzeugten oder ergänzten Notizen, sofern ein einzelner
Auftrag nicht ausdrücklich etwas anderes verlangt.

## Arbeits- und Quellenregeln

- Bestehende Ordner und Notizen haben Vorrang vor neuen Parallelstrukturen.
- Neue Inhalte werden in den fachlich passendsten vorhandenen Ordner gelegt.
- Eine bestehende Notiz wird nur auf ausdrücklichen Auftrag verändert; ansonsten
  wird sie ergänzt oder eine neue Notiz erstellt.
- Verknüpfungen zwischen Notizen verwenden Obsidian-WikiLinks.
- Verwendete PDFs, Bilder und andere Originaldateien werden im Vault abgelegt.
- PDFs, Bilder und andere Originaldateien liegen in einem Unterordner `Dateien`
  des jeweiligen Themenordners und nicht direkt neben Markdown-Notizen.
- Ein Quellenlink zeigt exakt auf den tatsächlichen Vault-Pfad der Originaldatei.
- Bei mehreren Quellen werden Übereinstimmungen, Ergänzungen und Widersprüche
  fachlich geprüft. Ungeklärte Widersprüche bleiben mit konkretem Quellenlink
  sichtbar.
- Die Notiz enthält keine pauschalen Sätze darüber, dass sie ausschließlich auf
  Anhängen, PDFs, Bildern oder bereitgestellten Dateien basiert.

## Empfohlene Grundordnung

- `00 Inhalt.md`: diese Hauptseite und Navigation
- `00 Templates/`: wiederverwendbare Notizvorlagen
- `01 Wissen/`: dauerhaftes Fach- und Lernwissen
- `02 KI-Notizen/`: sichere Ablage, wenn noch kein eindeutiger Fachordner besteht
- `90 Anhänge/`: allgemeine Originaldateien, sofern kein thematischer Anhangordner
  geeigneter ist

Die Empfehlung erzeugt oder verschiebt keine Ordner automatisch. Die tatsächlich
vorhandene Struktur im folgenden Index ist maßgeblich.

## Vault-Übersicht

Der Inhalt zwischen den Markierungen wird automatisch gepflegt. Eigene Regeln
und Erklärungen außerhalb dieses Blocks bleiben unverändert.

{INDEX_START}
{index}
{INDEX_END}

## Pflege dieser Hauptseite

Änderungen an Regeln, Gestaltung oder Grundordnung können im Chat ausdrücklich
beauftragt werden, zum Beispiel: „Ändere in 00 Inhalt Emojis auf Ja“ oder
„Überarbeite die Grundordnung, aber lass alle anderen Regeln unverändert“.
"""


def ensure_vault_guide(root: Path, create: bool = True, refresh: bool = True) -> Dict[str, object]:
    """Legt die Hauptseite einmalig an und aktualisiert nur ihren Indexblock."""
    target = safe_join(root, GUIDE_PATH)

    if not target.exists():
        if not create:
            return {"path": GUIDE_PATH, "exists": False, "created": False, "updated": False}
        result = write_text_file(root, GUIDE_PATH, _default_content(build_vault_index(root)), overwrite=False)
        return {"path": result["path"], "exists": True, "created": True, "updated": False}

    if not target.is_file():
        return {"path": GUIDE_PATH, "exists": False, "created": False, "updated": False}

    current = target.read_text(encoding="utf-8", errors="replace")
    if not refresh or INDEX_START not in current or INDEX_END not in current:
        return {"path": GUIDE_PATH, "exists": True, "created": False, "updated": False}
    updated = _replace_index(current, build_vault_index(root))
    changed = updated != current
    if changed:
        write_text_file(root, GUIDE_PATH, updated, overwrite=True)
    return {"path": GUIDE_PATH, "exists": True, "created": False, "updated": changed}


def guide_context(root: Path) -> str:
    """Liest die vom Nutzer gestaltbare Hauptseite als maßgeblichen KI-Kontext."""
    target = safe_join(root, GUIDE_PATH)
    if not target.is_file():
        return ""
    content = target.read_text(encoding="utf-8", errors="replace")
    # Der vollständige Index bleibt im Vault. Im Prompt reichen Regeln und
    # kompakte Ordnerübersicht; Regeln NACH dem Index bleiben ebenfalls sichtbar.
    start, end = content.find(INDEX_START), content.find(INDEX_END)
    if 0 <= start < end:
        content = content[:start] + content[end + len(INDEX_END):]
    if len(content) > MAX_CONTEXT_CHARS:
        content = content[:MAX_CONTEXT_CHARS] + "\n\n[Weitere Regeln bei Bedarf mit notiz_lesen laden]"
    return content


def ensure_file_subfolder_rule(root: Path, subfolder: str = "Dateien") -> Dict[str, object]:
    """Hält eine ausdrücklich gewählte Quellenordnung in der Hauptseite fest."""
    target = safe_join(root, GUIDE_PATH)
    if not target.is_file():
        return {"path": GUIDE_PATH, "updated": False}
    content = target.read_text(encoding="utf-8", errors="replace")
    rule = (
        f"- PDFs, Bilder und andere Originaldateien liegen in einem Unterordner "
        f"`{subfolder}` des jeweiligen Themenordners und nicht direkt neben "
        "Markdown-Notizen."
    )
    if rule in content:
        return {"path": GUIDE_PATH, "updated": False}
    if INDEX_START not in content or INDEX_END not in content:
        # Eine vollständig eigene 00-Inhalt-Datei bleibt weiterhin unangetastet.
        return {"path": GUIDE_PATH, "updated": False}

    heading = "## Arbeits- und Quellenregeln"
    start = content.find(heading)
    if start < 0:
        return {"path": GUIDE_PATH, "updated": False}
    next_heading = content.find("\n## ", start + len(heading))
    if next_heading < 0:
        next_heading = len(content)
    before = content[:next_heading].rstrip()
    after = content[next_heading:].lstrip("\n")
    updated = before + "\n" + rule + "\n\n" + after
    write_text_file(root, GUIDE_PATH, updated, overwrite=True)
    return {"path": GUIDE_PATH, "updated": True}


def build_vault_index(root: Path) -> str:
    """Erzeugt eine lesbare Topologie mit echten WikiLinks zu Vault-Dateien."""
    lines: List[str] = []
    entries = 0
    truncated = False

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            (name for name in dirnames if not name.startswith(".") and name not in IGNORED_DIRS),
            key=str.casefold,
        )
        folder = Path(dirpath)
        rel_folder = to_relative(root, folder)
        depth = len(Path(rel_folder).parts) if rel_folder else 0

        if rel_folder:
            if entries >= MAX_INDEX_ENTRIES:
                truncated = True
                break
            lines.append(f"{'  ' * (depth - 1)}- `{rel_folder}/`")
            entries += 1

        for filename in sorted(filenames, key=str.casefold):
            path = folder / filename
            if filename.startswith(".") or filename == GUIDE_PATH or path.is_symlink():
                continue
            if not is_supported(path):
                continue
            if entries >= MAX_INDEX_ENTRIES:
                truncated = True
                break
            rel = to_relative(root, path)
            label = path.name.replace("|", "-")
            if kind_for(path) == "note":
                target = rel.rsplit(".", 1)[0]
                label = path.stem.replace("|", "-")
            else:
                target = rel
            indent = "  " * depth
            lines.append(f"{indent}- [[{target}|{label}]]")
            entries += 1
        if truncated:
            break

    if truncated:
        lines.append(f"- … Index nach {MAX_INDEX_ENTRIES} Einträgen gekürzt")
    if not lines:
        return "- Der Vault enthält außer dieser Hauptseite noch keine Ordner oder Dateien."
    return "\n".join(lines)


def _replace_index(content: str, index: str) -> str:
    start = content.find(INDEX_START)
    end = content.find(INDEX_END)
    if start < 0 or end < 0 or end < start:
        # Eine eigene, bereits vorhandene 00-Inhalt-Datei ohne Markierungen ist
        # vollständig nutzerverwaltet und wird von der App nicht umgeschrieben.
        return content
    before = content[: start + len(INDEX_START)]
    after = content[end:]
    return before.rstrip() + "\n" + index.rstrip() + "\n" + after.lstrip()
