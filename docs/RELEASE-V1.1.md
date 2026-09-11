# KnowHow Tool V1.1

## Änderungen

- Separate NAS-Bibliothek aus Navigation, Suche, Konfiguration, API,
  Hintergrundjobs und Build entfernt; auch die ausschließlich dafür genutzte
  Docling-Einrichtung entfällt.
- Bestehende lokale Vaults, Chats, Anhänge und Datenbanken bleiben erhalten.
  Alte Katalogtabellen werden weder gelöscht noch für Antworten verwendet.
- Vor einer Wissensfrage werden neue/geänderte Vault-Dokumente indiziert.
- Quellenanweisungen unterscheiden PDF-Seiten von Notizen und DOCX-Dateien.
- Spirit-Mailadresse aus der Oberfläche entfernt; Versionsanzeige auf 1.1.
- Proprietäre Lizenz für mRbRaIn0 und separate Drittanbieter-Lizenzhinweise.
- Release-ZIP mit expliziter Dateiliste und SHA-256-Prüfsummen.

## Prüfung am 11. September 2026

- 70 automatisierte Tests bestanden: lokale Workflows, Anhänge, Backups,
  Profile/Chats, Wissensindex, Desktop-Start und Sicherheitsgrenzen.
- Python-Kompilierung und Syntaxprüfung aller 16 JavaScript-Dateien bestanden.
- Gebaute One-File-EXE: Selbsttest für Imports, SQLite, FTS5, sqlite-vec,
  WebView2 und eingebettete Dateien bestanden.
- Portable EXE mit leerem Datenordner: Start, V1.1-Oberfläche ohne NAS/Kontaktmail,
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

Das ZIP in einen beschreibbaren lokalen Ordner entpacken. Ollama und Modelle
müssen separat vorhanden sein; für die EXE ist keine Python-Installation nötig.
Ein eigenes Unternehmensprofil und einen lokalen Wissensordner einrichten.
Bild-/Scanwissen für spätere Fragen in Textnotizen übernehmen lassen.

Die EXE ist nicht digital signiert. Ausführung auf dem Zielgerät hängt von
dessen IT-Richtlinien, WebView2-Verfügbarkeit und Hardware ab. Der konkrete
Unternehmenslaptop wurde nicht getestet. Details stehen in der README.
