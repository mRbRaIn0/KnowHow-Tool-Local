"""Werkzeuge, die das Modell im Vault benutzen darf.

Sicherheitsgrenze: Das Modell ruft ausschließlich diese Funktionen auf. Es
bekommt keine Shell und keinen freien Dateisystemzugriff. Standardmäßig kann es
nur neu anlegen oder anhängen. Eine bestehende Notiz darf es ausschließlich bei
einem ausdrücklich erkannten Änderungsauftrag und nur über die geschützten
Bearbeitungsmodi verändern. Löschen bleibt dem Menschen im Editor vorbehalten.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import posixpath
import re
import shutil
import time
from urllib.parse import unquote
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from . import attachments
from .attachments import AttachmentError
from .text_cache import read_search_text
from .vault import (
    DOC_EXT, IGNORED_DIRS, IMAGE_EXT, VaultError, iter_files, kind_for, list_dir,
    create_unique_file, read_text_file, safe_join, to_relative, unique_path, write_text_file,
)
from .vault_guide import ensure_file_subfolder_rule, ensure_vault_guide
from .workflow import ActionRequirements, note_title
from .vault_actions import vault_io

log = logging.getLogger(__name__)

MAX_READ_CHARS = 6000       # so viel Notiztext bekommt das Modell je Datei
MAX_SEARCH_HITS = 8
SNIPPET_RADIUS = 220


# --------------------------------------------------------------- Definitionen

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "vault_suchen",
            "description": (
                "Durchsucht den Wissens-Vault des Nutzers nach Notizen, Dokumenten "
                "und Dateien. Einmal gezielt suchen, wenn relevantes Wissen oder der "
                "Zielpfad noch unbekannt sind. Bereits bereitgestellte Treffer nutzen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "suchbegriff": {
                        "type": "string",
                        "description": "Ein oder zwei Stichworte, z. B. 'Azure Arc' oder 'Docker'.",
                    }
                },
                "required": ["suchbegriff"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notiz_lesen",
            "description": (
                "Liest den Inhalt einer Datei aus dem Vault. Vor dem Ergänzen einer "
                "Notiz immer erst lesen, um Struktur und vorhandene Inhalte zu kennen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pfad": {
                        "type": "string",
                        "description": "Vault-relativer Pfad, z. B. '01 Wissen/Azure/Azure Arc.md'.",
                    },
                    "offset": {"type": "integer", "description": "Zeichenposition, zuerst 0; bei langen Dateien naechster_offset verwenden."},
                    "limit": {"type": "integer", "description": "Maximal 6000 Zeichen pro Aufruf."}
                },
                "required": ["pfad"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ordner_auflisten",
            "description": (
                "Zeigt den Inhalt eines Ordners im Vault. Nützlich, um den richtigen "
                "Ablageort für eine neue Notiz zu finden."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pfad": {
                        "type": "string",
                        "description": "Vault-relativer Ordner. Leer lassen für die oberste Ebene.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notiz_erstellen",
            "description": (
                "Legt eine NEUE Markdown-Notiz im Vault an. Nutze das, wenn der Nutzer "
                "um eine Notiz, Dokumentation oder Zusammenfassung bittet. Der Inhalt "
                "muss vollständiges Markdown sein — beschreibe die Notiz nicht nur, "
                "sondern schreibe sie. Bestehende Dateien werden nie überschrieben."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pfad": {
                        "type": "string",
                        "description": (
                            "Vault-relativer Zielpfad mit Endung .md, "
                            "z. B. '01 Wissen/Azure/Azure Arc.md'."
                        ),
                    },
                    "inhalt": {
                        "type": "string",
                        "description": "Der vollständige Markdown-Inhalt der Notiz.",
                    },
                },
                "required": ["pfad", "inhalt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notiz_ergaenzen",
            "description": (
                "Hängt Text an eine bestehende Notiz an, ohne vorhandene Inhalte zu "
                "verändern. Nutze das zum Erweitern und Dokumentieren. Optional kann "
                "der Text unter einer bestimmten Überschrift eingefügt werden."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pfad": {"type": "string", "description": "Vault-relativer Pfad der Notiz."},
                    "inhalt": {"type": "string", "description": "Der anzuhängende Markdown-Text."},
                    "abschnitt": {
                        "type": "string",
                        "description": (
                            "Optional: Überschrift, unter der eingefügt wird, "
                            "z. B. 'Inhalt'. Fehlt sie, wird ans Ende angehängt."
                        ),
                    },
                },
                "required": ["pfad", "inhalt"],
            },
        },
    },
]

# Bestehende Inhalte dürfen nur bei einer ausdrücklich erkannten Änderungsabsicht
# bearbeitet werden. Deshalb wird diese Definition pro Anfrage separat ergänzt.
EDIT_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "notiz_bearbeiten",
            "description": (
                "Bearbeitet eine BESTEHENDE Notiz, wenn der Nutzer die Änderung "
                "ausdrücklich verlangt hat. Vorher zwingend notiz_lesen aufrufen. "
                "Ändere mit text_ersetzen genau eine Textstelle, mit "
                "abschnitt_ersetzen nur den Inhalt einer Überschrift oder mit "
                "vollstaendig_neustrukturieren die ganze Notiz, falls der Nutzer "
                "ausdrücklich eine neue Struktur/ein neues Design verlangt. "
                "Nicht betroffene Inhalte und Metadaten müssen erhalten bleiben."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pfad": {
                        "type": "string",
                        "description": "Vault-relativer Pfad der zuvor gelesenen Notiz.",
                    },
                    "modus": {
                        "type": "string",
                        "enum": [
                            "text_ersetzen", "abschnitt_ersetzen",
                            "vollstaendig_neustrukturieren",
                        ],
                    },
                    "alter_text": {
                        "type": "string",
                        "description": (
                            "Nur bei text_ersetzen: der exakte, genau einmal "
                            "vorkommende bisherige Text."
                        ),
                    },
                    "abschnitt": {
                        "type": "string",
                        "description": (
                            "Nur bei abschnitt_ersetzen: Überschrift des zu "
                            "ersetzenden Abschnitts, ohne #-Zeichen."
                        ),
                    },
                    "neuer_inhalt": {
                        "type": "string",
                        "description": (
                            "Neuer Text, neuer Abschnittsinhalt oder bei vollständiger "
                            "Neustrukturierung der komplette neue Markdown-Inhalt."
                        ),
                    },
                    "grund": {
                        "type": "string",
                        "description": "Kurze Begründung, welche Nutzeranforderung umgesetzt wird.",
                    },
                },
                "required": ["pfad", "modus", "neuer_inhalt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "markdown_dateien_bereinigen",
            "description": (
                "Bearbeitet in EINEM kontrollierten Stapel wirklich ALLE Markdown-"
                "Dateien des Vaults. Nur verwenden, wenn der Nutzer ausdrücklich alle "
                "Dateien beziehungsweise den gesamten Vault genannt hat. Das Werkzeug "
                "liest jede Markdown-Datei selbst, entfernt auf Wunsch Emojis und/oder "
                "wandelt relative Markdown- und WikiLinks in vollständige, vorhandene "
                "Obsidian-WikiLinks um. Suchtreffer begrenzen den Stapel nicht."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operationen": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["remove_emojis", "fix_relative_links"],
                        },
                        "description": "Nur die ausdrücklich vom Nutzer verlangten Operationen.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dateien_in_unterordner_verschieben",
            "description": (
                "Verschiebt vaultweit vorhandene PDFs, Dokumente und Bilder, die "
                "direkt neben Markdown-Notizen liegen, in einen Unterordner desselben "
                "Themenordners. Aktualisiert anschließend alle betroffenen Markdown- "
                "und WikiLinks auf die neuen tatsächlichen Vault-Pfade. Nur verwenden, "
                "wenn der Nutzer diese Dateiordnung ausdrücklich verlangt hat."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "unterordner": {
                        "type": "string",
                        "description": (
                            "Ein einfacher Ordnername ohne Pfadbestandteile. "
                            "Standard und empfohlener Wert: 'Dateien'."
                        ),
                    }
                },
            },
        },
    },
]

# Werkzeuge für angehängte Dateien — nur aktiv, wenn welche vorliegen.
ATTACHMENT_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "anhang_lesen",
            "description": (
                "Liest den Textinhalt einer angehängten Datei (Markdown, Text, "
                "Quellcode, PDF, DOCX, CSV) sowie gespeicherte Bildauswertungen. "
                "Liefert naechster_offset: damit alle weiteren Teile abrufen, bis null."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Dateiname des Anhangs."},
                    "offset": {"type": "integer", "description": "Zeichenposition; zuerst 0, dann naechster_offset."},
                    "limit": {"type": "integer", "description": "Zeichen pro Teil, maximal 12000."},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bild_ansehen",
            "description": (
                "Sieht sich ein angehängtes Bild an und beschreibt, was darauf zu sehen "
                "ist. Für Screenshots, Fotos, Diagramme und abfotografierte Blätter. "
                "Stelle über 'frage' genau das, was du wissen willst — etwa 'Lies den "
                "gesamten Text ab' oder 'Gib die Tabelle als Markdown wieder'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Dateiname des Bildes."},
                    "frage": {
                        "type": "string",
                        "description": "Was soll am Bild ermittelt werden?",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "anhang_in_vault_ablegen",
            "description": (
                "Kopiert eine angehängte Datei in den Vault und gibt den Vault-Pfad "
                "zurück, mit dem du sie in einer Notiz einbetten kannst. Nutze das, "
                "wenn der Nutzer Dateien einsortieren, ablegen oder in seine "
                "Dokumentation aufnehmen möchte. Das Original bleibt erhalten."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Dateiname des Anhangs."},
                    "zielordner": {
                        "type": "string",
                        "description": (
                            "Vault-relativer Zielordner, z. B. '99 Bilder' oder "
                            "'90 Dokumente'. Leer lassen für den Standard-Anhangordner."
                        ),
                    },
                    "neuer_name": {
                        "type": "string",
                        "description": (
                            "Optional: sprechender Dateiname OHNE Endung. "
                            "Die Dateiendung des Originals bleibt immer erhalten."
                        ),
                    },
                },
                "required": ["name"],
            },
        },
    },
]

# Werkzeuge, die etwas schreiben — die Oberfläche hebt sie hervor.
WRITING_TOOLS = {
    "notiz_erstellen", "notiz_ergaenzen", "notiz_bearbeiten",
    "markdown_dateien_bereinigen", "dateien_in_unterordner_verschieben",
    "anhang_in_vault_ablegen",
}

TOOL_ALIASES = {
    # Kleine lokale Modelle vertauschen bei diesem deutschen Namen gelegentlich
    # den letzten Konsonanten. Der Auftrag darf daran nicht scheitern.
    "notiz_ergaetzen": "notiz_ergaenzen",
    "notiz_erganzen": "notiz_ergaenzen",
}


def canonical_tool_name(name: str) -> str:
    value = (name or "").strip()
    return TOOL_ALIASES.get(value, value)


# ------------------------------------------------------------------ Ausführung

class ToolRunner:
    """Führt Werkzeugaufrufe innerhalb genau eines Vaults aus."""

    def __init__(self, root: Path, chat_id: str = "", attachment_dir: str = "",
                 vision: Optional[Callable] = None, allow_edit: bool = False,
                 allow_full_rewrite: bool = False,
                 batch_edit_operations: Iterable[str] = (),
                 allow_file_organization: bool = False, defer_guide: bool = False,
                 preview_writes: bool = False, focus=None):
        self.root = root
        self.defer_guide = defer_guide
        self.preview_writes = preview_writes
        self.approved_previews = {}
        self.focus = focus
        self.chat_id = chat_id
        self.attachment_dir = attachment_dir or "90 Anhänge"
        self.vision = vision            # async Rückruf für die Bildanalyse
        self.allow_edit = allow_edit
        self.allow_full_rewrite = allow_full_rewrite
        self.batch_edit_operations = tuple(
            item for item in batch_edit_operations
            if item in {"remove_emojis", "fix_relative_links"}
        )
        self.allow_batch_edit = bool(self.allow_edit and self.batch_edit_operations)
        self.batch_edit_done = False
        self.completed_batch_operations: set[str] = set()
        self.allow_file_organization = allow_file_organization
        self.file_organization_done = False
        self.changed_files: List[str] = []
        self.note_files: List[str] = []
        self.read_notes: List[str] = []
        self.read_ranges = {}
        self.edited_notes: List[str] = []
        self.stored_attachments: Dict[str, Dict[str, str]] = {}

    def _changed(self, path: str) -> None:
        if path not in self.changed_files:
            self.changed_files.append(path)

    def refresh_guide(self) -> None:
        if self.changed_files:
            ensure_vault_guide(self.root, create=False)

    def _refresh_guide(self) -> None:
        if not self.defer_guide:
            self.refresh_guide()

    async def run(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Gibt immer ein Ergebnis zurück — Fehler werden dem Modell mitgeteilt."""
        name = canonical_tool_name(name)
        handler: Optional[Callable[..., Dict[str, Any]]] = getattr(self, f"_{name}", None)
        if handler is None:
            return {"fehler": f"Unbekanntes Werkzeug: {name}"}
        try:
            if inspect.iscoroutinefunction(handler):
                return await handler(**_clean(arguments))
            # Dateizugriffe blockieren sonst den Event-Loop.
            return await vault_io(lambda: handler(**_clean(arguments)))
        except (VaultError, AttachmentError) as exc:
            return {"fehler": str(exc)}
        except TypeError as exc:
            return {"fehler": f"Falsche Parameter für {name}: {exc}"}
        except OSError as exc:
            log.warning("Werkzeug %s fehlgeschlagen: %s", name, exc)
            return {"fehler": f"Dateizugriff fehlgeschlagen: {exc}"}

    # -------------------------------------------------------------- Lesen

    def _vault_suchen(self, suchbegriff: str = "", **_: Any) -> Dict[str, Any]:
        term = (suchbegriff or "").strip().lower()
        if len(term) < 2:
            return {"fehler": "Der Suchbegriff ist zu kurz."}

        treffer: List[Dict[str, Any]] = []
        paths = sorted(self.focus.files(self.root) if self.focus else iter_files(self.root), key=lambda path: (
            term not in to_relative(self.root, path).lower(),
            to_relative(self.root, path).lower(),
        ))
        for path in paths:
            if len(treffer) >= MAX_SEARCH_HITS:
                break
            rel = to_relative(self.root, path)
            name_hit = term in path.name.lower() or term in rel.lower()
            auszug = ""
            if kind_for(path) in ("note", "text", "code"):
                try:
                    text, lower = read_search_text(path)
                except OSError:
                    text, lower = "", ""
                position = lower.find(term)
                if position >= 0:
                    start = max(0, position - SNIPPET_RADIUS)
                    auszug = text[start:position + SNIPPET_RADIUS].strip()
                elif not name_hit:
                    continue
            elif not name_hit:
                continue
            treffer.append({"pfad": rel, "typ": kind_for(path), "auszug": auszug})

        if not treffer:
            return {"treffer": [], "hinweis": f"Zu '{suchbegriff}' gibt es im Vault noch nichts."}
        return {"treffer": treffer, "anzahl": len(treffer)}

    def _notiz_lesen(self, pfad: str = "", offset: int = 0, limit: int = MAX_READ_CHARS, **_: Any) -> Dict[str, Any]:
        if self.focus and not self.focus.allows(pfad) and pfad not in self.changed_files:
            return {'fehler': 'Datei liegt außerhalb der erwähnten Ziele. Bitte den konkreten Pfad vom Nutzer nennen lassen.'}
        data = read_text_file(self.root, pfad)
        inhalt = data["content"]
        offset, limit = max(0, int(offset)), max(1, min(int(limit), MAX_READ_CHARS))
        end = min(len(inhalt), offset + limit)
        gekuerzt = end < len(inhalt)
        ranges = self.read_ranges.setdefault(data['path'], [])
        ranges.append((offset, end))
        covered = 0
        for start, finish in sorted(ranges):
            if start > covered:
                break
            covered = max(covered, finish)
        if covered >= len(inhalt) and data['path'] not in self.read_notes:
            self.read_notes.append(data['path'])
        return {
            "pfad": data["path"],
            "inhalt": inhalt[offset:end],
            "gekuerzt": gekuerzt,
            "naechster_offset": end if gekuerzt else None,
            "gesamtzeichen": len(inhalt),
        }

    def _ordner_auflisten(self, pfad: str = "", **_: Any) -> Dict[str, Any]:
        if self.focus and not self.focus.allows(pfad):
            return {'fehler': 'Ordner liegt außerhalb der erwähnten Ziele.', 'ziele': self.focus.paths or []}
        nodes = list_dir(self.root, pfad or "")
        return {
            "pfad": pfad or "(Vault-Wurzel)",
            "ordner": [n.name for n in nodes if n.type == "dir"],
            "dateien": [n.name for n in nodes if n.type == "file"],
        }

    # ------------------------------------------------------------ Schreiben

    def _review_note(self, path: str, content: str, create: bool = False):
        if not self.preview_writes:
            return path, content
        from .write_preview import PreviewNeeded
        from .vault_actions import fingerprint
        target_path = unique_path(self.root, path) if create else path
        target = safe_join(self.root, target_path)
        before = read_text_file(self.root, target_path)['content'] if target.is_file() else ''
        preview = PreviewNeeded(target_path, before, content, create, fingerprint(target))
        approved = self.approved_previews.get(preview.key)
        if approved is None:
            raise preview
        chosen = safe_join(self.root, approved['path'])
        if not create and approved['path'] != target_path:
            raise VaultError('Das Ziel einer bestehenden Notiz darf in der Vorschau nicht wechseln.')
        expected = approved['expected'] if approved['path'] == approved['original_path'] else None
        if fingerprint(chosen) != expected:
            raise VaultError('Das Vorschauziel wurde inzwischen verändert. Bitte erneut prüfen.')
        if not approved['path'].lower().endswith('.md') or not approved['content'].strip():
            raise VaultError('Die Vorschau braucht ein .md-Ziel und nichtleeren Inhalt.')
        checked, errors = _canonical_vault_source_links(self.root, approved['content'])
        if errors:
            raise VaultError(_source_link_error(errors))
        return approved['path'], checked

    def _notiz_erstellen(self, pfad: str = "", inhalt: str = "", **_: Any) -> Dict[str, Any]:
        inhalt = clean_generated_text(inhalt)
        inhalt, link_errors = _canonical_vault_source_links(self.root, inhalt)
        if link_errors:
            return {"fehler": _source_link_error(link_errors)}
        if not pfad.strip() or not inhalt.strip():
            return {"fehler": "Pfad und Inhalt dürfen nicht leer sein."}
        if not pfad.lower().endswith(".md"):
            pfad = f"{pfad}.md"

        pfad, inhalt = self._review_note(pfad, _normalise(inhalt), create=True)
        relative = create_unique_file(
            self.root, pfad, lambda stream: stream.write(inhalt.encode("utf-8")), exact=self.preview_writes)
        result = {"path": relative}
        self._changed(result["path"])
        if result["path"] not in self.note_files:
            self.note_files.append(result["path"])
        invalidate_overview(self.root)  # neuer Pfad soll in der Übersicht auftauchen
        self._refresh_guide()
        log.info("Modell hat Notiz angelegt: %s", result["path"])
        return {"erstellt": result["path"], "zeichen": len(inhalt)}

    def _notiz_ergaenzen(self, pfad: str = "", inhalt: str = "",
                         abschnitt: str = "", **_: Any) -> Dict[str, Any]:
        if self.focus and not self.focus.allows(pfad) and pfad not in self.changed_files:
            return {'fehler': 'Bestehende Notiz liegt außerhalb der erwähnten Ziele.'}
        inhalt = clean_generated_text(inhalt)
        inhalt, link_errors = _canonical_vault_source_links(self.root, inhalt)
        if link_errors:
            return {"fehler": _source_link_error(link_errors)}
        if not inhalt.strip():
            return {"fehler": "Der Inhalt darf nicht leer sein."}

        target = safe_join(self.root, pfad)
        if not target.is_file():
            return {
                "fehler": f"'{pfad}' gibt es nicht.",
                "hinweis": "Nutze notiz_erstellen, um die Notiz neu anzulegen.",
            }

        bestehend = read_text_file(self.root, pfad)["content"]
        neu = _insert(bestehend, _normalise(inhalt), abschnitt)
        pfad, neu = self._review_note(pfad, neu)
        result = write_text_file(self.root, pfad, neu, overwrite=True)
        self._changed(result["path"])
        if result["path"] not in self.note_files:
            self.note_files.append(result["path"])
        log.info("Modell hat Notiz ergänzt: %s (+%d Zeichen)", result["path"], len(inhalt))
        return {
            "ergaenzt": result["path"],
            "abschnitt": abschnitt or "(am Ende)",
            "zeichen_hinzugefuegt": len(inhalt),
        }

    def _notiz_bearbeiten(self, pfad: str = "", modus: str = "",
                          neuer_inhalt: str = "", alter_text: str = "",
                          abschnitt: str = "", grund: str = "", **_: Any) -> Dict[str, Any]:
        """Gezielte Änderung mit expliziter Freigabe und Erhalt des übrigen Texts."""
        if not self.allow_edit:
            return {
                "fehler": (
                    "Bearbeiten ist für diese Anfrage nicht freigegeben. Der Nutzer "
                    "muss die gewünschte Änderung ausdrücklich nennen."
                )
            }
        neuer_inhalt = clean_generated_text(neuer_inhalt)
        neuer_inhalt, link_errors = _canonical_vault_source_links(self.root, neuer_inhalt)
        if link_errors:
            return {"fehler": _source_link_error(link_errors)}
        if not neuer_inhalt.strip():
            return {"fehler": "Der neue Inhalt darf nicht leer sein."}

        data = read_text_file(self.root, pfad)
        note_path = data["path"]
        if note_path not in self.read_notes:
            return {
                "fehler": "Die Notiz muss in dieser Anfrage zuerst mit notiz_lesen gelesen werden."
            }
        bestehend = data["content"]

        if modus == "text_ersetzen":
            if not alter_text:
                return {"fehler": "Für text_ersetzen fehlt alter_text."}
            occurrences = bestehend.count(alter_text)
            if occurrences != 1:
                return {
                    "fehler": (
                        "alter_text muss exakt einmal vorkommen; gefunden: "
                        f"{occurrences}. Lies die Notiz erneut und grenze die Stelle genauer ein."
                    )
                }
            neu = bestehend.replace(alter_text, neuer_inhalt.strip(), 1)
            detail = "eine Textstelle"

        elif modus == "abschnitt_ersetzen":
            if not abschnitt.strip():
                return {"fehler": "Für abschnitt_ersetzen fehlt die Überschrift in abschnitt."}
            try:
                neu = _replace_section(bestehend, abschnitt, _normalise(neuer_inhalt))
            except ValueError as exc:
                return {"fehler": str(exc)}
            detail = f"Abschnitt '{abschnitt.strip()}'"

        elif modus == "vollstaendig_neustrukturieren":
            if not self.allow_full_rewrite:
                return {
                    "fehler": (
                        "Eine vollständige Neustrukturierung wurde nicht ausdrücklich "
                        "freigegeben. Nutze text_ersetzen oder abschnitt_ersetzen."
                    )
                }
            neu = _preserve_frontmatter(bestehend, _normalise(neuer_inhalt))
            retention = _content_retention(bestehend, neu)
            if retention < 0.35:
                return {
                    "fehler": (
                        "Die Neustrukturierung würde zu viel vorhandenen Inhalt verlieren "
                        f"({retention:.0%} inhaltliche Abdeckung). Übernimm die fehlenden "
                        "Informationen und versuche es erneut."
                    )
                }
            detail = f"gesamte Struktur ({retention:.0%} Inhalt erhalten)"
        else:
            return {"fehler": f"Unbekannter Bearbeitungsmodus: {modus}"}

        if neu.replace("\r\n", "\n") == bestehend.replace("\r\n", "\n"):
            return {"fehler": "Die vorgeschlagene Bearbeitung enthält keine Änderung."}
        note_path, neu = self._review_note(note_path, neu)
        result = write_text_file(self.root, note_path, neu, overwrite=True)
        self._changed(result["path"])
        if result["path"] not in self.note_files:
            self.note_files.append(result["path"])
        if result["path"] not in self.edited_notes:
            self.edited_notes.append(result["path"])
        log.info("Modell hat Notiz gezielt bearbeitet: %s (%s)", result["path"], detail)
        return {
            "bearbeitet": result["path"],
            "modus": modus,
            "umfang": detail,
            "grund": grund.strip(),
        }

    def _markdown_dateien_bereinigen(
        self, operationen: Any = None, **_: Any
    ) -> Dict[str, Any]:
        """Führt ausdrücklich freigegebene mechanische Änderungen vaultweit aus."""
        if not self.allow_batch_edit:
            return {
                "fehler": (
                    "Die Stapelbearbeitung ist für diese Anfrage nicht freigegeben. "
                    "Der Nutzer muss ausdrücklich alle Dateien oder den gesamten "
                    "Vault als Umfang nennen."
                )
            }
        if self.focus and self.focus.paths == ():
            return {'fehler': 'Bitte den Zielordner oder ausdrücklich den gesamten Vault nennen.'}

        if isinstance(operationen, str):
            requested = {operationen}
        elif isinstance(operationen, list):
            requested = {str(item) for item in operationen}
        else:
            requested = set()
        allowed = set(self.batch_edit_operations)
        selected = allowed.intersection(requested) if requested else allowed
        selected.difference_update(self.completed_batch_operations)
        if not selected:
            return {
                "fehler": "Keine noch ausstehende freigegebene Stapeloperation angegeben.",
                "erlaubt": list(self.batch_edit_operations),
            }

        result = _batch_clean_markdown(self.root, selected, self.focus)
        if "fehler" in result:
            return result

        self.completed_batch_operations.update(selected)
        self.batch_edit_done = allowed.issubset(self.completed_batch_operations)
        for path in result["geaenderte_dateien"]:
            self._changed(path)
            if path not in self.note_files:
                self.note_files.append(path)
            if path not in self.edited_notes:
                self.edited_notes.append(path)
        invalidate_overview(self.root)
        self._refresh_guide()
        return {
            **result,
            "vollstaendig": self.batch_edit_done,
            "noch_ausstehend": sorted(allowed.difference(self.completed_batch_operations)),
        }

    def _dateien_in_unterordner_verschieben(
        self, unterordner: str = "Dateien", **_: Any
    ) -> Dict[str, Any]:
        """Ordnet Binärquellen themennah ein und hält ihre Links konsistent."""
        if not self.allow_file_organization:
            return {
                "fehler": (
                    "Das Verschieben vorhandener Vault-Dateien ist für diese Anfrage "
                    "nicht freigegeben. Der Nutzer muss die gewünschte Dateiordnung "
                    "ausdrücklich nennen."
                )
            }
        folder = (unterordner or "Dateien").strip()
        if (not folder or folder in {".", ".."}
                or any(char in folder for char in '\\/:*?"<>|')):
            return {"fehler": f"Ungültiger Unterordner: {unterordner}"}
        if self.focus and self.focus.paths == ():
            return {'fehler': 'Bitte den Zielordner oder ausdrücklich den gesamten Vault nennen.'}

        result = _organize_vault_files(self.root, folder, self.focus)
        if "fehler" in result:
            return result

        self.file_organization_done = True
        for item in result["verschoben"]:
            self._changed(item["neuer_pfad"])
        for path in result["geaenderte_notizen"]:
            self._changed(path)
            if path not in self.note_files:
                self.note_files.append(path)
            if path not in self.edited_notes:
                self.edited_notes.append(path)
        invalidate_overview(self.root)
        self._refresh_guide()
        guide = ensure_file_subfolder_rule(self.root, folder)
        if guide.get("updated"):
            self._changed(str(guide["path"]))
        return {**result, "hauptseite": guide, "vollstaendig": True}


    # ------------------------------------------------------------- Anhänge

    def _anhang_lesen(self, name: str = "", offset: int = 0, limit: int = 7000, **_: Any) -> Dict[str, Any]:
        path = attachments.resolve(self.chat_id, name)
        cache = attachments.load_cache(self.chat_id)
        if name not in cache:
            if path.suffix.lower() in IMAGE_EXT:
                return {"fehler": "Noch keine Bildauswertung gespeichert. Nutze bild_ansehen."}
            result = attachments.extract_text(path, full=True)
            if result.get("fehler"):
                return result
            attachments.checkpoint(self.chat_id, name, "text", result.get("text", ""),
                                   complete=path.suffix.lower() != ".pdf")
        return attachments.cached_excerpt(self.chat_id, name, offset, limit)

    async def _bild_ansehen(self, name: str = "", frage: str = "", **_: Any) -> Dict[str, Any]:
        cached = await asyncio.to_thread(attachments.load_analysis, self.chat_id)
        if cached["progress"].get(name, {}).get("complete"):
            result = await asyncio.to_thread(attachments.cached_excerpt, self.chat_id, name)
            result["beschreibung"] = result.pop("text")
            return result
        if self.vision is None:
            return {"fehler": "Bildanalyse steht nicht zur Verfügung."}
        path = await asyncio.to_thread(attachments.resolve, self.chat_id, name)
        endung = path.suffix.lower()

        prompt = frage.strip() or (
            "Beschreibe genau, was hier zu sehen ist. Gib allen erkennbaren Text "
            "wörtlich wieder und stelle Tabellen als Markdown dar."
        )

        if endung not in IMAGE_EXT and endung != ".pdf":
            return {"fehler": f"'{name}' ist weder Bild noch PDF. Nutze anhang_lesen."}
        from .attachment_analysis import analyse_attachments
        async for _ in analyse_attachments(self.chat_id, [attachments.describe(path)], prompt, self.vision, self):
            pass
        result = await asyncio.to_thread(attachments.cached_excerpt, self.chat_id, name)
        result["beschreibung"] = result.pop("text")
        return result

    def _anhang_in_vault_ablegen(self, name: str = "", zielordner: str = "",
                                 neuer_name: str = "", **_: Any) -> Dict[str, Any]:
        if name in self.stored_attachments:
            return self.stored_attachments[name]
        quelle = attachments.resolve(self.chat_id, name)
        ordner = (zielordner or self.attachment_dir).strip()

        # Die Dateiendung kommt immer vom Original. Modelle schlagen sonst gern
        # ".md" vor, und ein PDF unter .md wäre im Vault unbrauchbar.
        stamm = Path(attachments.safe_filename(neuer_name.strip() or quelle.name)).stem
        dateiname = f"{stamm or quelle.stem}{quelle.suffix}"

        with quelle.open("rb") as source:
            rel = create_unique_file(
                self.root, f"{ordner}/{dateiname}" if ordner else dateiname,
                lambda stream: shutil.copyfileobj(source, stream))
        ziel = safe_join(self.root, rel)
        self._changed(rel)
        invalidate_overview(self.root)
        self._refresh_guide()
        log.info("Anhang in den Vault übernommen: %s -> %s", quelle.name, rel)

        alias = quelle.name.replace("|", "-")
        einbettung = (
            f"![[{rel}]]" if ziel.suffix.lower() in IMAGE_EXT
            else f"[[{rel}|{alias}]]"
        )
        result = {
            "abgelegt": rel,
            "original": quelle.name,
            "einbetten_als": einbettung,
        }
        self.stored_attachments[quelle.name] = result
        return result

    # ----------------------------------------- Verbindliche Auftragskontrolle

    def missing_actions(self, requirements: ActionRequirements) -> List[str]:
        """Noch fehlende Ergebnisse eines ausdrücklich schreibenden Auftrags."""
        missing: List[str] = []
        special_operation = False
        if requirements.organize_vault_files:
            special_operation = True
            if not self.file_organization_done:
                missing.append("organize_files")
        if requirements.requires_batch_edit:
            special_operation = True
            if not self.batch_edit_done:
                missing.append("batch_edit")
        if not special_operation and requirements.requires_edit and not self.edited_notes:
            missing.append("edit")
        elif not special_operation and requirements.note_write and not self.note_files:
            missing.append("note")
        if requirements.archive_attachments:
            names = set(requirements.attachment_names)
            if names.difference(self.stored_attachments):
                missing.append("attachments")
            if self.note_files and self.stored_attachments and not self._links_complete():
                missing.append("links")
        return missing

    def finish_required_actions(
        self,
        requirements: ActionRequirements,
        prompt: str,
        draft: str,
    ) -> List[Dict[str, Any]]:
        """Sicherheitsnetz nach erfolglosen Modellkorrekturen.

        Der Text stammt weiterhin vom Modell. Diese Methode sorgt nur dafür,
        dass der eindeutige Schreibauftrag nicht als Chatentwurf liegen bleibt.
        """
        steps: List[Dict[str, Any]] = []
        if requirements.organize_vault_files and not self.file_organization_done:
            result = self._dateien_in_unterordner_verschieben(
                unterordner=requirements.file_subfolder
            )
            steps.append(_automatic_step(
                "dateien_in_unterordner_verschieben", result,
                {"unterordner": requirements.file_subfolder},
            ))

        if requirements.requires_batch_edit and not self.batch_edit_done:
            remaining = set(requirements.batch_edit_operations).difference(
                self.completed_batch_operations
            )
            result = self._markdown_dateien_bereinigen(operationen=sorted(remaining))
            steps.append(_automatic_step(
                "markdown_dateien_bereinigen", result,
                {"operationen": sorted(remaining)},
            ))

        if (requirements.note_write and not requirements.requires_batch_edit
                and not requirements.organize_vault_files
                and not self.note_files):
            content = draft.strip()
            title = note_title(prompt)
            if not content:
                content = f"# {title}\n\n{prompt.strip()}"
            elif not content.lstrip().startswith("#"):
                content = f"# {title}\n\n{content}"

            # Eine Bearbeitung darf niemals still als neue Notiz enden. Nur eine
            # ausdrücklich erlaubte vollständige Neustrukturierung mit genau
            # einem zuvor gelesenen Ziel kann sicher automatisch abgeschlossen werden.
            if requirements.requires_edit:
                if requirements.allow_full_rewrite and len(self.read_notes) == 1 and content:
                    result = self._notiz_bearbeiten(
                        self.read_notes[0], "vollstaendig_neustrukturieren", content,
                        grund="Sicherheits-Fallback nach ausdrücklicher Neustrukturierung",
                    )
                else:
                    result = {
                        "fehler": (
                            "Die verlangte Änderung konnte nicht sicher automatisch "
                            "ausgeführt werden. Es wurde keine neue Datei angelegt und "
                            "kein bestehender Inhalt pauschal überschrieben."
                        )
                    }
                steps.append(_automatic_step("notiz_bearbeiten", result))

            # Wenn das Modell zuvor genau eine Notiz gelesen hat und der Nutzer
            # ergänzen wollte, ist dieses Ziel eindeutig. Sonst wird sicher eine
            # neue Notiz angelegt, statt eine möglicherweise falsche zu verändern.
            elif requirements.mode == "update" and len(self.read_notes) == 1:
                result = self._notiz_ergaenzen(self.read_notes[0], content)
                tool = "notiz_ergaenzen"
                steps.append(_automatic_step(tool, result))
            else:
                safe_title = attachments.safe_filename(title)
                if safe_title.lower().endswith(".md"):
                    safe_title = safe_title[:-3]
                wanted = f"02 KI-Notizen/{safe_title}.md"
                result = self._notiz_erstellen(unique_path(self.root, wanted), content)
                tool = "notiz_erstellen"
                steps.append(_automatic_step(tool, result))

        if requirements.archive_attachments and (not requirements.requires_edit or self.note_files):
            target_dir = self._fallback_attachment_dir()
            for name in requirements.attachment_names:
                if name in self.stored_attachments:
                    continue
                result = self._anhang_in_vault_ablegen(name=name, zielordner=target_dir)
                steps.append(_automatic_step("anhang_in_vault_ablegen", result,
                                             {"name": name, "zielordner": target_dir}))

        link_result = self.ensure_attachment_links()
        if link_result:
            steps.append(_automatic_step("dateien_verknuepfen", link_result))
        return steps

    def ensure_attachment_links(self) -> Optional[Dict[str, Any]]:
        """Kanonisiert Quellenlinks und ergänzt fehlende echte Vault-Links."""
        if not self.note_files or not self.stored_attachments:
            return None
        note_path = self.note_files[-1]
        current = read_text_file(self.root, note_path)["content"]
        current, corrected = _canonical_attachment_links(
            current, list(self.stored_attachments.values())
        )
        if corrected:
            note_path, current = self._review_note(note_path, current)
            result = write_text_file(self.root, note_path, current, overwrite=True)
            self._changed(result["path"])

        missing = [item for item in self.stored_attachments.values()
                   if not _contains_vault_link(current, item["abgelegt"])]
        if not missing:
            if not corrected:
                return None
            return {
                "notiz": note_path,
                "korrigiert": corrected,
                "verknuepft": [],
            }

        lines = []
        for item in missing:
            rel = item["abgelegt"]
            name = item["original"].replace("|", "-")
            if Path(rel).suffix.lower() in IMAGE_EXT:
                lines.append(f"- **{name}:** ![[{rel}]]")
            else:
                lines.append(f"- [[{rel}|{name}]]")
        if re.search(r"(?im)^#{1,6}\s+zugehörige dateien\s*$", current):
            result = self._notiz_ergaenzen(
                note_path, "\n".join(lines), abschnitt="Zugehörige Dateien"
            )
        else:
            result = self._notiz_ergaenzen(
                note_path, "## Zugehörige Dateien\n\n" + "\n".join(lines)
            )
        return {
            "notiz": note_path,
            "korrigiert": corrected,
            "verknuepft": [item["abgelegt"] for item in missing],
            "ergebnis": result,
        }

    def _links_complete(self) -> bool:
        if not self.note_files:
            return False
        try:
            content = read_text_file(self.root, self.note_files[-1])["content"]
        except VaultError:
            return False
        return all(_contains_vault_link(content, item["abgelegt"])
                   for item in self.stored_attachments.values())

    def _fallback_attachment_dir(self) -> str:
        if self.note_files:
            parent = str(Path(self.note_files[-1]).parent).replace("\\", "/")
            if parent and parent != ".":
                return f"{parent}/Dateien"
        return self.attachment_dir


