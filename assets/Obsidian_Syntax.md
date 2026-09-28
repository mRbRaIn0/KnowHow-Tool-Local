# Obsidian-Syntax: erweiterte Referenz

Diese Datei nur bei Bedarf für erweiterte Markdown- oder Obsidian-Funktionen lesen.

- Weitere Überschriften: `####` bis `######` mit Leerzeichen. Sonderzeichen als Literal mit Backslash maskieren.
- Weitere Betonung: `***fett und kursiv***`, `~~gestrichen~~`, `==markiert==`.
- Code inline: `` `code` ``. Einen ganzen Notiztext nicht in einen Codeblock setzen.
- Tabellen: Pipes in Zellen oder Linkalias als `\|` maskieren. Ausrichtung: `:---`, `:---:`, `---:`.
- WikiLinks: Alias `[[Ordner/Notiz|Name]]`, Überschrift `[[Ordner/Notiz#Abschnitt]]`, Block `[[Ordner/Notiz#^block-id]]`. Anker müssen existieren.
- Einbettungen: `![[Ordner/Notiz#Abschnitt]]`, `![[Ordner/Bild.png|480]]`, `![[Ordner/Quelle.pdf#page=3]]`.
- Weblinks: `[Name](https://example.org)`; Leerzeichen in URLs als `%20` kodieren.
- Callouts: `> [!tip]- Titel` für einklappbare Hinweise. Weitere Typen sind `note`, `warning`, `question`.
- Fußnoten: `Aussage[^quelle]` und `[^quelle]: Beleg`. Kommentare: `%% Kommentar %%`. Trennlinie: `---` auf eigener Zeile.
- YAML: WikiLinks in Properties quotieren; Aliase als `aliases: [Name]` und Tags als `tags: [wissen]`.
- Formeln: `$x^2$` inline, `$$ ... $$` als Block. Mermaid-Diagramme in einem Codeblock mit Sprache `mermaid`.
- Canvas und Bases sind eigene Dateiformate. Dataview, Templater und Tasks erfordern installierte Community-Plugins; ihre Verfügbarkeit nie voraussetzen.
