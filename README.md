# KnowHow Tool · V1.3

**Direkte Dateiaktionen:** Fertigen Text mit `Füge diesen Text zu SPS/delete2.md hinzu:`
und anschließendem Inhalt ohne Modellaufruf ergänzen – auch bei leerer Notiz.
Exakte Pfade haben Vorrang; mehrere Treffer lösen eine Ordnerfrage aus.
[Befehle, Performance-Diagnose und Grenzen](docs/DIRECT-ACTIONS.md).

Lokale Wissens-KI für Windows von **mRbRaIn0**. Sammle Informationen, Bilder und
Dokumente in einem eigenen Wissensordner und frage ihre Inhalte mit Quellen ab.
Die KI läuft über Ollama auf deinem Rechner; Notizen bleiben normale
Markdown-Dateien, die du auch mit Obsidian bearbeiten kannst.

[Windows-Release](https://github.com/mRbRaIn0/KnowHow-Tool-Local/releases/latest)
· [KI-Verhalten](KI.md) · [Release V1.3](docs/RELEASE-V1.3.md)

## Neu in V1.3

- Reine Ablagebefehle wie „Datei schnell ablegen“ oder „Lege die Dateien in
  "Projekt/Dateien" ab“ werden ohne Modellaufruf und ohne Inhaltsanalyse ausgeführt.
  Ohne Ziel wird der konfigurierte Anhangordner verwendet. Aufträge mit
  Zusammenfassung, Notiz oder inhaltlicher Einsortierung laufen weiter über die KI.
- Gleiche Dateinamen werden automatisch nummeriert: `image.png`, `image1.png`,
  `image2.png`. Das gilt auch für Uploads und neu erstellte Notizen.
- Kürzere Arbeitsanweisungen, kompakte frühere KI-Antworten und ein
  gebündeltes Aktualisieren der Vault-Übersicht vermeiden unnötige Arbeit.
- Die KI erhält eine feste Markdown-/Obsidian-Syntaxreferenz aus dem Code.
  Eigene Gestaltungsregeln gehören weiterhin in `00 Inhalt.md` im Vault.
  Community-Plugins werden nicht vorausgesetzt; die App-Vorschau unterstützt
  nicht sämtliche Darstellungen von Obsidian.
- **Gezielter Kontext:** Genannte Dateien und Ordner begrenzen Suche und
  Lesezugriffe. Pfade mit Leerzeichen in Anführungszeichen oder `[[WikiLinks]]`
  nennen. Ohne Ziel lädt der Arbeitschat keinen allgemeinen Vault-Kontext.
  „Im gesamten Vault“ erweitert den Umfang ausdrücklich. Wissensfragen ohne
  Pfadangabe suchen weiterhin im freigegebenen Wissen.
- **Informationen erhalten:** Alle eingegebenen Sachinformationen bleiben im
  Arbeitskontext. Die KI soll sie sinnvoll gliedern und ergänzen; unbekannte
  Fakten bleiben als offen markiert. Bei zu großem Kontext stoppt sie mit einem
  Hinweis, statt alte Nutzerangaben still zu entfernen.
- **Schreibvorschau:** Notizinhalt, Diff, Quellenlinks und Zielpfad vor dem
  Speichern prüfen. Übernehmen, Anpassen oder den Auftrag abbrechen.
- **Rückgängig:** Der letzte Vault-Auftrag lässt sich in der Kontextspalte
  zurücknehmen, einschließlich Notizinhalten, verschobenen Dateien und Links.
  Neuere externe Änderungen verhindern eine überschreibende Rücknahme.
- **Bildwissen speichern:** OCR und Bildbeschreibungen werden mit Original-Link
  und erkannten Seitenangaben unter `91 Quellenwissen` suchbar abgelegt.
  Vorschau und Quellenablage lassen sich in den Einstellungen und pro Nachricht
  ausschalten. „Nur ansehen“ legt keine Bildquelle im Vault ab.
- **Optionales Vision-Modell:** In den KI-Einstellungen kann ein installiertes
  `qwen3-vl:8b` aktiviert werden. Es bearbeitet den gesamten Bild-/Scanblock,
  wird entladen und übergibt einmal an das Chatmodell. Spätere Bildwerkzeuge
  verwenden das bildfähige Chatmodell. Standardmäßig bleibt diese Option aus.

## Zwei Bereiche für dein Wissen

| Bereich | Aufgabe |
|---|---|
| **Wissen erweitern** | Informationen eingeben, Dateien anhängen, Bilder auswerten und Notizen anlegen oder ergänzen. Originaldateien können passend im Wissensordner abgelegt und verlinkt werden. |
| **Wissen fragen** | Fragen zur gespeicherten Wissensbasis stellen. Relevante Auszüge gelangen mit Dateiquellen in den Modellkontext. Dieser Bereich hat keine Schreibwerkzeuge. |

Weitere Funktionen:

- Datei- und Notizbrowser mit Markdown-Editor, Vorschau und Obsidian-WikiLinks.
- Bilder und Screenshots per Dateiauswahl, Drag-and-drop oder Zwischenablage.
- Textauswertung für PDFs, DOCX, Markdown und unterstützte Text-/Codedateien.
- Bildanalyse und Auswertung gescannter PDF-Seiten über ein lokales Vision-Modell.
- Hybride Suche aus SQLite-Volltextsuche und lokalen Ollama-Embeddings.
- Getrennte Profile, Chatverläufe, Vorlagen und lokale ZIP-Backups.
- Helles/dunkles Design und eigenes App-Fenster über WebView2.

## Schnellstart unter Windows

1. **Ollama einrichten.** Installiere [Ollama für Windows](https://ollama.com/download/windows)
   und lade mindestens das Standardmodell plus das Suchmodell. Stand 11. September 2026:

   | Modell | Rolle |
   |---|---|
   | **`qwen3.5:9b`** (Standard) | Allrounder für diese App: Deutsch, Thinking, Werkzeuge, Bilder und gescannte Seiten. Braucht etwa 8 GB Grafik- oder Arbeitsspeicher. Thinking macht Antworten gründlicher, aber langsamer. Kein Audio, keine Cloud. |
   | **`qwen3.5:4b`** | Kleiner und schneller. Thinking möglich. Schwächer bei langen Notizen, schwierigen Scans und kniffligen Werkzeugaufträgen. Gut, wenn der 9B-Stand zu langsam ist. |
   | **`qwen3-vl:8b`** | Besonders für Fotos, Screenshots und gescannte PDFs. Kein voller Ersatz für den 9B-Allrounder: Text, Thinking und Vault-Werkzeuge sind oft schwächer. |
   | **`nomic-embed-text`** (Suche) | Nur für die lokale Wissenssuche, kein Chat. Ohne dieses Modell bleiben Stichwortsuche und Dateibrowser nutzbar, die Bedeutungs-Suche fehlt. |

   ```powershell
   ollama pull qwen3.5:9b
   ollama pull nomic-embed-text
   ```

   Optional bei wenig Speicher bzw. viel Bildarbeit:

   ```powershell
   ollama pull qwen3.5:4b
   ollama pull qwen3-vl:8b
   ```

   Neue Profile starten mit Thinking aus für schnellere Antworten. Du kannst es
   neben der Eingabe einschalten; bestehende Einstellungen bleiben erhalten. Die Einrichtung braucht Internet; der spätere Betrieb kann
   offline erfolgen.

2. **Release entpacken.** Lade `KnowHow-Tool-v1.3-Windows.zip` aus den
   [Releases](https://github.com/mRbRaIn0/KnowHow-Tool-Local/releases/latest)
   und entpacke es in einen beschreibbaren lokalen Ordner, beispielsweise
   `%LOCALAPPDATA%/KnowHow-Tool`. Chats liegen im Ordner `data` **neben** der EXE.
   Bei einem Update denselben Ordner verwenden und `data` behalten — nicht in einen
   neuen leeren Ordner entpacken.
3. **App starten.** Öffne `KnowHow Tool.exe`. Python wird für die EXE nicht
   benötigt. Ollama und die Modelle sind separat erforderlich.
4. **Profil und Wissensordner wählen.** Wähle in den Einstellungen einen eigenen
   lokalen Ordner oder einen vorhandenen Obsidian-Vault. Für getrennte Daten
   kannst du ein eigenes Unternehmensprofil anlegen.
5. **Wissen hinzufügen und abfragen.** Nutze zunächst **Wissen erweitern** und
   stelle anschließend unter **Wissen fragen** deine Frage.

Beispiel:

> **Wissen erweitern:** „Erstelle aus diesem Screenshot und der angehängten
> Anleitung eine Wissensnotiz. Übernimm die Gerätekennung und die Wartungsschritte
> und verlinke beide Originaldateien.“
>
> **Wissen fragen:** „Welche Wartungsschritte gelten für dieses Gerät? Nenne die
> Quellen aus meinem Wissen.“

Bild- und Scanerkenntnisse müssen als Textnotiz gespeichert werden, damit sie
später in der Wissenssuche verfügbar sind. Vor einer Wissensfrage gleicht die
App neue und geänderte Textdokumente mit dem Index ab.

## Voraussetzungen und Grenzen

- Windows 10/11, Ollama und ausreichend Arbeitsspeicher für das ausgewählte Modell.
  Die Geschwindigkeit hängt insbesondere von Modell, GPU und Kontextgröße ab.
- WebView2 für das eingebettete Fenster. Bei fehlendem WebView2 versucht die App
  einen lokalen Browser im App-Modus zu verwenden.
- Die EXE ist nicht digital signiert. Auf verwalteten Geräten muss ihre
  Ausführung den geltenden IT-Richtlinien entsprechen.
- Bis zu 50 Anhänge je Eingabe, 40 MB je Datei und 400 MB je Chat.
  PDF-Seiten werden einzeln ausgewertet und zwischengespeichert.
- Fehlende Embeddings verhindern die Stichwortsuche nicht. Bildauswertung
  benötigt ein Modell mit Vision-Unterstützung.
- KI-Antworten können Fehler enthalten. Prüfe wichtige Angaben anhand der
  Originalquellen. Allgemeines Modellwissen soll als solches gekennzeichnet sein.

## Lokal gespeicherte Daten

Eine portable EXE legt ihren `data/`-Ordner neben sich an. Dort liegen
Konfiguration, profilbezogene Datenbanken, Uploads und lokale Protokolle.
Ein Build im `dist/`-Ordner dieses Quellprojekts verwendet dessen vorhandenen
`data/`-Ordner. Der gewählte Wissensordner enthält die eigentlichen Notizen und
abgelegten Originaldateien.

Die App erstellt im ausgewählten Wissensordner eine `00 Inhalt.md` als
Orientierung und Inhaltsübersicht. Bestehende eigene Regeln bleiben erhalten.
Obsidian ist optional; es wird kein proprietäres Notizformat verwendet.

Unter **Einstellungen → Daten → Backup** kannst du Vault, Profilkonfiguration
und Datenbank lokal sichern. Die App übernimmt keine automatische
Synchronisation zwischen Geräten.

## Aktualisieren (Chats behalten)

Chats, Profile und Einstellungen überleben ein Update nur, wenn der Ordner
`data` am gleichen Ort bleibt. Der Vault (Notizen) liegt separat im gewählten
Wissensordner und bleibt davon unberührt.

1. Die laufende App vollständig beenden. Eine alte Instanz darf nicht weiterlaufen.
2. Das neue ZIP aus den Releases herunterladen.
3. Den Inhalt **in denselben Ordner** entpacken, in dem bereits `KnowHow Tool.exe`
   liegt, und vorhandene Dateien ersetzen. Den Ordner `data` nicht löschen.
4. `KnowHow Tool.exe` starten. Verlauf und Vault-Pfad sind dieselben wie zuvor.

Nicht in einen neuen leeren Ordner entpacken — dort entsteht ein leerer
`data`-Ordner und der Verlauf wirkt verschwunden. In diesem Fall den alten
`data`-Ordner neben die neue EXE kopieren und neu starten. Unter Windows die
App nicht aus dem ZIP-Explorer heraus starten, sondern zuerst entpacken.

## Datenschutz

- Backend nur auf `127.0.0.1`, mit wechselndem Port und Sitzungsschlüssel.
- Prüfung von Host und Ursprung sowie eine restriktive Content-Security-Policy.
- Offline-Modus standardmäßig aktiv; Ollama-Verbindungen bleiben lokal.
- Keine Telemetrie, Analytics oder extern geladenen CDN-Ressourcen.
- Modell-Downloads erfolgen nur nach einer ausdrücklich gestarteten Einrichtung.
- Vault-Werkzeuge prüfen Dateipfade und besitzen keinen Shell-Zugriff.

Release-Pakete und Quellcode enthalten keine persönlichen Profile, Chats,
Uploads, Wissensordner oder Modelle.

## Aus dem Quellcode starten

Für die Entwicklung benötigst du Python; V1.3 wurde mit Python 3.12 geprüft.
`start.bat` richtet die lokale `.venv` mit den festgelegten Abhängigkeiten ein
und startet die Anwendung. Alternativ nach der Einrichtung:

```powershell
.\.venv\Scripts\python.exe run.py
```

Die Konfiguration wird beim ersten Start angelegt. `config.example.json`
dokumentiert die Einstellungen. `KI.md` beschreibt Werkzeuge, Modustrennung,
Quellenbehandlung und Schreibkontrollen.

## Prüfen und EXE bauen

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q backend run.py
powershell -ExecutionPolicy Bypass -File .\build-exe.ps1
```

Der Build erzeugt `dist/KnowHow Tool.exe`, das Release-ZIP und
`dist/SHA256SUMS.txt`. Lizenzhinweise werden aus der installierten Umgebung
zusammengestellt und mitgeliefert. Für reproduzierbare Ergebnisse eine frische
Umgebung mit `requirements.txt` und `requirements-build.txt` verwenden.

V1.3: 109 automatisierte Python-Tests bestanden. Zusätzliche Build- und
Startprüfungen stehen im Release-Bericht.
Details und Grenzen stehen in den [Release-Notizen](docs/RELEASE-V1.3.md).

Die vorherige V1.1 wurde mit automatisierten Tests, einem echten lokalen Bild-/DOCX-Workflow
und einem Starttest der portablen EXE geprüft. Umfang und wiederholbare
Abnahmeskripte stehen im [Prüfbericht](docs/RELEASE-V1.1.md).

## Lizenz

Copyright © 2026 mRbRaIn0. Siehe [LICENSE](LICENSE).
Drittanbieter-Komponenten behalten ihre eigenen Lizenzen:
[THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).