def _automatic_step(tool: str, result: Dict[str, Any],
                    arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "tool": tool,
        "arguments": arguments or {},
        "result": result,
        "writing": True,
        "ok": "fehler" not in result,
        "automatic": True,
    }


def _contains_vault_link(content: str, relative: str) -> bool:
    """Akzeptiert ausschließlich den tatsächlichen vollständigen Vault-Pfad."""
    rel = relative.replace("\\", "/").lower()
    for match in re.finditer(r"!?\[\[([^\]|#]+)", content or ""):
        target = match.group(1).strip().replace("\\", "/").lower()
        if target == rel:
            return True
    return False


def _canonical_attachment_links(
    content: str, items: List[Dict[str, str]]
) -> tuple[str, List[str]]:
    """Ersetzt geratene Dateinamenlinks durch die beim Kopieren erhaltenen Pfade."""
    by_name: Dict[str, Dict[str, str]] = {}
    by_path: Dict[str, Dict[str, str]] = {}
    for item in items:
        rel = item["abgelegt"].replace("\\", "/")
        by_path[rel.casefold()] = item
        by_name[Path(rel).name.casefold()] = item
        by_name[Path(item["original"]).name.casefold()] = item

    corrected: List[str] = []
    pattern = re.compile(r"!?\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")

    def replace(match: re.Match[str]) -> str:
        raw_target = match.group(1).strip().replace("\\", "/")
        item = by_path.get(raw_target.casefold())
        if item is None:
            item = by_name.get(Path(raw_target).name.casefold())
        if item is None:
            return match.group(0)
        canonical = item["einbetten_als"]
        if match.group(0) != canonical:
            rel = item["abgelegt"]
            if rel not in corrected:
                corrected.append(rel)
        return canonical

    return pattern.sub(replace, content or ""), corrected


