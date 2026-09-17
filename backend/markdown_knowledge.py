"""Kompakte, offline verfügbare Schreibreferenz für Obsidian-Notizen.

Referenz: https://help.obsidian.md/syntax, /links, /embeds, /callouts,
/advanced-syntax. Die App-Vorschau bildet nicht jede Obsidian-Funktion ab.
"""

MARKDOWN_INSTRUCTIONS = r"""Markdown / Obsidian — Syntax beim Schreiben:
- Überschriften: # Titel, ## Abschnitt, ### Unterabschnitt bis ######; Leerzeichen nach #. Absätze mit Leerzeile trennen.
- Betonung: **fett**, *kursiv*, ***beides***, ~~gestrichen~~, ==markiert==. Literale Sonderzeichen mit Backslash maskieren.
- Listen: - Eintrag; nummeriert: 1. Schritt; Aufgaben: - [ ] offen / - [x] erledigt. Unterpunkte einrücken.
- Code inline mit `code`; Codeblöcke mit drei Backticks plus Sprache (z.B. python) öffnen und mit drei Backticks schließen. Nicht die gesamte Notiz in einen Codeblock setzen.
- Tabellen: Kopfzeile | Begriff | Wert |, darunter | --- | --- |, danach Datenzeilen. Jede Zeile gleich viele Spalten; Pipes im Zelltext/Linkalias als \| maskieren; Ausrichtung :---, :---:, ---:.
- Interne Links mit vollständigem Vault-Pfad: [[Ordner/Notiz]], Alias [[Ordner/Notiz|Anzeigename]], Überschrift [[Ordner/Notiz#Abschnitt]], Block [[Ordner/Notiz#^block-id]]. Anker müssen vorhanden sein; Block-ID als ^block-id am Absatzende, nur Buchstaben/Ziffern/Bindestriche.
- Einbettungen: ![[Ordner/Notiz#Abschnitt]], ![[Ordner/Bild.png|480]], ![[Ordner/Quelle.pdf#page=3]]. Originalpfade aus Werkzeugergebnissen übernehmen. Bilder normalerweise einbetten, Dokumente als Quellen verlinken.
- Weblinks: [Bezeichnung](https://example.org); Leerzeichen in URLs als %20. Keine erfundenen Quellen, keine reinen Ordnerlinks; vorhandene Indexnotiz verlinken. Neue Links auf Notizen nur zu bekannten oder gerade erstellten Zielen.
- Zitat: > Text. Callout: > [!info] Titel, nächste Zeile > Inhalt; Typen z.B. note, tip, warning, question; einklappbar mit [!tip]-.
- Fußnoten: Aussage[^quelle] und eigene Definitionszeile [^quelle]: Beleg. Kommentare: %% Kommentar %%. Trennlinie: --- auf eigener Zeile mit Leerzeilen davor/danach.
- Properties: YAML-Block zwischen --- ganz am Dateianfang; z.B. tags: [wissen], aliases: [Alternativname]. WikiLinks in YAML quotieren. Vorhandene Metadaten erhalten. Tags im Text: #wissen/thema (keine Leerzeichen).
- Formeln: $x^2$ inline, $$ ... $$ als Block. Diagramme: geschlossener Codeblock mit Sprache mermaid, z.B. flowchart LR und A --> B.
- Canvas und Bases sind eigene Formate (.canvas/.base), keine Markdown-Notizen. Dataview/Templater/Tasks erfordern Community-Plugins: deren Installation niemals voraussetzen; nur bei bestätigter Verfügbarkeit verwenden.
Wähle nur die zur Aufgabe passende Syntax. Obsidian rendert mehr als die App-Vorschau; Plugins und ausführbare Blöcke sind keine universellen Markdown-Funktionen."""
