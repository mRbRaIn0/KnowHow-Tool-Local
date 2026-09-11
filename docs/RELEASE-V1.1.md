# KnowHow Tool V1.1

## Änderungen

- Lokale Wissensverwaltung mit getrennten Bereichen für Erweitern und Fragen.
- Bestehende lokale Vaults, Chats, Anhänge und Datenbanken bleiben erhalten.
- Vor einer Wissensfrage werden neue/geänderte Vault-Dokumente indiziert.
- Quellenanweisungen unterscheiden PDF-Seiten von Notizen und DOCX-Dateien.
- Versionsanzeige auf 1.1.
- Proprietäre Lizenz für mRbRaIn0 und separate Drittanbieter-Lizenzhinweise.
- Empfohlene Modelle Stand 11. September 2026: `qwen3.5:9b` als Standard
  mit Thinking, Alternativen `qwen3.5:4b` und `qwen3-vl:8b`, Suche über
  `nomic-embed-text`. Chats bleiben im Ordner `data` neben der EXE.

## Prüfung am 11. September 2026

- 73 automatisierte Tests bestanden: lokale Workflows, Anhänge, Backups,
  Profile/Chats, Wissensindex, Desktop-Start, Sicherheitsgrenzen und
  Update-Erhalt von Verlauf und Konfiguration.
- Python-Kompilierung und Syntaxprüfung aller 16 JavaScript-Dateien bestanden.
- Gebaute One-File-EXE: Selbsttest für Imports, SQLite, FTS5, sqlite-vec,
  WebView2 und eingebettete Dateien bestanden.
- Portable EXE mit leerem Datenordner: Start, V1.1-Oberfläche,
  Einstellungen, Schreiben, Lesen, Suche und Sitzung-/Host-/Ursprungsschutz geprüft.
- Echter lokaler Ollama-Test mit `qwen3.5:9b` und `nomic-embed-text`:
  synthetisches Bild und DOCX hochgeladen, Bildkennung und Wartungstermin
  zusammen mit einer Texteingabe in einer Notiz gespeichert, beide Originale
  abgelegt und die drei Fakten direkt danach mit Quellen abgefragt.
  Der Fragenmodus veränderte keine Vault-Dateien.

Der erste Modelllauf ergänzte unbelegte Seitenzahlen. Die Quellenanweisung
wurde deshalb präzisiert; die erneute Abfrage lieferte alle drei Fakten mit
korrekten Dateiverweisen ohne erfundene Seitenzahlen. Die Tests ersetzen keine fachliche Prüfung von
KI-Antworten; sie garantieren keine Fehlerfreiheit bei beliebigen Dokumenten.

## Wiederholen

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q backend run.py
.\.venv\Scripts\python.exe tests/manual_local_validation.py
.\.venv\Scripts\python.exe tests/manual_frozen_validation.py dist/Lokale-Wissens-KI.exe
```

Die manuellen Tests verwenden ausschließlich synthetische Daten unter
`.test-runtime/`. Der Modelltest benötigt die beiden lokal installierten
Modelle. Die EXE-Prüfung startet eine eigene portable Kopie ohne sichtbares
Fenster. Windows-Sandboxbeschränkungen können temporäre Testordner oder das
Entpacken der EXE blockieren; die Abnahme erfolgte außerhalb dieser Sandbox.

## Unternehmenslaptop

Das ZIP in denselben beschreibbaren Ordner entpacken, in dem die bisherige
`KnowHow Tool.exe` liegt, und vorhandene Dateien ersetzen. Den Ordner `data`
nicht löschen, sonst gehen Chats und Profile verloren. Ollama und Modelle
müssen separat vorhanden sein; für die EXE ist keine Python-Installation nötig.
Ein eigenes Unternehmensprofil und einen lokalen Wissensordner einrichten.
Bild-/Scanwissen für spätere Fragen in Textnotizen übernehmen lassen.

Die EXE ist nicht digital signiert. Ausführung auf dem Zielgerät hängt von
dessen IT-Richtlinien, WebView2-Verfügbarkeit und Hardware ab. Der konkrete
Unternehmenslaptop wurde nicht getestet. Details stehen in der README.
