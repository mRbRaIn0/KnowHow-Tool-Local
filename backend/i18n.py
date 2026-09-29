"""Sprache der Oberfläche (de/en) für Texte, die der Server selbst erzeugt.

Die Oberfläche übersetzt ihre eigenen Texte über frontend/i18n/*.json. Hier stehen
nur Meldungen, die im Backend entstehen und dem Nutzer angezeigt oder im Chat
gespeichert werden: Bestätigungen, Fehler, Zwischenstände und die Sprachregel
für das Modell. Deutsch ist die Grundsprache; Englisch wird bei Bedarf gewählt.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Tuple

from .config import store


def language() -> str:
    try:
        return store.config.ui.language
    except Exception:  # Konfiguration nicht ladbar: Grundsprache
        return "de"


# Schlüssel -> (Deutsch, Englisch)
MESSAGES: Dict[str, Tuple[str, str]] = {
    "sources": ("Quellen", "Sources"),
    "chat.new": ("Neuer Chat", "New chat"),
    "work.unfinished": (
        "Bearbeitung noch nicht abgeschlossen. Gespeicherte Arbeitsnotizen und Aktionen können im selben Chat fortgesetzt werden.",
        "Processing not finished yet. Saved working notes and actions can be continued in the same chat."),
    "work.rollbackFailed": ("Rücknahme fehlgeschlagen: {error}. ", "Undo failed: {error}. "),
    "work.fileTaskInterrupted": (
        "Dateiauftrag unterbrochen; bestätigte Änderungen bleiben rücknehmbar.",
        "File task interrupted; confirmed changes can still be undone."),
    "work.stored": ("Abgelegt: {embed}", "Stored: {embed}"),
    "work.notStored": ("Nicht abgelegt: {name} — {error}", "Not stored: {name} — {error}"),
    "work.searchInterrupted": (
        "Wissenssuche unterbrochen; noch keine neuen Dateiaktionen ausgeführt.",
        "Knowledge search interrupted; no new file actions have been executed yet."),
    "work.analysisInterrupted": (
        "Auswertung unterbrochen. Bereits gelesene Dateien und Seiten sind zwischengespeichert; beim Fortsetzen werden sie wiederverwendet.",
        "Analysis interrupted. Files and pages already read are cached and will be reused when continuing."),
    "work.analysisFailed": ("Auswertung konnte nicht abgeschlossen werden: {error}", "The analysis could not be completed: {error}"),
    "work.variantsInterrupted": ("Variantenerstellung unterbrochen: {error}", "Variant creation interrupted: {error}"),
    "work.variantsCancelled": (
        "Variantenerstellung unterbrochen. Es wurde nichts gespeichert.",
        "Variant creation interrupted. Nothing was saved."),
    "work.fileCreated": ("Datei erstellt: [[{path}]]", "File created: [[{path}]]"),
    "work.noFinalAnswer": ("Das Modell hat keine abschließende Antwort geliefert.", "The model did not deliver a final answer."),
    "work.noFinalAnswer2": ("Keine abschließende Modellantwort erhalten.", "No final model answer received."),
    "work.modelInterrupted": ("Modellantwort unterbrochen: {error}", "Model answer interrupted: {error}"),
    "work.processingInterrupted": ("Bearbeitung unterbrochen: {error}", "Processing interrupted: {error}"),
    "work.answerInterrupted": (
        "Antwort unterbrochen. Gespeicherte Arbeitsnotizen und bestätigte Aktionen bleiben für die nächste Nachricht erhalten.",
        "Answer interrupted. Saved working notes and confirmed actions are kept for the next message."),
    "work.noFileYet": (
        "In diesem Durchlauf wurde noch keine Vault-Datei erstellt oder geändert.",
        "No vault file has been created or changed in this run yet."),
    "work.notFullyDone": (
        "Der angeforderte Vault-Auftrag konnte nicht vollständig ausgeführt werden.",
        "The requested vault task could not be completed fully."),
    "work.savedOne": ("Im Vault gespeichert: `{path}`", "Saved in the vault: `{path}`"),
    "work.savedMany": ("Im Vault gespeichert:", "Saved in the vault:"),
    "work.globalDone": ("Der globale Vault-Auftrag wurde ausgeführt.", "The global vault task was executed."),
    "work.batchIncomplete": (
        "Die globale Vault-Bearbeitung konnte nicht vollständig abgeschlossen werden.",
        "The global vault edit could not be completed fully."),
    "work.organizeIncomplete": (
        "Die verlangte Dateiordnung konnte trotz der automatischen Fortsetzung nicht vollständig ausgeführt werden. Es wurden keine unbestätigten Ersatzänderungen vorgenommen.",
        "The requested file organisation could not be completed fully despite the automatic continuation. No unconfirmed substitute changes were made."),
    "work.editIncomplete": (
        "Die bestehende Notiz wurde nicht pauschal überschrieben, weil die verlangte Änderung nicht sicher genug abgegrenzt werden konnte.",
        "The existing note was not overwritten wholesale because the requested change could not be delimited safely enough."),
    "batch.done": (
        "Fertig. Alle {n} Markdown-Dateien im beauftragten Umfang wurden geprüft.",
        "Done. All {n} Markdown files in the requested scope were checked."),
    "batch.changed": ("Geändert: {n}", "Changed: {n}"),
    "batch.unchanged": ("Unverändert: {n}", "Unchanged: {n}"),
    "batch.executed": ("Ausgeführt: {ops}", "Executed: {ops}"),
    "batch.emojis": ("Emojis entfernt", "Emojis removed"),
    "batch.links": (
        "relative Links und Ordner-WikiLinks auf vorhandene Notizen normalisiert",
        "relative links and folder wiki links normalised to existing notes"),
    "batch.files": ("Bearbeitete Dateien:", "Edited files:"),
    "batch.unresolved": ("Nicht auflösbare Links: {n}", "Unresolvable links: {n}"),
    "org.done": ("Fertig. {n} PDF-, Dokument- und Bilddateien wurden geprüft.", "Done. {n} PDF, document and image files were checked."),
    "org.moved": ("In den Unterordner `{folder}` verschoben: {n}", "Moved to the subfolder `{folder}`: {n}"),
    "org.already": ("Bereits passend eingeordnet: {n}", "Already filed correctly: {n}"),
    "org.notes": ("Notizen mit aktualisierten Links: {n}", "Notes with updated links: {n}"),
    "org.newPaths": ("Neue Vault-Pfade:", "New vault paths:"),
    "org.rule": (
        "Die dauerhafte Ablageregel wurde außerdem in `{path}` ergänzt.",
        "The permanent filing rule was also added to `{path}`."),
    "undo.history": ("Der letzte Vault-Auftrag wurde rückgängig gemacht.", "The last vault task was undone."),
    "undo.message": (
        "Der letzte Vault-Auftrag wurde rückgängig gemacht. Zurückgesetzte Dateien: {paths}",
        "The last vault task was undone. Restored files: {paths}"),
    "history.interrupted": (
        "Antwort unterbrochen. Gespeicherte Arbeitsnotizen bei Bedarf gezielt laden.",
        "Answer interrupted. Load saved working notes selectively if needed."),
    "preview.cancelled": (
        "Schreibvorschau abgebrochen. Keine weiteren Aktionen ausgeführt.",
        "Write preview cancelled. No further actions were executed."),
    "preview.rolledBack": (" Bereits ausgeführte Dateiänderungen wurden zurückgenommen.", " File changes already made were rolled back."),
    "preview.rollbackFailed": (
        "{text} Rücknahme nicht möglich: {error}. Bereits ausgeführte Änderungen bleiben erhalten.",
        "{text} Undo not possible: {error}. Changes already made are kept."),
    "variants.summaryRefined": ("Überarbeitete Fassung für `{path}` erstellt.", "Revised version for `{path}` created."),
    "variants.summaryMany": ("{n} Varianten für `{path}` erstellt.", "{n} variants for `{path}` created."),
    "variants.notSaved": (
        " Noch nichts gespeichert: Variante wählen und übernehmen oder ändern.",
        " Nothing saved yet: choose a variant and apply or edit it."),
    "variants.applied": ("{title} übernommen: [[{path}]]", "{title} applied: [[{path}]]"),
    "variants.strict": ("Variante 1 – Strikt", "Variant 1 – Strict"),
    "variants.structured": ("Variante 2 – Strukturiert", "Variant 2 – Structured"),
    "variants.extended": ("Variante 3 – Erweitert", "Variant 3 – Extended"),
    "variants.refined": ("Überarbeitete Fassung", "Revised version"),
    "variants.conflict": (
        "Die Notiz wurde seit dem Erstellen der Varianten geändert. Bitte Varianten neu erstellen, damit keine Änderung verloren geht.",
        "The note was changed after the variants were created. Please create the variants again so no change is lost."),
    "context.full": (
        "Die Nutzereingaben dieses Chats umfassen {chars:,} Zeichen und überschreiten das aktuelle Eingabebudget von {budget:,} Zeichen. "
        "Alle Eingaben bleiben vollständig im Chat gespeichert. Es wurden keine Nutzerangaben stillschweigend weggelassen und keine neuen Dateiaktionen ausgeführt. "
        "Erhöhe die Kontextgröße in den KI-Einstellungen und sende anschließend ‚weiter‘. "
        "Falls das Modell keinen größeren Kontext unterstützt, müssen wir den Auftrag ausdrücklich in kleinere Teile aufteilen.",
        "The user inputs of this chat comprise {chars:,} characters and exceed the current input budget of {budget:,} characters. "
        "All inputs remain fully stored in the chat. No user details were silently dropped and no new file actions were executed. "
        "Increase the context size in the AI settings and then send ‘continue’. "
        "If the model does not support a larger context, we have to split the task into smaller parts explicitly."),
    "ollama.running": ("Ollama läuft bereits.", "Ollama is already running."),
    "ollama.notFound": ("ollama.exe wurde nicht gefunden. Bitte Ollama manuell starten.", "ollama.exe was not found. Please start Ollama manually."),
    "ollama.started": ("Ollama wurde gestartet.", "Ollama was started."),
    "ollama.startedSilent": ("Ollama wurde gestartet, antwortet aber noch nicht. Bitte kurz warten.", "Ollama was started but is not responding yet. Please wait a moment."),
}

# Antwortsprache des Modells; die Anweisungen selbst bleiben Deutsch.
LANGUAGE_RULE = {
    "de": "",
    "en": ("SPRACHE: Antworte ausschließlich auf Englisch. Notizen, Überschriften und Bestätigungen werden auf Englisch verfasst; "
           "Quellen, Dateinamen und Zitate bleiben unverändert."),
}


def bt(key: str, **params: Any) -> str:
    """Server-Text in der gewählten Sprache."""
    german, english = MESSAGES[key]
    text = english if language() == "en" else german
    return text.format(**params) if params else text


def language_rule() -> str:
    return LANGUAGE_RULE.get(language(), "")


def marker(*keys: str) -> Tuple[str, ...]:
    """Beide Sprachfassungen eines Textes, für Prüfungen wie 'enthält Rücknahme-Hinweis'."""
    return tuple(text for key in keys for text in MESSAGES[key])


# ------------------------------------------------ Bestehende deutsche Fehlermeldungen

_EXACT: Dict[str, str] = {
    "Backup nicht gefunden.": "Backup not found.",
    "Bitte den Pfad manuell eintragen.": "Please enter the path manually.",
    "Bitte einen Profilnamen angeben.": "Please enter a profile name.",
    "Bitte zuerst einen erreichbaren Vault auswählen.": "Please select a reachable vault first.",
    "Chat nicht gefunden.": "Chat not found.",
    "Arbeitschat nicht gefunden.": "Work chat not found.",
    "Datei nicht gefunden.": "File not found.",
    "Die Nachricht ist leer.": "The message is empty.",
    "Diese Varianten sind nicht mehr vorhanden.": "These variants no longer exist.",
    "Diese Vorschau ist nicht mehr aktuell.": "This preview is no longer current.",
    "Dieser Chat antwortet noch.": "This chat is still answering.",
    "Ein anderer Auftrag bearbeitet diesen Vault bereits.": "Another task is already working on this vault.",
    "Ein anderer Auftrag bearbeitet diesen Vault gerade.": "Another task is currently working on this vault.",
    "Es wurden keine Dateien übergeben.": "No files were provided.",
    "Löschen erfordert eine Bestätigung.": "Deleting requires confirmation.",
    "Ordner nicht gefunden.": "Folder not found.",
    "Profil nicht gefunden.": "Profile not found.",
    "Stopp ist angefordert; die laufende Anfrage wird noch beendet.": "Stop has been requested; the running request is still being ended.",
    "Unbekannte Sprache.": "Unknown language.",
    "Unbekannte Variante.": "Unknown variant.",
    "Unbekanntes Thema.": "Unknown theme.",
    "Datei konnte nicht als Text gelesen werden.": "The file could not be read as text.",
    "Die Anhänge dieses Chats sind zusammen zu groß.": "The attachments of this chat are too large together.",
    "Die Vault-Wurzel kann nicht gelöscht werden.": "The vault root cannot be deleted.",
    "Ein Ordner kann nicht in sich selbst verschoben werden.": "A folder cannot be moved into itself.",
    "Es ist kein Vault konfiguriert.": "No vault is configured.",
    "Ungültige Chat-Kennung.": "Invalid chat identifier.",
    "Bitte einen konkreten Dateinamen nennen.": "Please name a specific file name.",
    "Dateipfad und genannter Ordner widersprechen sich.": "The file path and the named folder contradict each other.",
    "Der anzuhängende Text ist leer.": "The text to append is empty.",
    "Textaktionen benötigen eine Markdown-Datei (.md).": "Text actions need a Markdown file (.md).",
    "Bei einer exakten Dateiaktion bleibt der angegebene Zielpfad verbindlich.": "For an exact file action the given target path stays binding.",
    "Zum Umbenennen nur den neuen Dateinamen angeben; für Ordnerwechsel „Verschiebe“ verwenden.": "To rename, give only the new file name; use “Move” to change folders.",
    "Ungültiges Rücknahmeprotokoll.": "Invalid undo log.",
    "Ein Vault-Auftrag läuft noch. Bitte zuerst beenden oder stoppen.": "A vault task is still running. Please finish or stop it first.",
    "Fehler beim Umgang mit Anhängen.": "Error while handling attachments.",
    "Schreibvorschau abgebrochen. Keine weiteren Aktionen ausgeführt.": "Write preview cancelled. No further actions were executed.",
}

# (Muster, englische Vorlage); \1 usw. verweisen auf Gruppen des Musters.
_PATTERNS = [
    (r"^Unerwarteter Fehler: (.*)$", r"Unexpected error: \1"),
    (r"^Anhänge gehören in .*", "Attachments belong in “Extend knowledge”. The question chat only reads from your knowledge base."),
    (r"^Der Ordnerdialog ist nicht verfügbar.*", "The folder dialog is not available (tkinter is missing). Please enter the path manually."),
    (r"^Im Offline-Modus sind nur lokale Ollama-Adressen erlaubt.*", "In offline mode only local Ollama addresses are allowed (localhost / 127.0.0.1)."),
    (r"^Der Vault ist lesbar, aber die Hauptdatei (.*)$", r"The vault is readable, but the main file \1"),
    (r"^Die Datei '(.*)' existiert bereits\.$", r"The file '\1' already exists."),
    (r"^'(.*)' existiert bereits\.$", r"'\1' already exists."),
    (r"^Der Ordner existiert nicht: (.*)$", r"The folder does not exist: \1"),
    (r"^Kein Ordner: (.*)$", r"Not a folder: \1"),
    (r"^Start fehlgeschlagen: (.*)$", r"Start failed: \1"),
    (r"^'(.*)' ist mit (\d+) MB zu groß \(erlaubt sind (\d+) MB\)\.$", r"'\1' is too large at \2 MB (\3 MB are allowed)."),
    (r"^Absoluter Pfad ist nicht erlaubt: (.*)$", r"Absolute paths are not allowed: \1"),
    (r"^Anhang '(.*)' gibt es nicht\.$", r"Attachment '\1' does not exist."),
    (r"^Datei ist zu groß für den Editor \((\d+) KB\)\.$", r"The file is too large for the editor (\1 KB)."),
    (r"^Datei nicht gefunden: (.*)$", r"File not found: \1"),
    (r"^Der Vault-Pfad existiert nicht: (.*)$", r"The vault path does not exist: \1"),
    (r"^Der Vault-Pfad ist kein Ordner: (.*)$", r"The vault path is not a folder: \1"),
    (r"^Eingebettetes Bild zu groß: (.*)$", r"Embedded image too large: \1"),
    (r"^Es sind höchstens (\d+) Anhänge je Eingabe möglich\.$", r"At most \1 attachments per input are possible."),
    (r"^Nicht gefunden: (.*)$", r"Not found: \1"),
    (r"^Ordner nicht lesbar: (.*)$", r"Folder not readable: \1"),
    (r"^Pfad ist ein Ordner: (.*)$", r"Path is a folder: \1"),
    (r"^Pfad liegt außerhalb des Vaults: (.*)$", r"Path is outside the vault: \1"),
    (r"^Pfad liegt außerhalb des Vaults\.$", "Path is outside the vault."),
    (r"^Ungültiger Anhang: (.*)$", r"Invalid attachment: \1"),
    (r"^Ungültiger Name: (.*)$", r"Invalid name: \1"),
    (r"^Ungültiger Pfad: (.*)$", r"Invalid path: \1"),
    (r"^Ziel existiert bereits: (.*)\. Keine Datei überschrieben\.$", r"Target already exists: \1. No file was overwritten."),
    (r"^Datei zwischenzeitlich verändert: (.*)$", r"File changed in the meantime: \1"),
    (r"^Rücknahme würde neuere Änderungen überschreiben: (.*)$", r"Undo would overwrite newer changes: \1"),
    (r"^Rücknahme-Sicherung ist unvollständig: (.*)$", r"Undo backup is incomplete: \1"),
    (r"^Kein reguläres Dateiziel: (.*)$", r"Not a regular file target: \1"),
    # Direkte Dateiaktionen
    (r"^Mehrere exakt passende Dateien: (.*)\. In welchem Ordner\? Antworte mit „Ordner <Pfad>“\.$",
     r"Several files match exactly: \1. Which folder? Answer with “Ordner <path>”."),
    (r"^Gefunden: (.*)$", r"Found: \1"),
    (r"^Keine exakt passende Datei: (.*)$", r"No exactly matching file: \1"),
    (r"^Welchen Text soll ich zu (\[\[.*\]\]) hinzufügen\? Antworte mit „Text: …“\.$",
     r"Which text should I append to \1? Answer with “Text: …”."),
    (r"^Die Datei (\[\[.*\]\]) existiert bereits\. Zum Ergänzen .*$",
     r"The file \1 already exists. To extend it, use “Füge diesen Text … hinzu”."),
    (r"^(\[\[.*\]\]) ergänzt\.$", r"\1 extended."),
    (r"^(\[\[.*\]\]) erstellt \(exakter Zielpfad war nicht vorhanden\)\.$", r"\1 created (the exact target path did not exist)."),
    (r"^(\[\[.*\]\]) erstellt\.$", r"\1 created."),
    (r"^Datei nicht gefunden: (.*)\. Keine Änderung vorgenommen\.$", r"File not found: \1. No change made."),
    (r"^Datei gelöscht: (.*)\. Über „Rückgängig“ wiederherstellbar\.$", r"File deleted: \1. Can be restored via “Undo”."),
    (r"^(\[\[.*\]\]) → (\[\[.*\]\])\. Links angepasst: (\d+)\.$", r"\1 → \2. Links adjusted: \3."),
    # Ollama
    (r"^Das Modell '(.*)' ist in Ollama nicht installiert\.$", r"The model '\1' is not installed in Ollama."),
    (r"^Das Embedding-Modell '(.*)' ist nicht installiert\.$", r"The embedding model '\1' is not installed."),
    (r"^Ollama ist unter (.*) nicht erreichbar\. Läuft der Ollama-Dienst\? \((.*)\)$", r"Ollama is not reachable at \1. Is the Ollama service running? (\2)"),
    (r"^Offline-Modus ist aktiv: Der Server '(.*)' ist nicht lokal und wurde blockiert\.$", r"Offline mode is active: the server '\1' is not local and was blocked."),
]
_COMPILED = [(re.compile(pattern, re.DOTALL), template) for pattern, template in _PATTERNS]


def localize(text: Any) -> Any:
    """Übersetzt eine bekannte deutsche Servermeldung; unbekannte Texte bleiben unverändert."""
    if language() != "en" or not isinstance(text, str) or not text:
        return text
    if text in _EXACT:
        return _EXACT[text]
    for pattern, template in _COMPILED:
        match = pattern.match(text)
        if match:
            return match.expand(template)
    return text


def localize_detail(detail: Any) -> Any:
    """Für HTTP-Fehler: Text oder {'message': …, 'kind': …}."""
    if isinstance(detail, str):
        return localize(detail)
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        return {**detail, "message": localize(detail["message"])}
    return detail
