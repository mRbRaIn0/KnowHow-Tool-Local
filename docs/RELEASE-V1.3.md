# KnowHow Tool V1.3

Stand: 17.09.2026

## Änderungen

- Reine Ablageaufträge werden direkt ausgeführt: kein Ollama-Aufruf, keine
  Vision-Auswertung, keine Wissenssuche und keine künstliche Begleitnotiz.
  Explizite Zielordner in Anführungszeichen werden übernommen; ansonsten gilt
  der konfigurierte Anhangordner. Inhaltliche und mehrdeutige Aufträge bleiben
  Modellaufgaben. Fehlgeschlagene Kopien bleiben offen.
- Uploads, Originaldateien im Vault und neue Notizen nummerieren Kollisionen
  automatisch: `image.png`, `image1.png`, `image2.png`. Exklusive Dateianlage
  verhindert Überschreiben bei gleichzeitigem Speichern. Wiederholte Ablage
  desselben Anhangs innerhalb eines Auftrags verwendet dessen bestätigten Pfad.
- Kürzere Arbeitsanweisungen konzentrieren das Modell auf die konkrete Aufgabe,
  vorhandene Auswertungen und tatsächliche Werkzeugergebnisse. Die feste
  Markdown-/Obsidian-Referenz liegt in `backend/markdown_knowledge.py` und wird
  direkt in den Systemkontext aufgenommen. Keine zusätzliche Suchrunde nötig.
- Kontext konzentriert sich auf ausdrücklich genannte Dateien und Ordner.
  Suche und Lesezugriffe werden im Backend eingegrenzt, einschließlich der
  SQL-/Vektortrefferauswahl. Kein globaler Ordnerindex im Arbeitschat; globaler
  Umfang nur auf ausdrücklichen Auftrag. Allgemeine Wissensfragen dürfen
  weiterhin global suchen. Lange Notizen sind vollständig seitenweise lesbar.
- Alle Nutzerinformationen bleiben erhalten und sollen sinnvoll strukturiert,
  ausgearbeitet und ohne erfundene Fakten ergänzt werden. Alte KI-Prosa und
  fremde Leseauszüge entfallen. Überschrittene Eingabebudgets erzeugen einen
  klaren Hinweis statt stiller Kürzung. Chats bleiben vollständig gespeichert.
- Der generierte Vault-Index bleibt in `00 Inhalt.md`, entfällt aber im Prompt.
  Individuelle Regeln vor und nach dem Index bleiben verfügbar. Der Index wird
  nach Dateiaktionen einmal pro Chatdurchlauf aktualisiert. Neue Notizen ohne
  Quellenlinks benötigen keinen vollständigen Scan aller Bild-/Dokumentdateien.
- Thinking ist für neue Profile standardmäßig aus. Bestehende gespeicherte
  Entscheidungen sowie die Auswahl pro Nachricht bleiben erhalten.
- Schreibvorschau für neue, ergänzte und bearbeitete Notizen: Diff Alt → Neu,
  vollständige Inhalte, Quellenlinks, Zielpfad; Übernehmen / Anpassen / Abbrechen.
  Externe Änderungen erfordern eine neue Vorschau. Abbrechen beendet den
  Auftrag und versucht seine bisherigen Dateiänderungen zurückzunehmen.
- Persistente Rücknahme des letzten Vault-Auftrags, einschließlich Notizinhalten,
  Originalkopien, Verschiebungen und Linkanpassungen. Konflikte mit neueren
  Änderungen werden vor der Rücknahme aller Dateien geprüft.
- Automatische, durchsuchbare Bild-/Scan-Quellennotizen mit Original-Link,
  vollständigem OCR-Text, erkannten Gerätekennungen, Seiten und Leselücken.
  Vorschau und Bildwissen sind standardmäßig aktiv und abschaltbar, auch pro
  Nachricht. „Nur ansehen“ bleibt ohne automatische Quellenablage.
- Optionales installiertes Vision-Modell, Vorgabe `qwen3-vl:8b`, standardmäßig
  deaktiviert: gesamte Bild-/Scanserie nacheinander, danach bestätigtes Entladen
  und einmaliger Übergang zum Chatmodell. Keine automatische Aufteilung, kein
  paralleles Laden großer Chat-/Vision-Modelle durch die App. Fehlendes VL und
  spätere Bildwerkzeuge verwenden das bildfähige Chatmodell. Keine Installation
  im Hintergrund.

## Prüfung

157 Python-Tests bestanden, darunter konkurrierende Dateianlage, fortlaufende
Nummerierung, unveränderte Originale, wiederholte Anhangablage, direkter
Chatablauf ohne Modell/Analyse/Suche, Erhalt individueller Vault-Regeln und
vollständige Nutzerinformationen, Kontextgrenzen, scoped SQL-/Vektorsuche,
Vorschauen, bearbeitete Übernahmen, Abbruch, Rücknahme und Konflikte sowie
suchbare OCR-Quellen und serieller Vision-Wechsel mit simulierten Modellclients.

Zusätzlich: JavaScript-Modulsyntax und Chat-Auswahl-/Stopp-Prüfungen sowie
Python-Kompilierung und `git diff --check`. Im isolierten Browser wurde die
Vorschau geöffnet, Inhalt und Ziel geändert, gespeichert und per Button
zurückgenommen. Die neuen Einstellungen wurden in der Oberfläche geprüft.

Windows-EXE und ZIP wurden gebaut. Die portable EXE wurde durch
`tests/manual_frozen_validation.py` in einem isolierten Verzeichnis mit frischem
Test-Vault erfolgreich geprüft: Selbsttest, Start,
Sitzungsschutz, Host/Origin, Frontend, Einstellungen, Schreiben, Lesen, Suche,
direkte Anhangablage, Nummerierung, Vorschau, angepasste Übernahme, Abbruch und
Rücknahme einschließlich Konfliktfall. Das lokale Prüfprotokoll dokumentiert
die Messung kleiner synthetischer Direktablagen ohne EXE-Startzeit; dies ist
kein Benchmark großer Dateien oder der Qwen-Generierung.

Abschlussprotokoll: `.test-runtime/v13-frozen-175da5c9/report.json`.
Release: `dist/KnowHow-Tool-v1.3-Windows.zip`, Prüfsummen:
`dist/SHA256SUMS.txt`. Quellcode und Versionstag werden per SSH an
`git@github.com:mRbRaIn0/KnowHow-Tool-Local.git` übertragen.

## Grenzen

Die Beschleunigung der direkten Dateiablage folgt aus dem vollständig
entfallenen Modellaufruf. Für echte Qwen-Generierung und Vision-Auswertung wird
keine pauschale Beschleunigung oder fehlerfreie Syntax garantiert; deren Laufzeit
hängt weiter von Hardware, Modell, Thinking und Quellenumfang ab.

Die Syntaxreferenz umfasst die üblichen Markdown- und Obsidian-Funktionen,
einschließlich Tabellen, Properties, Callouts, Ankern, Einbettungen, Formeln und
Mermaid. Sie bedeutet keinen vollständigen Obsidian-Renderer in der App.
Community-Plugins werden nur bei bestätigter Verfügbarkeit vorausgesetzt.

Syntaxgrundlagen: [Formatierung](https://help.obsidian.md/syntax),
[interne Links](https://help.obsidian.md/links),
[Einbettungen](https://help.obsidian.md/embeds),
[Callouts](https://help.obsidian.md/callouts),
[erweiterte Syntax](https://help.obsidian.md/advanced-syntax).

Beim Update die Anwendung schließen und den vorhandenen `data`-Ordner behalten.