def _canonical_vault_source_links(root: Path, content: str) -> tuple[str, List[str]]:
    """Prüft Links zu Binärquellen gegen tatsächlich vorhandene Vault-Dateien.

    Ein nur mit Dateinamen angegebener Link wird auf den vollständigen Pfad
    erweitert, wenn dieser im Vault eindeutig ist. Nicht vorhandene oder
    mehrdeutige PDF-/Dokument-/Bildlinks werden nicht geschrieben.
    """
    source_ext = DOC_EXT | IMAGE_EXT
    # Ohne Quellenlink ist kein vollständiger Vault-Scan nötig.
    if not re.search(r"\[\[[^\]]+\.(?:" + "|".join(
            re.escape(ext[1:]) for ext in source_ext) + r")(?=[#|\]])", content, re.I):
        return content, []
    by_path: Dict[str, str] = {}
    by_name: Dict[str, List[str]] = {}
    for path in iter_files(root, kinds=("doc", "image")):
        rel = to_relative(root, path)
        by_path[rel.casefold()] = rel
        by_name.setdefault(path.name.casefold(), []).append(rel)

    problems: List[str] = []
    pattern = re.compile(
        r"(?P<embed>!)?\[\[(?P<target>[^\]|#]+)"
        r"(?P<anchor>#[^\]|]*)?(?:\|(?P<label>[^\]]*))?\]\]"
    )

    def replace(match: re.Match[str]) -> str:
        target = match.group("target").strip().replace("\\", "/")
        if Path(target).suffix.casefold() not in source_ext:
            return match.group(0)
        canonical = by_path.get(target.casefold())
        if canonical is None:
            candidates = by_name.get(Path(target).name.casefold(), [])
            if len(candidates) == 1:
                canonical = candidates[0]
            elif not candidates:
                problems.append(f"nicht vorhanden: {target}")
                return match.group(0)
            else:
                problems.append(
                    f"mehrdeutig: {target} ({', '.join(candidates[:4])})"
                )
                return match.group(0)

        prefix = "!" if match.group("embed") else ""
        anchor = match.group("anchor") or ""
        label = match.group("label")
        alias = f"|{label}" if label is not None else ""
        return f"{prefix}[[{canonical}{anchor}{alias}]]"

    return pattern.sub(replace, content or ""), list(dict.fromkeys(problems))


