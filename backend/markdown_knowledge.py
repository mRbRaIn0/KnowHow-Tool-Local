"""Kernregeln für jede neu geschriebene Obsidian-Notiz."""

MARKDOWN_INSTRUCTIONS = """Markdown / Obsidian — Kernsyntax beim Schreiben:
- Überschriften: # Titel, ## Abschnitt, ### Unterabschnitt; Leerzeichen nach #.
- **fett**, *kursiv*; Absätze durch Leerzeilen trennen.
- Listen: - Eintrag; nummeriert: 1. Schritt; Checkboxen: - [ ] / - [x].
- Tabellen: Kopfzeile, Trennzeile mit --- je Spalte, danach Datenzeilen.
- Codeblöcke mit drei Backticks und optionaler Sprache öffnen und schließen; Zitate mit >.
- Interne Links: [[Ordner/Notiz]], Dateien: [[Ordner/Datei.pdf|Name]], Bilder: ![[Ordner/Bild.png]]. Nur vorhandene Ziele verlinken.
- Tags: #wissen/thema. Properties als YAML-Frontmatter zwischen --- am Dateianfang; bestehende Metadaten erhalten.
- Callouts: > [!info] Titel und folgende Zeilen mit >. Anhänge mit ihrem tatsächlichen Vault-Pfad referenzieren.
- Seltenere Syntax steht in Obsidian_Syntax.md im Vault. Lies diese Datei nur, wenn die konkrete Aufgabe erweiterte Syntax braucht."""
