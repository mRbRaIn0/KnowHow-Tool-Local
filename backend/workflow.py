"""Erkennt konkrete Vault-Aufträge und prüft, ob sie wirklich erledigt wurden.

Das Modell bleibt für Inhalt, Struktur und Ablageentscheidung verantwortlich.
Diese kleine, deterministische Schicht verhindert aber, dass ein klarer Auftrag
wie "Erstelle eine Notiz" mit einer bloßen Chat-Antwort endet.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


_CREATE = re.compile(
    r"\b(?:erstell\w*|anleg\w*|verfass\w*|schreib\w*|dokumentier\w*|"
    r"speicher\w*|sicher\w*|mach\w*)\b.{0,45}"
    r"\b(?:notiz|dokumentation|dokument|lernzettel|übersicht|zusammenfassung|"
    r"wissensseite|datei|markdown)\b|"
    r"\b(?:create|write|save|draft)\b.{0,35}\b(?:note|documentation|document|file)\b",
    re.IGNORECASE | re.DOTALL,
)
_UPDATE = re.compile(
    r"\b(?:ergänz\w*|erweiter\w*|aktualisier\w*|überarbeit\w*|"
    r"vervollständig\w*|füg\w*.{0,18}hinzu|append|update|extend)\b",
    re.IGNORECASE | re.DOTALL,
)
_EDIT = re.compile(
    r"\b(?:änder\w*|abänder\w*|bearbeit\w*|überarbeit\w*|aktualisier\w*|korrigier\w*|entfern\w*|"
    r"ersetz\w*|pass\w*.{0,15}an)\b.{0,55}"
    r"\b(?:notiz|text|abschnitt|struktur|aufbau|design|layout|formatierung|"
    r"datei|dokumentation|dokument|emoji|link|wikilink|verlinkung)\w*\b|"
    r"\b(?:notiz|text|abschnitt|struktur|aufbau|design|layout|formatierung|emoji|link|wikilink|verlinkung)\w*\b"
    r".{0,35}\b(?:änder\w*|abänder\w*|bearbeit\w*|überarbeit\w*|aktualisier\w*|"
    r"korrigier\w*|entfern\w*|ersetz\w*|anpass\w*)\b|"
    r"\b(?:möchte|will|soll)\w*\b.{0,45}\b(?:ein\s+)?(?:anderes?|neues?)\s+"
    r"(?:struktur|aufbau|design|layout|formatierung)\b|"
    r"\b(?:gib|mach)\w*\b.{0,45}\b(?:ein\s+)?(?:anderes?|neues?)\s+"
    r"(?:struktur|aufbau|design|layout|formatierung)\b",
    re.IGNORECASE | re.DOTALL,
)
_ALL_FILES = re.compile(
    r"\b(?:von\s+)?(?:allen?|sämtlichen?|jeglichen?)\s+"
    r"(?:(?:markdown|md)[- ]?)?(?:dateien|notizen|readme(?:s|-dateien)?)\b|"
    r"\b(?:im|für\s+den)\s+(?:gesamten?|ganzen?)\s+vault\b|"
    r"\bvaultweit\b|"
    r"\b(?:alle|aller|sämtliche|sämtlicher)\s+(?:mds|markdowns)\b",
    re.IGNORECASE,
)
_SCOPE_ONLY = re.compile(
    r"^\s*(?:von\s+)?(?:allen?|sämtlichen?|jeglichen?)\s+"
    r"(?:(?:markdown|md)[- ]?)?(?:dateien|notizen|readme(?:s|-dateien)?)\s*[.!?]*\s*$",
    re.IGNORECASE,
)
_REMOVE_EMOJIS = re.compile(
    r"\b(?:entfern\w*|lösch\w*|nimm\w*.{0,12}(?:raus|weg)|ohne)\b"
    r".{0,45}\bemoj\w*\b|\bemoj\w*\b.{0,35}\b(?:entfern\w*|lösch\w*|weg)\b",
    re.IGNORECASE | re.DOTALL,
)
_FIX_RELATIVE_LINKS = re.compile(
    r"\b(?:ersetz\w*|änder\w*|korrigier\w*|reparier\w*|verbesser\w*)\b.{0,55}"
    r"\b(?:relative\w*\s+)?(?:wiki)?links?|verlinkung\w*\b|"
    r"\brelative\w*\s+(?:wiki)?links?\b",
    re.IGNORECASE | re.DOTALL,
)
_ORGANIZE_VAULT_FILES = re.compile(
    r"\b(?:mach\w*|erstell\w*|nutz\w*|verwend\w*|verschieb\w*|sortier\w*|"
    r"ordn\w*|pack\w*|leg\w*)\b.{0,60}\bunterordner\w*\b.{0,35}"
    r"\b(?:datei\w*|pdfs?|dokument\w*|anhäng\w*)\b|"
    r"\b(?:datei\w*|pdfs?|dokument\w*|anhäng\w*)\b.{0,65}"
    r"\b(?:in|unter)\b.{0,20}\bunterordner\w*\b|"
    r"\bpdfs?\b.{0,55}\bnicht\b.{0,35}\b(?:gleich\w*\s+ebene|neben)\b"
    r".{0,25}\b(?:md|markdown|notiz\w*)\b",
    re.IGNORECASE | re.DOTALL,
)
_FULL_REWRITE = re.compile(
    r"\b(?:umstrukturier\w*|neustrukturier\w*|komplett\w*.{0,20}"
    r"(?:überarbeit\w*|neu\s+schreib\w*)|(?:ein\s+)?(?:anderes?|neues?)\s+"
    r"(?:struktur|design|layout|aufbau|formatierung)|"
    r"gesamten?\s+text.{0,20}(?:überarbeit\w*|änder\w*)|"
    r"(?:design|layout|aufbau|struktur).{0,25}(?:grundlegend|komplett|vollständig|neu)|"
    r"(?:grundlegend|komplett|vollständig).{0,15}(?:design|layout|aufbau|struktur))\b",
    re.IGNORECASE | re.DOTALL,
)
_ARCHIVE = re.compile(
    r"\b(?:einsortier\w*|ableg\w*|archivier\w*|übernimm\w*|importier\w*|"
    r"in\s+(?:den\s+)?vault|in\s+die\s+(?:notiz|dokumentation)|"
    r"sort\w*.{0,20}(?:datei|anhang)|store|archive|file)\b",
    re.IGNORECASE | re.DOTALL,
)
# Ausdrückliche Ausnahmen: Der Anhang soll NICHT in den Vault übernommen werden.
# Bewusst eng gefasst — im Zweifel wird abgelegt.
_NO_ARCHIVE = re.compile(
    r"\b(?:nicht|kein\w*|ohne|keinesfalls|niemals)\b[^.!?]{0,45}"
    r"\b(?:hochlad\w*|hochzuladen|ablad\w*|ableg\w*|abzulegen|speicher\w*|"
    r"zu\s+speichern|sicher\w*|einsortier\w*|einzusortieren|sortier\w*|"
    r"übernehm\w*|übernommen|zu\s+übernehmen|importier\w*|kopier\w*|"
    r"archivier\w*|hinzufüg\w*)\b|"
    r"\b(?:nur|lediglich|bloß|blos|einfach)\b[^.!?]{0,30}"
    r"\b(?:anschau\w*|anzuschauen|ansehen|anseh\w*|angucken|guck\w*|"
    r"betracht\w*|zu\s+betrachten|les\w*|zu\s+lesen|auslesen|analysier\w*|"
    r"zu\s+analysieren|auswert\w*|prüf\w*|check\w*|beschreib\w*)\b|"
    r"\b(?:anschau\w*|ansehen|betracht\w*|les\w*|analysier\w*|auswert\w*)\b"
    r"[^.!?]{0,20}\b(?:nur|lediglich|bloß|blos)\b|"
    r"\bnicht\b[^.!?]{0,30}\b(?:in\s+den\s+vault|im\s+vault)\b|"
    # Trennbare Verben: "Schau dir das nur an", "Werte das Bild nur aus".
    # Das "nur" muss unmittelbar vor der Partikel stehen, damit
    # "Lies die PDF und erstelle nur eine Notiz" nicht falsch greift.
    r"\b(?:schau|sieh|guck|werte|lies|les|hör)\w*\b[^.!?]{0,35}"
    r"\bnur\b\s+(?:kurz\s+|schnell\s+|einmal\s+)?(?:an|aus|durch|rein)\b|"
    r"\b(?:don\'?t|do\s+not)\b[^.!?]{0,25}\b(?:upload|save|store|import|file)\b|"
    r"\bonly\b[^.!?]{0,25}\b(?:look|view|read|analy[sz]e|describe)\b",
    re.IGNORECASE,
)

_HOW_TO = re.compile(
    r"^\s*(?:wie\s+(?:kann|würde|soll)\s+(?:ich|man)|erklär\w*\s+mir,?\s+wie|"
    r"how\s+(?:can|do|would)\s+i)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ActionRequirements:
    """Mindestresultat einer konkreten Nutzeranfrage."""

    note_write: bool = False
    mode: str = ""  # create | update | edit | organise
    requires_edit: bool = False
    allow_full_rewrite: bool = False
    edit_all_notes: bool = False
    batch_edit_operations: tuple[str, ...] = ()
    organize_vault_files: bool = False
    file_subfolder: str = "Dateien"
    archive_attachments: bool = False
    keep_out_of_vault: bool = False
    attachment_names: tuple[str, ...] = ()

    @property
    def actionable(self) -> bool:
        return (self.note_write or self.organize_vault_files
                or self.archive_attachments or self.keep_out_of_vault)

    @property
    def requires_batch_edit(self) -> bool:
        return self.requires_edit and self.edit_all_notes and bool(self.batch_edit_operations)

    def contract(self) -> str:
        if not self.actionable:
            return ""
        actions = []
        if self.organize_vault_files:
            actions.append(
                "vorhandene PDFs, Dokumente und Bilder, die direkt neben Markdown-"
                f"Notizen liegen, in den Unterordner '{self.file_subfolder}' desselben "
                "Themenordners verschieben und alle betroffenen Links auf die neuen "
                "tatsächlichen Vault-Pfade aktualisieren. Nutze dafür einmal "
                "dateien_in_unterordner_verschieben"
            )
        if self.requires_batch_edit:
            labels = {
                "remove_emojis": "sämtliche Emojis entfernen",
                "fix_relative_links": (
                    "sämtliche relativen Markdown- und WikiLinks auf tatsächlich "
                    "vorhandene vollständige Vault-Ziele umstellen"
                ),
            }
            operations = "; ".join(labels[item] for item in self.batch_edit_operations)
            actions.append(
                "alle Markdown-Dateien im ausdrücklich genannten Umfang vollständig prüfen und in einem "
                f"Stapel bearbeiten: {operations}. Nutze dafür "
                "markdown_dateien_bereinigen; Suchtreffer sind keine Begrenzung des Umfangs"
            )
        elif self.requires_edit:
            actions.append(
                "die betroffene bestehende Notiz zuerst vollständig lesen und nur "
                "die ausdrücklich verlangte Textstelle, den Abschnitt oder die "
                "Struktur bearbeiten; alle nicht betroffenen Inhalte erhalten"
            )
        elif self.note_write:
            actions.append(
                "eine vollständige, inhaltlich geprüfte Markdown-Notiz im Vault "
                "erstellen oder die passende bestehende Notiz ergänzen"
            )
        if self.keep_out_of_vault:
            actions.append(
                "die angehängten Dateien NUR auswerten und beantworten. Sie dürfen "
                "ausdrücklich NICHT in den Vault kopiert werden — rufe "
                "anhang_in_vault_ablegen nicht auf"
            )
        elif self.archive_attachments:
            actions.append(
                "alle angehängten Originaldateien in einen inhaltlich passenden "
                "Vault-Ordner kopieren"
            )
            actions.append(
                "die tatsächlich zurückgegebenen Vault-Pfade in der Notiz als "
                "Obsidian-WikiLinks erwähnen"
            )
        return (
            "VERBINDLICHES ERGEBNIS DIESES AUFTRAGS:\n- "
            + "\n- ".join(actions)
            + "\nEine Beschreibung, ein Markdown-Entwurf nur im Chat oder eine "
              "Rückfrage nach Erlaubnis erfüllt den Auftrag nicht. Nutze die Werkzeuge "
              "jetzt und antworte erst, wenn die Änderungen wirklich erfolgt sind."
        )

    def correction(self, missing: Iterable[str]) -> str:
        labels = {
            "note": "Die Notiz wurde noch nicht im Vault erstellt oder ergänzt.",
            "attachments": "Noch nicht alle Originalanhänge wurden in den Vault kopiert.",
            "links": "Die gespeicherten Anhänge sind noch nicht mit ihren echten Pfaden verlinkt.",
            "edit": "Die ausdrücklich verlangte Änderung wurde noch nicht an der bestehenden Notiz ausgeführt.",
            "batch_edit": (
                "Die Änderung wurde noch nicht über alle Markdown-Dateien "
                "des genannten Umfangs ausgeführt. Einzelne bearbeitete Dateien genügen nicht."
            ),
            "organize_files": (
                "Die ausdrücklich verlangte Dateiordnung wurde noch nicht ausgeführt. "
                "Eine Beschreibung der Zielstruktur oder die Behauptung, Dateien nicht "
                "verschieben zu können, genügt nicht."
            ),
        }
        details = " ".join(labels.get(item, item) for item in missing)
        return (
            "AUFTRAG NOCH NICHT ERLEDIGT. " + details + " "
            "Führe die fehlenden Schreibwerkzeuge jetzt aus. Wiederhole keinen bloßen "
            "Entwurf und kündige die Arbeit nicht nur an."
        )


def analyse_request(
    text: str,
    attachment_names: Iterable[str] = (),
    context_messages: Iterable[str] = (),
) -> ActionRequirements:
    """Leitet nur aus eindeutigen Formulierungen verpflichtende Aktionen ab.

    Erklärfragen wie "Wie kann ich eine Notiz erstellen?" bleiben normale
    Wissensfragen. Bei einem Schreibauftrag mit Anhängen gehören die Originale
    dagegen automatisch zur entstehenden Obsidian-Dokumentation.
    """
    value = " ".join((text or "").split())
    names = tuple(str(name) for name in attachment_names if str(name).strip())
    if not value or _HOW_TO.search(value):
        return ActionRequirements(attachment_names=names)

    previous = [" ".join(str(item).split()) for item in context_messages if str(item).strip()]
    action_value = value
    scope_value = value

    # Kurze Folgeaufträge behalten die bereits erteilte Änderungsfreigabe. Eine
    # unmittelbar vorherige Reichweite wie „Von allen Dateien“ gilt ebenso für
    # den folgenden konkret formulierten Änderungsauftrag.
    if _EDIT.search(value):
        if previous and _SCOPE_ONLY.search(previous[-1]):
            scope_value = f"{previous[-1]} {value}"
    elif _SCOPE_ONLY.search(value):
        for earlier in reversed(previous[-6:]):
            if _EDIT.search(earlier):
                action_value = f"{earlier} {value}"
                scope_value = action_value
                break

    update = bool(_UPDATE.search(action_value))
    edit = bool(_EDIT.search(action_value))
    full_rewrite = bool(edit and _FULL_REWRITE.search(action_value))
    edit_all = bool(edit and _ALL_FILES.search(scope_value))
    batch_operations = []
    if edit_all and _REMOVE_EMOJIS.search(action_value):
        batch_operations.append("remove_emojis")
    if edit_all and _FIX_RELATIVE_LINKS.search(action_value):
        batch_operations.append("fix_relative_links")
    organize_vault_files = bool(_ORGANIZE_VAULT_FILES.search(value))
    create = bool(_CREATE.search(value))

    # Angehängte Dateien gehören standardmäßig in den Vault. Nur eine
    # ausdrückliche Formulierung wie "nur anschauen" oder "nicht hochladen"
    # verhindert das.
    keep_out = bool(names and _NO_ARCHIVE.search(value))
    archive = bool(names) and not keep_out

    # "Sortiere die Dateien ein" braucht ebenfalls eine kleine Indexnotiz, weil
    # der Nutzer die Dateien ausdrücklich im Text erwähnt und verlinkt haben will.
    organise = bool(names and _ARCHIVE.search(value))
    note_write = create or update or edit or organise
    mode = (
        "edit" if edit else "update" if update else
        "organise" if organise and not create else "create" if create else ""
    )
    return ActionRequirements(
        note_write=note_write,
        mode=mode,
        requires_edit=edit,
        allow_full_rewrite=full_rewrite,
        edit_all_notes=edit_all,
        batch_edit_operations=tuple(batch_operations),
        organize_vault_files=organize_vault_files,
        archive_attachments=archive,
        keep_out_of_vault=keep_out,
        attachment_names=names,
    )


def note_title(text: str, fallback: str = "Neue Wissensnotiz") -> str:
    """Erzeugt nur für den seltenen Sicherheits-Fallback einen lesbaren Titel."""
    value = " ".join((text or "").replace("\n", " ").split())
    value = re.sub(
        r"^(?:bitte\s+)?(?:erstell\w*|anleg\w*|verfass\w*|schreib\w*|"
        r"dokumentier\w*|ergänz\w*|erweiter\w*|sortier\w*)\s+(?:mir\s+)?",
        "", value, flags=re.IGNORECASE,
    )
    value = re.sub(r"\b(?:eine|einen|die|das)\s+(?:notiz|dokumentation|übersicht)\s+(?:zu|über)\s+", "", value,
                   flags=re.IGNORECASE)
    value = value.strip(" .,:;!?\"'")
    if len(value) > 72:
        value = value[:72].rsplit(" ", 1)[0]
    return value or fallback


def simple_root_note(prompt: str) -> str | None:
    """Only a complete, unambiguous create command without content instructions."""
    match = re.fullmatch(
        r'\s*(?:bitte\s+)?(?:lege|erstelle)\s+(?:eine?\s+)?(?:test\s+)?'
        r'["„]([\w -]+(?:\.md)?)["“]\s+(?:(?:md|markdown)[- ]*)?datei\s+'
        r'(?:an\s+)?(?:im\s+(?:obersten|obersten\s+vault-)\s*ordner|im\s+hauptordner|'
        r'im\s+vault-root)(?:\s+an)?\s*[.!]?\s*',
        prompt, re.IGNORECASE,
    )
    if not match:
        return None
    name = match.group(1).strip()
    if not name or name.casefold() in {'00 inhalt', '00 inhalt.md'}:
        return None
    return name if name.lower().endswith('.md') else name + '.md'


def simple_attachment_archive(prompt: str) -> str | None:
    """Nur vollständige reine Ablagebefehle; '' bedeutet Standard-Anhangordner.

    Ein explizites Ziel muss in Anführungszeichen stehen. Inhaltliche Aufträge,
    Negationen, einzelne ausgewählte Dateien und Folgeaktionen gehen ans Modell.
    """
    if re.fullmatch(
        r'\s*(?:bitte\s+)?(?:die\s+|alle\s+)?(?:datei(?:en)?|anhänge|bilder)'
        r'\s+(?:(?:einfach|nur|schnell)\s+)*(?:ablegen|speichern|kopieren)\s*[.!]?\s*',
        prompt, re.IGNORECASE,
    ):
        return ""
    match = re.fullmatch(
        r'\s*(?:bitte\s+)?(?:speichere?|kopiere?|archiviere?|lege?)\s+'
        r'(?:(?:die|das|den|diese|dieses|diesen|alle|meine)\s+)?(?:angehängte[nrs]?\s+)?'
        r'(?:datei(?:en)?|anhänge|anhang|bilder|bild|uploads?)'
        r'(?:\s+(?:bitte|einfach|nur|schnell))*'
        r'(?:\s+ab)?'
        r'(?:\s+(?:im|in den|in dem|in)\s+(?:vault|wissensordner)|'
        r'\s+(?:im|in den|in dem|in)\s+(?:ordner\s+)?["„]([^"“\n]+)["“])?'
        r'(?:\s+ab)?\s*[.!]?\s*', prompt, re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1).strip() if match.group(1) is not None else ""