def _source_link_error(problems: List[str]) -> str:
    return (
        "Die Notiz enthält Quellenlinks, die keinem eindeutigen tatsächlichen "
        "Vault-Pfad entsprechen: " + "; ".join(problems)
        + ". Lege die Originaldatei zuerst im Vault ab und verwende den "
          "zurückgegebenen vollständigen Pfad."
    )


_EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"  # Flaggen
    "\U0001F300-\U0001FAFF"  # Symbole, Piktogramme, Gesichter
    "\U0001F3FB-\U0001F3FF"  # Hautfarbmodifikatoren
    "\u2300-\u23FF"
    "\u2600-\u27BF"
    "]",
    re.UNICODE,
)


def _batch_clean_markdown(root: Path, operations: set[str], focus=None) -> Dict[str, Any]:
    """Bereitet alle Änderungen vor und schreibt sie anschließend transaktional."""
    notes = sorted(focus.files(root, kinds=('note',)) if focus else iter_files(root, kinds=("note",)), key=lambda item: str(item).casefold())
    resolver = _build_link_resolver(root)
    prepared: List[tuple[str, str, str]] = []
    unresolved: List[Dict[str, str]] = []

    try:
        for path in notes:
            rel = to_relative(root, path)
            original = read_text_file(root, rel)["content"]
            updated = original
            if "remove_emojis" in operations:
                updated = _outside_fences(updated, _remove_emojis)
            if "fix_relative_links" in operations:
                file_unresolved: List[str] = []
                updated = _outside_fences(
                    updated,
                    lambda line, note=rel: _fix_links_in_line(
                        line, note, resolver, file_unresolved
                    ),
                )
                unresolved.extend(
                    {"datei": rel, "link": item} for item in dict.fromkeys(file_unresolved)
                )
            if updated != original:
                prepared.append((rel, original, updated))
    except (OSError, VaultError) as exc:
        return {
            "fehler": f"Die Stapelprüfung wurde vor dem Schreiben abgebrochen: {exc}",
            "geprueft": 0,
            "geaendert": 0,
        }

    written: List[tuple[str, str]] = []
    try:
        for rel, original, updated in prepared:
            write_text_file(root, rel, updated, overwrite=True)
            written.append((rel, original))
    except (OSError, VaultError) as exc:
        rollback_errors = []
        for rel, original in reversed(written):
            try:
                write_text_file(root, rel, original, overwrite=True)
            except (OSError, VaultError) as rollback_exc:
                rollback_errors.append(f"{rel}: {rollback_exc}")
        suffix = (
            " Rücksetzen fehlgeschlagen bei: " + "; ".join(rollback_errors)
            if rollback_errors else " Bereits geschriebene Dateien wurden zurückgesetzt."
        )
        return {"fehler": f"Stapelbearbeitung fehlgeschlagen: {exc}.{suffix}"}

    changed = [rel for rel, _, _ in prepared]
    return {
        "operationen": sorted(operations),
        "geprueft": len(notes),
        "geaendert": len(changed),
        "unveraendert": len(notes) - len(changed),
        "geaenderte_dateien": changed,
        "nicht_aufloesbare_links": unresolved,
    }


