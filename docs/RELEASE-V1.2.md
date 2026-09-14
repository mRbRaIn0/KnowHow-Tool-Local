# KnowHow Tool V1.2

Stand: 14.09.2026

## Änderungen

- Modell und Thinking werden pro Nachricht fest übermittelt. Die Auswahl steht oberhalb der Eingabe; die rechte Anzeige folgt dem bestätigten Status.
- Eindeutige Befehle zum Anlegen einer benannten Markdown-Datei im Hauptordner laufen ohne Modellgenerierung. Vorhandene Dateien werden nicht überschrieben.
- Wiederholte Textsuchen nutzen einen begrenzten Cache; Dateinamen werden bevorzugt. Exakte lokale Treffer vermeiden zusätzliche Embedding-Aufrufe. Die optionale semantische Anfrage hat ein Zeitlimit.
- Anhang-Auswertungen werden ungekürzt nach jeder Datei bzw. PDF-Seite atomar zwischengespeichert. PDF-Bildinhalte und eingebettete Word-Bilder werden berücksichtigt; die frühere Acht-Seiten-Grenze der Vorauswertung entfällt.
- Gespeicherte Arbeitsnotizen stehen für Folgefragen und die Wiederaufnahme unterbrochener Auswertungen bereit. Umfangreiche Inhalte sind über das Anhang-Werkzeug in Teilen abrufbar.
- Leselücken werden markiert. Bestätigte Dateiaktionen und laufende Antworten werden gesichert; bei reinem Thinking ohne Ergebnis wird ein Abschluss angefordert und nötigenfalls ein konkreter Status ausgegeben.

## Prüfung

86 Python-Tests bestanden, darunter zehn simulierte Screenshot-Auswertungen, zwölf PDF-Seiten mit Abbruch/Wiederaufnahme, echtes PDF-Rendering, eingebettete Word-Bilder, Folgefragen und Abbruch nach einer Dateiaktion. JavaScript-Prüfungen für Auswahlübermittlung und veraltete Statusantworten sowie Syntax- und Diff-Prüfungen bestanden.

Die Qualität und Laufzeit echter Qwen-Auswertungen wurden für V1.2 nicht neu gemessen. Ein neuer EXE-Build und dessen Starttest sind nicht Bestandteil dieses Quellcode-Releases. Das Build-Skript erzeugt künftig die V1.2-Paketnamen.
