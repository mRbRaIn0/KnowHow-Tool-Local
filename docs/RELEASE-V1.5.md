# KnowHow Tool V1.5

Stand: 29.09.2026

## Änderungen

- **Suchbereich (Funktion M).** Zwischen Modell und Thinking wählt ein Dropdown den
  Vault-Ordner für die Suche. Standard „Alle Ordner“. Die Ordnerliste stammt aus dem
  Dateiindex des Vaults, Unterordner werden mitdurchsucht. Die Auswahl gilt für den aktuellen
  Chat (bis zum Neuladen). Die Kontextspalte zeigt den aktiven Bereich, der Suchschritt
  „N Treffer · in IT/Azure“.
- **Kein Eintrag gefunden (Funktion J).** Der Hinweis wird ausschließlich von der Oberfläche
  erzeugt (aus dem Suchergebnis) und erscheint einmal über der Antwort. Er steht nicht mehr im
  Prompt oder im gespeicherten Antworttext. Wiederholt das Modell ihn dennoch, entfernt ein
  Filter die Zeile, bevor sie sichtbar wird.
- **Modell-Info ohne „null“ (Funktion I).** Ursache: `Element.append(null)` schreibt das Wort
  „null“ in die Seite. Betroffen war die letzte Zeile der Kontextspalte im Fragen-Chat, ebenso
  die Einstellungen (Ollama läuft) und die Übersicht (keine Fähigkeiten). Neue Helfer `fill`
  und `kv` lassen leere Werte komplett weg.
- **Varianten als Schalter (Funktion L)**, gleich gestaltet wie Thinking, standardmäßig aus.
- **Markdown-Spickzettel (Funktion K)** in der Seitenleiste der Notizen mit allen Bausteinen
  aus dem Plan. Kopieren je Block oder komplett, Einfügen an der Cursorposition der
  Schnellerfassung. Beispieltexte sind übersetzt.
- **Chat-Kontextmenü (Funktion H):** Zu Ordner hinzufügen (Ordnerauswahl, „Kein Ordner“,
  „Neuer Ordner …“), Archivieren bzw. Aus dem Archiv holen, Chat löschen. Tastatur:
  Kontextmenütaste bzw. Umschalt+F10, Pfeiltasten, Escape. Löschen fragt in einem eigenen
  Dialog nach; die Schaltfläche ist dauerhaft rot.
- **Sprache Deutsch/English (Funktionen N, O).** Neuer Block „Sprache“ unter den
  Konfigurationsblöcken. Alle Oberflächentexte stehen in `frontend/i18n/de.json` und
  `en.json` (rund 550 Schlüssel; ein Test stellt gleiche Schlüssel, gleiche Platzhalter und
  echtes Englisch sicher). Der Server übersetzt seine Bestätigungen und bekannten Fehlermeldungen
  (`backend/i18n.py`); die KI antwortet in der gewählten Sprache. Umschalten lädt die Seite neu.
- Vault-Index `00 Inhalt.md` und `Obsidian_Syntax.md` sind bei Wissensfragen keine Quelle mehr.

## Prüfung

Automatisierte Tests: 241 bestanden (neu: Sprachdateien, Suchbereich, Hinweis-Filter,
englische Serverantworten, Spracheinstellung, englische Standardaufträge). JavaScript-Syntax
geprüft. In einer isolierten Instanz mit Test-Vault und simuliertem Ollama im Browser
durchgespielt, jeweils auf Deutsch und Englisch: Fragen mit und ohne Treffer, doppelter
Hinweis durch das Modell, Suchbereich `IT/Azure`, Varianten-Schalter samt Auswahl,
Rechtsklickmenü, neuer Ordner, Löschdialog, Spickzettel (Kopieren, Einfügen, Ein-/Ausklappen),
Sprachwechsel mit Neuladen. Eine automatische Durchsicht aller Ansichten fand im englischen
Modus keine deutschen Oberflächentexte.

## Grenzen

- Die mitgelieferten Notizvorlagen und Vault-Inhalte bleiben in ihrer Sprache (deutsch).
- Direkte Dateibefehle wie „Füge diesen Text zu … hinzu“ sind deutsch. Freie englische
  Aufträge werden nur teilweise als Schreibauftrag erkannt; die vorbereiteten Aufträge der
  Oberfläche funktionieren in beiden Sprachen.
- Die Antwortgeschwindigkeit von Qwen hängt weiter von Hardware, Modell und Thinking ab. Ein
  kleinerer Suchbereich verringert vor allem Suchaufwand und Kontextgröße.
- Update: Anwendung schließen und den vorhandenen `data`-Ordner behalten.
