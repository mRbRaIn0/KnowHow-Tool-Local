# KnowHow Tool · V1.1

Lokale Wissens-KI für Windows von **mRbRaIn0**. Sammle Informationen, Bilder und
Dokumente in einem eigenen Wissensordner und frage ihre Inhalte mit Quellen ab.
Die KI läuft über Ollama auf deinem Rechner; Notizen bleiben normale
Markdown-Dateien, die du auch mit Obsidian bearbeiten kannst.

[Windows-Release](https://github.com/mRbRaIn0/KnowHow-Tool-Local/releases/latest)
· [KI-Verhalten](KI.md) · [Prüfbericht V1.1](docs/RELEASE-V1.1.md)

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
   und stelle ein Chat-Modell mit Bild- und Werkzeugunterstützung bereit.
   Der geprüfte Modellstand verwendet `qwen3.5:9b` und `nomic-embed-text`:

   ```powershell
   ollama pull qwen3.5:9b
   ollama pull nomic-embed-text
   ```

   Diese Einrichtung benötigt Internet. Der spätere Betrieb kann offline erfolgen.

2. **Release entpacken.** Lade `KnowHow-Tool-v1.1-Windows.zip` aus den
   [Releases](https://github.com/mRbRaIn0/KnowHow-Tool-Local/releases/latest)
   und entpacke es in einen beschreibbaren lokalen Ordner, beispielsweise
   `%LOCALAPPDATA%/KnowHow-Tool`.
3. **App starten.** Öffne `KnowHow Tool v1.1.exe`. Python wird für die EXE nicht
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
  Für gescannte PDFs werden bis zu acht Seiten je Dokument ausgewertet.
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

Für die Entwicklung benötigst du Python; V1.1 wurde mit Python 3.12 geprüft.
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

Der Build erzeugt `dist/KnowHow Tool v1.1.exe`, das Release-ZIP und
`dist/SHA256SUMS.txt`. Lizenzhinweise werden aus der installierten Umgebung
zusammengestellt und mitgeliefert. Für reproduzierbare Ergebnisse eine frische
Umgebung mit `requirements.txt` und `requirements-build.txt` verwenden.

V1.1 wurde mit automatisierten Tests, einem echten lokalen Bild-/DOCX-Workflow
und einem Starttest der portablen EXE geprüft. Umfang und wiederholbare
Abnahmeskripte stehen im [Prüfbericht](docs/RELEASE-V1.1.md).

## Lizenz

Copyright © 2026 mRbRaIn0. Siehe [LICENSE](LICENSE).
Drittanbieter-Komponenten behalten ihre eigenen Lizenzen:
[THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).