def _organize_vault_files(root: Path, subfolder: str, focus=None) -> Dict[str, Any]:
    """Verschiebt thematische Binärquellen samt Linkanpassung transaktional."""
    notes = sorted(iter_files(root, kinds=("note",)), key=lambda item: str(item).casefold())
    sources = sorted(
        focus.files(root, kinds=('doc', 'image')) if focus else iter_files(root, kinds=("doc", "image")),
        key=lambda item: str(item).casefold(),
    )
    note_parents = {str(path.parent).casefold() for path in notes}
    candidates = [
        path for path in sources
        if str(path.parent).casefold() in note_parents
        and path.parent.name.casefold() != subfolder.casefold()
    ]

    moves: List[tuple[Path, Path, str, str]] = []
    mapping: Dict[str, str] = {}
    conflicts: List[str] = []
    for source in candidates:
        old_rel = to_relative(root, source)
        target = source.parent / subfolder / source.name
        new_rel = to_relative(root, target)
        if target.exists():
            conflicts.append(new_rel)
            continue
        moves.append((source, target, old_rel, new_rel))
        mapping[old_rel.casefold()] = new_rel

    if conflicts:
        return {
            "fehler": (
                "Die Dateiordnung wurde vor dem Verschieben abgebrochen, weil "
                "Zieldateien bereits existieren: " + "; ".join(conflicts)
            ),
            "konflikte": conflicts,
        }

    prepared_notes: List[tuple[str, str, str]] = []
    try:
        for note in notes:
            rel = to_relative(root, note)
            original = read_text_file(root, rel)["content"]
            updated = _outside_fences(
                original,
                lambda line, note_path=rel: _rewrite_links_after_moves(
                    line, note_path, mapping
                ),
            )
            if updated != original:
                prepared_notes.append((rel, original, updated))
    except (OSError, VaultError) as exc:
        return {
            "fehler": f"Die Linkprüfung wurde vor dem Verschieben abgebrochen: {exc}"
        }

    moved: List[tuple[Path, Path]] = []
    written_notes: List[tuple[str, str]] = []
    try:
        for source, target, _, _ in moves:
            from .vault_actions import before_change, after_change
            before_change(root, to_relative(root, source))
            before_change(root, to_relative(root, target))
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
            after_change(root, to_relative(root, source))
            after_change(root, to_relative(root, target))
            moved.append((source, target))
        for rel, original, updated in prepared_notes:
            write_text_file(root, rel, updated, overwrite=True)
            written_notes.append((rel, original))
    except (OSError, VaultError) as exc:
        rollback_errors: List[str] = []
        for rel, original in reversed(written_notes):
            try:
                write_text_file(root, rel, original, overwrite=True)
            except (OSError, VaultError) as rollback_exc:
                rollback_errors.append(f"{rel}: {rollback_exc}")
        for source, target in reversed(moved):
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                target.replace(source)
                after_change(root, to_relative(root, source))
                after_change(root, to_relative(root, target))
            except OSError as rollback_exc:
                rollback_errors.append(f"{to_relative(root, target)}: {rollback_exc}")
        detail = (
            " Rücksetzen fehlgeschlagen bei: " + "; ".join(rollback_errors)
            if rollback_errors else " Alle bereits ausgeführten Änderungen wurden zurückgesetzt."
        )
        return {"fehler": f"Dateien konnten nicht vollständig geordnet werden: {exc}.{detail}"}

    return {
        "unterordner": subfolder,
        "geprueft": len(sources),
        "verschoben_anzahl": len(moves),
        "bereits_eingeordnet": len(sources) - len(moves),
        "verschoben": [
            {"alter_pfad": old_rel, "neuer_pfad": new_rel}
            for _, _, old_rel, new_rel in moves
        ],
        "geaenderte_notizen": [rel for rel, _, _ in prepared_notes],
    }


