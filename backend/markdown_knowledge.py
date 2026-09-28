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

# Funktion F: Die Darstellung folgt dem Inhalt, nicht alles wird Fließtext.
STRUCTURE_INSTRUCTIONS = """Struktur nach Inhalt wählen:
- kurze Fakten → Stichpunkte; Vergleiche und Eigenschaften mehrerer Dinge → Tabelle;
- Abläufe und Anleitungen → nummerierte Schritte; größere Themen → ## / ### Überschriften;
- Begriffe → kurze Definition (**Begriff**: Erklärung); zusammengehörige vorhandene Notizen → [[interne Links]].
- Fließtext nur für Zusammenhänge und Begründungen. Kurze Absätze, keine leeren Überschriften."""
