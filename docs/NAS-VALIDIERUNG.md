# NAS-Bibliothek – Prüfprotokoll

Stand: 31.08.2026, App 0.3.0. Alle Dateiaktionen fanden in isolierten
Testverzeichnissen statt. Produktive Profile, Vaults und NAS-Dateien wurden
nicht verwendet.

## Automatisierte Prüfung

`python -m pytest -q -p no:cacheprovider` mit separatem Testverzeichnis:
**71 Tests erfolgreich**, zusätzlich 10 erfolgreiche Subtests. Darin sind
die 45 bisherigen Tests für Chat, Anhänge, Vault, Workflows und Backups
enthalten. Ein bestehender Deprecation-Hinweis von FastAPI/Starlette zum
TestClient bleibt bestehen.

Die Bibliothekstests decken insbesondere ab:

- Originale bleiben beim Scan und bei Vorschlägen unverändert; Entwürfe
  überstehen einen Neustart und werden nicht als bestätigte Metadaten gesucht.
- Stale Revisionen, fremde Profile, fehlende Bestätigung, belegte Ziele und
  geänderte Quelldateien verhindern eine Ausführung.
- Gleichnamige Dateien und identische Kopien behalten verschiedene IDs.
- Hashgeprüfte Kopien, Wiederaufnahme nach Veröffentlichung, unveränderte
  Verschiebungen rückgängig machen und Transaktionsabbruch bei Freigabe.
- Ausfall einer Quelle erhält den Katalog. Änderungen während eines Scans
  erzeugen einen weiteren Scan statt verlorener Ereignisse.
- JSON enthält keine Volltexte, Vektoren oder KI-Entwürfe. Wiederherstellung
  erhält Tags, Struktur und stabile IDs bei neuer Quellenzuordnung.
- Explizite Inhaltsfreigabe und Widerruf, Vektorsuche mit Quellenfilter,
  Neuaufbau nach fehlender Erweiterung und getrennte Vaults trotz gleicher
  relativer Dateinamen.
- 100.000 Katalogeinträge: Seite mit den letzten 100 Einträgen innerhalb des
  Testlimits von fünf Sekunden. Suchtreffer hinter 20.000 Abschnitten.

## Bedienprüfung

Im lokalen Browser mit abgeschaltetem Ollama geprüft:

- Manuelles Tagging, Vorher-/Nachher-Vorschau, Freigabe und Neuladen.
- Eigene Tag-Gruppe anlegen und in der Metadateneingabe verwenden.
- Standard „Kopieren – Original behalten“, separate Ablagefreigabe und
  Abschluss des Hintergrundauftrags.
- Original und Kopie erscheinen getrennt; externe SHA-256-Prüfung stimmt
  überein. Textvorschau und bestätigte Tags sind sichtbar.
- Neue Obsidian-Notiz nach Vorschau mit bestätigter Beschreibung, Tags,
  Bibliotheks-ID und Dateiverweis. Original bleibt außerhalb des Test-Vaults.
- JSON-Sicherungsstatus, Strukturverwaltung und paginierte Prüfliste.

## Windows-Paket

Gebaut unter Windows 11 mit Python 3.12.10 und PyInstaller 6.15.0.
SQLite 3.49.1, sqlite-vec 0.1.9. UPX ist deaktiviert; das Paket ist unsigniert.

- Selbsttest der fertigen EXE: erfolgreicher Import, Uvicorn-Protokollierung,
  FTS5, Vektorerweiterung und erforderliche gebündelte Dateien.
- Echter Serverstart aus einer isolierten EXE-Kopie ohne Browser und ohne
  Ollama-Autostart. `/api/health` meldet 0.3.0.
- Bibliothek im neuen Profil zunächst deaktiviert; explizite Aktivierung
  erfolgreich. Leerer Katalog und geladene Vektorerweiterung bestätigt.
- Ein beim Start ohne Konsole gefundener Uvicorn-Fehler wurde durch gültige
  Standardstreams für die fensterlose EXE behoben und erneut geprüft.

Die Test-Sandbox verhindert das Entpacken mancher PyInstaller-/pytest-
Temporärdateien. Diese Prüfungen liefen deshalb außerhalb der Sandbox,
weiterhin ausschließlich mit isolierten Testdaten.

## Noch auf dem Zielsystem zu prüfen

- Physisches UGREEN-NAS: SMB-Trennung während einer Übertragung, erneute
  Verbindung, ACLs, Polling und Durchsatz. Lokale NAS-Testordner simulieren
  keine echten SMB-Eigenschaften.
- Optionales Docling-Paket mit vollständig geladenen Layout-/OCR-Modellen.
  Es wurde kein umfangreicher Modell-Download ausgeführt.
- Qualität und Geschwindigkeit der Vorschläge mit dem gewählten Ollama-
  Modell; Modellantworten sind in den Sicherheitstests simuliert.

Vor produktiven Verschiebungen die SMB-Prüfung mit entbehrlichen Kopien auf
einer eigenen Testfreigabe durchführen. Metadatensicherungen ersetzen kein
Backup der Originaldateien.