def _rewrite_links_after_moves(
    line: str, note_path: str, mapping: Dict[str, str]
) -> str:
    """Schreibt Links auf verschobene Quellen auf deren neuen Vault-Pfad um."""
    if not mapping:
        return line

    def moved_target(raw: str) -> Optional[str]:
        value = unquote(raw.strip().strip("<> ")).replace("\\", "/")
        if not value or value.startswith(("#", "http://", "https://", "mailto:", "data:", "obsidian:")):
            return None
        value = re.split(r"\s+[\"']", value, maxsplit=1)[0]
        path_part = value.partition("#")[0]
        direct = mapping.get(path_part.lstrip("/").casefold())
        if direct is not None:
            return direct
        parent = posixpath.dirname(note_path.replace("\\", "/"))
        candidate = posixpath.normpath(posixpath.join(parent, path_part))
        return mapping.get(candidate.casefold())

    def markdown_replace(match: re.Match[str]) -> str:
        target = moved_target(match.group("target"))
        if target is None:
            return match.group(0)
        embed = "!" if match.group("embed") else ""
        label = match.group("label").strip()
        alias = f"|{label}" if label else ""
        return f"{embed}[[{target}{alias}]]"

    def wiki_replace(match: re.Match[str]) -> str:
        target = moved_target(match.group("target"))
        if target is None:
            return match.group(0)
        embed = "!" if match.group("embed") else ""
        anchor = match.group("anchor") or ""
        label = match.group("label")
        alias = f"|{label.strip()}" if label and label.strip() else ""
        return f"{embed}[[{target}{anchor}{alias}]]"

    return _WIKI_LINK_RE.sub(wiki_replace, _MARKDOWN_LINK_RE.sub(markdown_replace, line))


def _outside_fences(content: str, transform: Callable[[str], str]) -> str:
    """Verändert normalen Markdown-Text, aber keine Inhalte in Codeblöcken."""
    lines = content.splitlines(keepends=True)
    fence_marker = ""
    fence_length = 0
    out: List[str] = []
    for line in lines:
        stripped = line.lstrip()
        fence = re.match(r"(`{3,}|~{3,})(.*)", stripped)
        if fence and not fence_marker:
            fence_marker, fence_length = fence[1][0], len(fence[1])
            out.append(line)
        elif fence_marker:
            out.append(line)
            if (fence and fence[1][0] == fence_marker and len(fence[1]) >= fence_length
                    and not fence[2].strip()):
                fence_marker = ""
        else:
            out.append(transform(line))
    return "".join(out)


