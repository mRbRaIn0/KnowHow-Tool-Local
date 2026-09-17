# Direkte Dateiaktionen und Laufzeitdiagnose

Der Arbeitschat erkennt eindeutige Dateioperationen vor jedem Modellzugriff.
Erstellen, Anhängen, exakte Suche, Löschen, Umbenennen und Verschieben benötigen
damit weder Ollama noch Embeddings, Agentenrunden oder einen Modellwechsel.

Beispiele (Namen mit Leerzeichen in Anführungszeichen oder Backticks):

```text
Füge diesen Text zu `SPS/delete2.md` hinzu:
Hier steht der vollständige fertige Text.

Erstelle `SPS/Neu.md`: Vollständiger Inhalt
Finde `delete2.md`
Lösche `SPS/delete2.md`
Benenne `SPS/delete2.md` in `Steuerung.md` um
Verschiebe `SPS/delete2.md` nach `SPS/Archiv`
```

Die Auflösung priorisiert den exakten Pfad, dann den exakten Dateinamen,
dann den exakten Markdown-Namen ohne `.md`. Auch leere Dateien zählen.
Bei mehreren gleichnamigen Dateien fragt die Anwendung nach dem Ordner.
Die Antwort `Ordner SPS` setzt denselben Auftrag mit unverändertem Text fort.
Ein ausdrücklich angegebener Pfad wechselt niemals in einen anderen Ordner.
Beim Anhängen wird ein fehlendes Ziel unter genau diesem Namen erstellt;
es entsteht keine nummerierte Ersatznotiz. Explizites Erstellen überschreibt
keine vorhandene Datei. Nummerierung bleibt für die Ablage von Anhängen bestehen.

Fertiger Text wird unverändert übernommen; nur zwischen vorhandenem Inhalt und
Ergänzung wird bei Bedarf eine Absatztrennung eingefügt. Die optionale
Schreibvorschau bleibt erhalten. Mit aktivierter Vorschau wartet die Anwendung
auf Übernehmen; für sofortiges Schreiben den Schalter im Arbeitschat ausschalten.
Der exakte Zielpfad bleibt auch in der Vorschau verbindlich.

Löschen betrifft eine konkret genannte Datei, niemals rekursiv einen Ordner.
Umbenennen und Verschieben passen bestehende Links mechanisch an; deshalb lesen
diese beiden Operationen die Markdown-Dateien im Vault. Die Dateiinhalte gehen
dabei nicht an ein Modell. Der letzte Auftrag lässt sich einschließlich seiner
Linkänderungen rückgängig machen. Schreibfehler beim Verschieben lösen eine
Rücknahme aus; externe Konflikte werden gemeldet statt überschrieben.

## Festgestellte Ursachen und Grenzen

- Für Anhängen fertiger Inhalte fehlte ein Direktpfad. Es lief der allgemeine
  Modell-/Werkzeugzyklus mit Kontext, Lesen, Schreiben und Abschlussantwort.
- Der automatische Abschluss konnte bei einem Ergänzungsauftrag ohne zuvor
  gelesene Zielnotiz auf eine neue KI-Notiz ausweichen. Das ist jetzt gesperrt.
- Die Textsuche war keine verlässliche exakte Dateiauflösung. Exakte Treffer
  werden jetzt vor Inhalts-/unscharfen Treffern geliefert, auch ohne Inhalt.
- Die Oberfläche blockierte den gesamten Chat bei ausgeschaltetem Ollama.
  Datei-Direktaktionen im Arbeitschat sind jetzt trotzdem möglich.
- Der generierte Vault-Inhaltsindex wird auf dem Direktpfad nicht synchron
  neu aufgebaut. Die Suche wird vom Dateiwächter aktualisiert; `00 Inhalt.md`
  kann bis zur nächsten Indexaktualisierung veraltete Einträge enthalten.

Freie Formulierungen, Zusammenfassungen und kombinierte mehrteilige Aufträge
bleiben Modellaufgaben. Eine kompakte Werkzeuginstruktion vermeidet unnötige
Planungsprosa, ohne den zu speichernden Inhalt zu kürzen. Bestehende Thinking-
Einstellungen bleiben respektiert. Das eigentliche HTTP-Streaming war bereits
aktiv; bei Schreibaufträgen wird ungeprüfte Modellprosa teilweise zurückgehalten.

Ollama hält das Modell standardmäßig fünf Minuten nach einer Anfrage geladen.
Die Anwendung setzt nun konfigurierbar `keep_alive` (Vorgabe `10m`; Einstellungen,
zum Beispiel `30m`, `1h` oder `0`). Der separate Vision-Durchlauf entlädt Modelle
weiterhin ausdrücklich vor dem Wechsel. Grundlage: [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md).

Die lokalen Logs protokollieren je Modellaufruf die Zeit bis zur ersten Ausgabe,
Gesamtdauer sowie Ollamas Lade-, Eingabe- und Generierungsdauer und Tokenzahlen.
Diese Diagnosezeile enthält keine Chattexte. Damit lassen sich Kaltstart,
großer Kontext und langsame Generierung getrennt beurteilen. Die früher vom
Nutzer beobachteten Minuten wurden nicht auf dessen beiden Geräten reproduziert.

## Prüfung

Automatisierte Tests decken exakte und leere Ziele, ähnlich benannte Dateien,
Mehrdeutigkeit mit Ordnerantwort, unveränderten Text, fehlende Ziele, Vorschau,
Rücknahme, Linkanpassungen und Fehler-Rollback ab. Der Direktpfadtest verbietet
Modell-, Kontext-, Guide- und Suchaufrufe ausdrücklich. Eine lokale Messung
des vollständigen Chatablaufs ohne Vorschau ergab etwa 183 ms. Das ist eine
Messung mit Testdaten auf dem Entwicklungsrechner, keine allgemeine Zeitgarantie.
Der portable EXE-Test prüft denselben Fall zusätzlich über HTTP ohne Ollama.
