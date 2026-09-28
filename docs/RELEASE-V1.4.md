# KnowHow Tool V1.4

## Geschwindigkeit und Richtigkeit (Funktion A)

- Ursache langsamer, unpräziser Wissensfragen: Die Volltextsuche verknüpfte alle
  Wörter mit ODER, auch „was“, „ist“ und „die“. Nahezu jede Frage erhielt bis zu
  sechs beliebige Auszüge, der Prompt wurde groß und „kein Treffer“ trat nie ein.
  Zusätzlich wurde vor jeder Frage der gesamte Vault synchron abgeglichen.
- Jetzt: Suchbegriffe ohne Füllwörter, Relevanzschwelle (Begriffsabdeckung oder
  semantische Ähnlichkeit), kein synchroner Abgleich bei laufendem
  Hintergrundindex, Verlauf auf etwa 8.000 Zeichen begrenzt.
- Ohne passenden Treffer setzt die Anwendung `Kein Eintrag gefunden – KI-Wissen:`
  vor die Antwort. Mit Treffern werden fehlende Quellenlinks `[[Pfad]]` ergänzt.
- Antwortregeln: direkt, Länge nach Frage und Vorgabe, Form nach Inhalt.
- Arbeitschat: identische Lese-/Such-/Bildaufrufe werden nicht wiederholt,
  höchstens zwei Suchläufe je Auftrag.

## Varianten-Modus (Funktion C)

- Schalter „Varianten“ im Arbeitschat, standardmäßig aus. Er wirkt nur bei Schreib-,
  Ergänzungs- oder Änderungsaufträgen; einfache Nachrichten laufen normal.
- Drei werkzeugfreie Modellaufrufe ohne Thinking: Strikt, Strukturiert, Erweitert.
  Ziel ist eine genannte bestehende Notiz oder ein Vorschlag unter `02 KI-Notizen/`.
- Nichts wird vor der Wahl gespeichert. **Übernehmen** ersetzt die Zielnotiz (nur wenn
  sie seitdem unverändert ist) oder legt eine nummerierte neue Notiz an; der Vorgang ist
  über „Letzten Vault-Auftrag rückgängig“ zurücknehmbar. **Ändern** überarbeitet die
  gewählte Fassung nach einem eigenen Wunsch.

## Struktur nach Inhalt (Funktion F)

- Feste Regel im Schreibkontext und in den Antwortregeln: Fakten → Stichpunkte,
  Vergleiche → Tabelle, Abläufe → nummerierte Schritte, Themen → Überschriften,
  Begriffe → Definition, verwandte Notizen → interne Links.

## Notizen, Bilder, Dateien (Funktion E)

- **Notizen:** Schnellerfassung mit Titel, optionalem Ordner und Text; sofort gespeichert,
  Namenskonflikte nummeriert. „Speichern + KI strukturieren“ und „Mit KI überarbeiten“
  öffnen einen Arbeitschat mit vorbereitetem Auftrag (vor dem Senden änderbar, Varianten
  zuschaltbar).
- **Bilder:** Ablagefläche für Ziehen, Strg+V und Auswahl; Filter, Einbettung kopieren
  (`![[…]]`) und „Mit KI auswerten“. Letzteres hängt die Vault-Datei an einen neuen Chat,
  ohne sie im Vault zu duplizieren.
- **Dateien:** Hochladen-Knopf und Ablegen von Explorer-Dateien direkt auf einen Ordner.
- Navigation in Arbeitsreihenfolge: Wissen fragen, Wissen erweitern, Notizen, Bilder, Dateien.
- Neue Endpunkte: `POST /api/files/upload` (Ordner optional, Standard Anhangordner) und
  `POST /api/attachments/{chat}/from-vault`.

## Behobene Fehler

- Die Chat-Ansicht meldete ihre Drop-Listener auf dem dauerhaften Hauptbereich nie ab.
  Spätere Drops in anderen Ansichten wurden zusätzlich in den zuletzt geöffneten Chat
  hochgeladen (seit der direkten Vault-Ablage mit zusätzlicher Vault-Kopie); nach mehreren
  Chat-Besuchen mehrfach. Die Listener werden jetzt beim Verlassen entfernt.
- Fehlt die mitgelieferte `Obsidian_Syntax.md`, wird der Vault trotzdem eingerichtet.

## Prüfung

208 Python-Tests bestanden (neu: Suchbegriffe, Relevanz, KI-Wissen-Kennzeichnung,
Quellenlinks, Verlaufsgrenze, Doppelaufrufe, Varianten samt Übernahme, Konflikt, Rücknahme
und Überarbeitung, Tab-Ablage, Anhang aus dem Vault). JavaScript-Modulsyntax geprüft. In
einer isolierten Instanz mit Test-Vault und simuliertem Ollama wurden Fragen mit und ohne
Treffer, alle drei Varianten, Übernehmen, Ändern, Schnellerfassung, Bild- und Dateiablage
im Browser durchgespielt. Echte Qwen-Laufzeiten hängen weiter von Hardware und Modell ab.

## Ablage und Oberfläche

- Markdown- und Obsidian-Grundregeln sind fest im Systemkontext. Seltene Syntax steht in `Obsidian_Syntax.md`, die für jeden Vault einmalig angelegt und nur bei Bedarf gelesen wird. Eigene Änderungen daran bleiben erhalten.
- „Als Notiz speichern“ legt die Antwort sofort als Markdown-Datei an. Namenskonflikte werden atomar mit `Notiz1.md`, `Notiz2.md` usw. gelöst; vorhandene Dateien bleiben unverändert.
- Uploads liegen sofort im konfigurierten Anhangordner des Vaults. Die Chat-Kopie bleibt für KI-Auswertung verfügbar. Gleiche Namen werden nummeriert. Entfernen aus dem Chat löscht die Vault-Datei nicht.
- Navigation und Einstellungen zeigen häufige Aufgaben zuerst. Seltene Bereiche stehen unter „Erweitert“. Doppelte Schalter, die wirkungslose Telemetrie-Anzeige und die unbenutzte Datei `soon.js` wurden entfernt.