def _remove_emojis(line: str) -> str:
    cleaned = _EMOJI_RE.sub("", line).replace("\ufe0f", "").replace("\u200d", "")
    cleaned = re.sub(r"^(#{1,6})[ \t]{2,}", r"\1 ", cleaned)
    cleaned = re.sub(r"^([-*+])[ \t]{2,}", r"\1 ", cleaned)
    cleaned = re.sub(r"\[[ \t]+", "[", cleaned)
    return cleaned


def _build_link_resolver(root: Path) -> Dict[str, Dict[str, str]]:
    files: Dict[str, str] = {}
    notes_by_dir: Dict[str, Dict[str, str]] = {}
    for path in iter_files(root):
        rel = to_relative(root, path).replace("\\", "/")
        target = rel.rsplit(".", 1)[0] if kind_for(path) == "note" else rel
        files[rel.casefold()] = target
        if kind_for(path) == "note":
            files[target.casefold()] = target
            parent = posixpath.dirname(rel).casefold()
            notes_by_dir.setdefault(parent, {})[path.name.casefold()] = target

    directories: Dict[str, str] = {}
    for folder, names in notes_by_dir.items():
        for preferred in ("readme.md", "00 inhalt.md", "00_inhalt.md", "index.md"):
            if preferred in names:
                directories[folder] = names[preferred]
                break
    return {"files": files, "directories": directories}


def _resolve_relative_link(
    raw: str, note_path: str, resolver: Dict[str, Dict[str, str]]
) -> Optional[str]:
    value = unquote(raw.strip().strip("<>")).replace("\\", "/")
    if not value or value.startswith(("#", "http://", "https://", "mailto:", "data:", "obsidian:")):
        return None
    # Titel in klassischen Markdown-Links: (datei.md "Titel")
    value = re.split(r"\s+[\"']", value, maxsplit=1)[0]
    path_part, marker, anchor = value.partition("#")
    parent = posixpath.dirname(note_path.replace("\\", "/"))
    if path_part.startswith("/"):
        candidate = posixpath.normpath(path_part.lstrip("/"))
    else:
        candidate = posixpath.normpath(posixpath.join(parent, path_part))
    if candidate == ".." or candidate.startswith("../"):
        return None

    target = resolver["files"].get(candidate.casefold())
    if target is None:
        target = resolver["directories"].get(candidate.rstrip("/").casefold())
    if target is None:
        return None
    return target + (f"#{anchor}" if marker and anchor else "")


_MARKDOWN_LINK_RE = re.compile(
    r"(?P<embed>!)?\[(?!\[)(?P<label>[^\]]*)\]\((?P<target>[^)]+)\)"
)
_WIKI_LINK_RE = re.compile(
    r"(?P<embed>!)?\[\[(?P<target>[^\]|#]+)"
    r"(?P<anchor>#[^\]|]*)?(?:\|(?P<label>[^\]]*))?\]\]"
)


def _fix_links_in_line(
    line: str,
    note_path: str,
    resolver: Dict[str, Dict[str, str]],
    unresolved: List[str],
) -> str:
    def markdown_replace(match: re.Match[str]) -> str:
        raw = match.group("target").strip()
        target = _resolve_relative_link(raw, note_path, resolver)
        if target is None:
            if not raw.startswith(("#", "http://", "https://", "mailto:", "data:", "obsidian:")):
                unresolved.append(raw)
            return match.group(0)
        embed = "!" if match.group("embed") else ""
        label = match.group("label").strip()
        alias = f"|{label}" if label else ""
        return f"{embed}[[{target}{alias}]]"

    def wiki_replace(match: re.Match[str]) -> str:
        raw = match.group("target").strip()
        anchor = match.group("anchor") or ""
        if raw.startswith((".", "/")):
            target = _resolve_relative_link(raw + anchor, note_path, resolver)
        else:
            # Bereits vaultweit formulierte Links können trotzdem nur auf einen
            # Ordner zeigen. Wenn dort eine README-/Indexnotiz existiert, wird
            # der Link auf dieses tatsächlich vorhandene Ziel vervollständigt.
            target = resolver["files"].get(raw.casefold())
            if target is None:
                target = resolver["directories"].get(raw.rstrip("/").casefold())
            if target is not None:
                target += anchor
        if target is None:
            if raw.startswith((".", "/")):
                unresolved.append(raw + anchor)
            return match.group(0)
        embed = "!" if match.group("embed") else ""
        label = match.group("label")
        alias = f"|{label.strip()}" if label and label.strip() else ""
        return f"{embed}[[{target}{alias}]]"

    return _WIKI_LINK_RE.sub(wiki_replace, _MARKDOWN_LINK_RE.sub(markdown_replace, line))


def _clean(arguments: Any) -> Dict[str, Any]:
    """Modelle liefern gelegentlich Zahlen oder None statt Strings."""
    if not isinstance(arguments, dict):
        return {}
    return {str(k): ("" if v is None else v) for k, v in arguments.items()}


def _normalise(text: str) -> str:
    return clean_generated_text(text).replace("\r\n", "\n").strip() + "\n"


def clean_generated_text(text: str) -> str:
    """Entfernt unerwünschte Herkunfts-Metasätze aus KI-Texten.

    Konkrete Quellenabschnitte und Links bleiben bestehen. Entfernt werden nur
    eigenständige pauschale Sätze wie „Diese Notiz basiert ausschließlich auf
    den angehängten PDFs und Bildern“.
    """
    generic = re.compile(
        r"(?:diese|die) (?:notiz|dokumentation|zusammenfassung) "
        r"(?:basiert|beruht) (?:ausschließlich |nur )?auf (?:den |der )?"
        r"(?:angehängten|bereitgestellten|hochgeladenen) "
        r"(?:pdfs?|bildern?|dateien|dokumenten|informationen)"
        r"(?: und (?:pdfs?|bildern?|dateien|dokumenten|informationen))?[.!]?",
        re.IGNORECASE,
    )

    def clean_line(line: str) -> str:
        plain = line.strip().strip("*_ ")
        # Nur eine vollständig generische Einzelzeile entfernen. Zusätzliche
        # Aussagen, Zahlen, konkrete Quellen, Zitate und Code bleiben erhalten.
        return "" if generic.fullmatch(plain) else line

    return _outside_fences((text or "").replace("\r\n", "\n"), clean_line).strip()



def _insert(bestehend: str, neu: str, abschnitt: str) -> str:
    """Fügt Text unter einer Überschrift ein — sonst am Dateiende."""
    body = bestehend.replace("\r\n", "\n").rstrip()
    if not abschnitt.strip():
        return f"{body}\n\n{neu}"

    ziel = abschnitt.strip().lstrip("#").strip().lower()
    lines = body.split("\n")
    start = None
    level = 0
    for index, line in enumerate(lines):
        if line.startswith("#") and line.lstrip("#").strip().lower() == ziel:
            start = index
            level = len(line) - len(line.lstrip("#"))
            break

    if start is None:
        # Überschrift nicht gefunden: als neuen Abschnitt anhängen. Bringt der
        # Text die Überschrift schon selbst mit, wird sie nicht doppelt gesetzt.
        erste_zeile = neu.lstrip().split("\n", 1)[0]
        if erste_zeile.startswith("#") and erste_zeile.lstrip("#").strip().lower() == ziel:
            return f"{body}\n\n{neu}"
        return f"{body}\n\n## {abschnitt.strip()}\n\n{neu}"

    # Ende des Abschnitts suchen: nächste Überschrift gleicher oder höherer Ebene.
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("#"):
            current = len(line) - len(line.lstrip("#"))
            if current <= level:
                end = index
                break

    block = "\n".join(lines[start:end]).rstrip()
    rest = "\n".join(lines[end:])
    out = f"{block}\n\n{neu.rstrip()}"
    return f"{out}\n\n{rest}".rstrip() + "\n" if rest.strip() else out + "\n"


def _replace_section(bestehend: str, abschnitt: str, neuer_inhalt: str) -> str:
    """Ersetzt nur den Rumpf einer vorhandenen Überschrift."""
    body = bestehend.replace("\r\n", "\n").rstrip()
    ziel = abschnitt.strip().lstrip("#").strip().lower()
    lines = body.split("\n")
    start = None
    level = 0
    for index, line in enumerate(lines):
        if line.startswith("#") and line.lstrip("#").strip().lower() == ziel:
            start = index
            level = len(line) - len(line.lstrip("#"))
            break
    if start is None:
        raise ValueError(f"Die Überschrift '{abschnitt}' wurde nicht gefunden.")

    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("#"):
            current = len(line) - len(line.lstrip("#"))
            if current <= level:
                end = index
                break

    replacement = neuer_inhalt.strip()
    first = replacement.split("\n", 1)[0] if replacement else ""
    if first.startswith("#") and first.lstrip("#").strip().lower() == ziel:
        replacement = replacement.split("\n", 1)[1].strip() if "\n" in replacement else ""
    before = "\n".join(lines[:start + 1]).rstrip()
    after = "\n".join(lines[end:]).lstrip()
    result = f"{before}\n\n{replacement}"
    if after:
        result += f"\n\n{after}"
    return result.rstrip() + "\n"


def _preserve_frontmatter(bestehend: str, neu: str) -> str:
    """Bei einer Neustrukturierung bleiben vorhandene YAML-Metadaten exakt erhalten."""
    match = re.match(r"\A(---\s*\n.*?\n---\s*\n)", bestehend, re.DOTALL)
    if not match:
        return neu
    without_new = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", neu, count=1,
                         flags=re.DOTALL).lstrip()
    return match.group(1).rstrip() + "\n\n" + without_new.rstrip() + "\n"


_RETENTION_STOPWORDS = {
    "aber", "alle", "auch", "dass", "eine", "einem", "einen", "einer",
    "eines", "oder", "sich", "sind", "unter", "über", "wenn", "werden",
    "wird", "wurde", "zum", "zur", "thema", "inhalt", "notiz",
}


def _content_retention(bestehend: str, neu: str) -> float:
    """Anteil charakteristischer alter Begriffe, die im neuen Text erhalten sind."""
    def terms(value: str) -> set[str]:
        return {
            word for word in re.findall(r"[\wäöüß-]{4,}", value.lower(), re.UNICODE)
            if word not in _RETENTION_STOPWORDS and not word.isdigit()
        }

    old_terms = terms(bestehend)
    if not old_terms:
        return 1.0
    return len(old_terms.intersection(terms(neu))) / len(old_terms)


# ------------------------------------------------------------- Vault-Kontext

_OVERVIEW_CACHE: Dict[str, tuple[float, str]] = {}
OVERVIEW_TTL = 120.0  # Sekunden


def vault_overview(root: Path, max_folders: int = 24) -> str:
    """Kompakte Vault-Übersicht für die System-Anweisung.

    Das Modell soll von sich aus wissen, dass ein Vault da ist und wie er
    gegliedert ist — ohne dass der Nutzer ihn jedes Mal erwähnen muss.

    Ergebnis wird kurz zwischengespeichert: Der Durchlauf kostet bei großen
    Vaults spürbar Zeit und wird bei jeder Nachricht gebraucht.
    """
    key = str(root)
    cached = _OVERVIEW_CACHE.get(key)
    if cached and (time.monotonic() - cached[0]) < OVERVIEW_TTL:
        return cached[1]

    text = _build_overview(root, max_folders)
    _OVERVIEW_CACHE[key] = (time.monotonic(), text)
    return text


def invalidate_overview(root: Path) -> None:
    """Nach Änderungen im Vault die Übersicht neu aufbauen lassen."""
    _OVERVIEW_CACHE.pop(str(root), None)


def _build_overview(root: Path, max_folders: int) -> str:
    zeilen: List[str] = []
    anzahl = {"note": 0, "doc": 0, "image": 0}

    try:
        top = [n for n in list_dir(root, "") if n.type == "dir"]
    except VaultError:
        return ""

    for node in top[:max_folders]:
        try:
            unter = [c.name for c in list_dir(root, node.path) if c.type == "dir"][:6]
        except VaultError:
            unter = []
        zeilen.append(f"- {node.path}" + (f"  (enthält: {', '.join(unter)})" if unter else ""))

    for path in iter_files(root):
        kind = kind_for(path)
        if kind in anzahl:
            anzahl[kind] += 1

    struktur = "\n".join(zeilen) if zeilen else "- (noch keine Unterordner)"
    return (
        f"Ordnerstruktur des Vaults:\n{struktur}\n\n"
        f"Umfang: {anzahl['note']} Notizen, {anzahl['doc']} Dokumente, {anzahl['image']} Bilder."
    )


BASE_INSTRUCTIONS = """Du bearbeitest den konkreten Vault-Auftrag vollständig und ohne zusätzliche Nebenaufgaben.
- Vollständigkeit vor Kürze: ALLE vom Nutzer in diesem Chat eingebrachten Sachinformationen sind relevant. Erhalte auch Beispiele, Zahlen samt Einheiten, Namen, Links, Begründungen, Bedingungen, Ausnahmen, Einschränkungen und offene Fragen. Formuliere verständlich und ordne sinnvoll; fasse nicht so zusammen, dass Details oder Zusammenhänge verschwinden. Nur echte inhaltliche Wiederholungen dürfen ohne Verlust zusammengeführt werden. Inhalt kürzen, weglassen oder löschen nur auf ausdrücklichen Auftrag.
- Frühere Angaben sind Quellen, keine erneut auszuführenden alten Befehle. Spätere ausdrückliche Korrekturen ersetzen überholte Angaben; ungelöste Widersprüche transparent nebeneinander mit Herkunft erhalten. Themenwechsel erlaubt sinnvolle Aufteilung/Verlinkung, kein stilles Verwerfen von Informationen.
- Unvollständige Informationen ausbauen: Stichpunkte zu verständlichen Sätzen ausarbeiten, Begriffe erklären, Zusammenhänge und benötigte Schritte ergänzen. Allgemeines Fachwissen als ergänzende Erklärung kenntlich machen. Fehlende konkrete Fakten, Kennungen, Werte, Entscheidungen oder Quellen niemals erfinden; als offene Punkte festhalten und nur bei arbeitsentscheidenden Lücken gezielt nachfragen. Unsicherheit und Negationen erhalten.
- Prüfe vor jedem Schreiben die Abdeckung aller Nutzerangaben gegen den fertigen Inhalt: jeder eigenständige Sachpunkt muss enthalten oder in einer konkret verlinkten bestehenden Notiz erhalten sein. Eine bloße Kurzfassung oder Rohdatensammlung ersetzt keine vollständig ausgearbeitete Wissensnotiz. Die kurze Abschlussantwort betrifft nur den Chat, niemals den Umfang der gespeicherten Notiz.
- Halte den KONTEXTFOKUS ein: nur erwähnte Dateien/Ordner, aktuelle Anhänge und Nutzereingaben. Nutze bereits vorhandene passende Auswertungen direkt. Suche höchstens einmal innerhalb des Fokus. Ohne eindeutiges notwendiges Ziel nur dessen Pfad erfragen. Keine allgemeine Vault-Erkundung oder wiederholte Suchläufe. Lange Notizen mit naechster_offset vollständig weiterlesen; mehrere unabhängige Werkzeugaufrufe dürfen in eine Runde.
- Neue Notiz: notiz_erstellen mit vollständigem Inhalt. Ergänzung: notiz_lesen, dann notiz_ergaenzen. Ausdrückliche Änderung: notiz_lesen, dann notiz_bearbeiten mit kleinstem passenden Umfang. Alles andere samt YAML erhalten; volle Neustrukturierung nur bei entsprechendem Auftrag. Keine ganzen Dateien löschen.
- Eindeutige Nutzeraufträge sind bereits freigegeben. Keine erneuten Erlaubnisfragen, Arbeitsankündigungen oder Entwürfe nur im Chat. Das Ergebnis muss mit erfolgreichen Werkzeugen im Vault landen.
- Globale Emoji-/Linkbereinigung: einmal markdown_dateien_bereinigen; Suchtreffer begrenzen nie den Umfang. Dateiordnung: dateien_in_unterordner_verschieben aktualisiert auch Links.
- Anhänge: bereitgestellte Auswertungen zuerst nutzen. Nur fehlende relevante Inhalte mit anhang_lesen/bild_ansehen nachladen. Alle zum Auftrag gehörenden Quellen berücksichtigen, Widersprüche mit Quelle benennen, Fakten nicht erfinden.
- Originale gemäß Auftragsvertrag mit anhang_in_vault_ablegen in den passenden Themenordner/Dateien kopieren; bei ausdrücklich verbotener Ablage nichts kopieren. Vor dem Schreiben einer Quellennotiz Originale ablegen und exakt einbetten_als übernehmen. Dateinamenskollisionen nummeriert das Werkzeug automatisch (image.png, image1.png, image2.png): keine Namenssuche oder Rückfrage.
- Nutze vorhandene Struktur und passende, tatsächlich vorhandene WikiLinks. Keine sachfremden Notizen umgestalten. Kurze Absätze, verständliche Gliederung, fachlich vollständiger Inhalt; keine Platzhalter, Dopplungen oder pauschalen Herkunftssätze.
- Nach erfolgreichem Schreiben genügt das Werkzeugergebnis als Speichernachweis. Nur bei konkretem Fehler erneut arbeiten. Zum Abschluss ein kurzer deutscher Satz mit tatsächlichem Pfad; den Notizinhalt nicht nochmals im Chat wiederholen."""
