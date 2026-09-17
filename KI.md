# KI-Spezifikation des KnowHow Tools

Diese Datei beschreibt verbindlich, **wie die KI der Anwendung arbeiten soll**.
Sie ergänzt die [README](README.md), die Installation, Bedienung und den gesamten
Funktionsumfang erklärt.

Es gibt drei Dokumentationsebenen:

1. `README.md` ist der allgemeine Einstieg in das Programm.
2. `KI.md` beschreibt das programmierte KI-Verhalten, die Sicherheitsregeln und
   die gemeinsam erarbeiteten Zuverlässigkeitsverbesserungen.
3. `00 Inhalt.md` im jeweils ausgewählten Vault ist die vom Nutzer bearbeitbare
   Hauptseite dieses konkreten Vaults. Ihre Regeln und ihre tatsächliche
   Ordnerstruktur werden dem Arbeitschat **Wissen erweitern** mitgegeben. Der
   getrennte Lesechat **Wissen fragen** erhält stattdessen nur passende Auszüge
   aus dem lokalen Wissensindex als Quellenkontext.

Bei Widersprüchen haben ein ausdrücklicher aktueller Nutzerauftrag und die
Sicherheitsgrenzen des Programms Vorrang. Anschließend gelten die Regeln der
Vault-Hauptseite und danach die allgemeinen Vorgaben aus dieser Datei.

---

## Empfohlene Modelle (Stand 11. September 2026)

Das Standard-Chatmodell ist **`qwen3.5:9b`** (bei Ollama gibt es kein `qwen3:9b`).
Neue Profile starten mit Thinking aus; die Eingabe kann es einschalten.
Explizit gespeicherte Einstellungen bestehender Profile bleiben erhalten.

| Modell | Kann | Kann nicht / Grenzen |
|---|---|---|
| `qwen3.5:9b` | Deutsch, Thinking, Werkzeuge, Bilder und Scans für diese App | Braucht etwa 8 GB Speicher; Thinking kostet Zeit; kein Audio, keine Cloud |
| `qwen3.5:4b` | Dieselbe Familie, schneller, Thinking möglich | Schwächer bei langen Notizen, schwierigen Bildern und Werkzeugketten |
| `qwen3-vl:8b` | Fotos, Screenshots, gescannte PDFs | Kein voller Allrounder: Text, Thinking und Vault-Werkzeuge oft schwächer |
| `nomic-embed-text` | Lokale Bedeutungs-Suche über den Wissensindex | Kein Chat, keine Bilder, keine Notizen schreiben |

Chats, Profile und Uploads liegen im Ordner `data` neben der EXE. Ein Update
gehört in denselben Ordner; `data` nicht löschen und nicht in einen neuen leeren
Ordner entpacken. Die Notizen selbst stehen im gewählten Vault.

---

## Zielbild

Die Anwendung ist keine allgemeine Chat-KI mit angehängtem Datei-Browser. Sie
ist ein lokaler **Obsidian-Meister und Datenversteher** mit zwei bewusst
getrennten KI-Bereichen:

1. **Wissen erweitern** ist der schreibende Arbeitschat. Er nimmt Informationen
   und Anhänge auf, erstellt oder ergänzt Notizen und darf ausdrücklich
   beauftragte Änderungen und Ordnungsarbeiten im Vault ausführen.
2. **Wissen fragen** ist ein reiner Lesechat. Er beantwortet Fragen aus der
   lokalen Wissensbasis und darf fehlende Zusammenhänge mit klar
   gekennzeichnetem allgemeinen Modellwissen ergänzen. Er besitzt keine
   Schreibwerkzeuge und nimmt keine Anhänge an.

Beide Bereiche besitzen getrennte Chatverläufe. Bestehende Chats aus der Zeit
vor dieser Trennung werden bei der Datenbankmigration dem bisherigen
Arbeitsbereich **Wissen erweitern** zugeordnet.

Für den Arbeitschat gilt:

- Sie kennt die tatsächliche Struktur des ausgewählten Vaults.
- Sie sucht und liest vorhandenes Wissen, bevor sie Behauptungen über den Vault
  aufstellt.
- Sie verarbeitet PDFs, Bilder, Dokumente, Quellcode und Markdown inhaltlich.
- Sie erstellt, ergänzt und bearbeitet echte Dateien, wenn dies verlangt wurde.
- Sie ordnet Quellen fachlich ein und verlinkt deren reale Vault-Pfade.
- Sie erhält bestehende Inhalte außerhalb des beauftragten Umfangs.
- Sie beendet Aufgaben erst, wenn das verlangte Ergebnis nachweislich vorliegt.
- Sie arbeitet vollständig lokal über Ollama und die kontrollierten
  Backend-Werkzeuge.

Eine Antwort wie „Ich werde die Datei jetzt bearbeiten“ ist kein Ergebnis. Die
KI muss die Bearbeitung ausführen, prüfen und erst danach berichten.

---

## Technischer Ablauf einer Anfrage

```text
Wissen erweitern                         Wissen fragen
        │                                      │
        ├─ Anhänge auswerten                   ├─ Wissensindex durchsuchen
        ├─ Änderungsfreigabe erkennen          ├─ relevante Quellen anhängen
        ├─ 00 Inhalt.md + Struktur laden       ├─ Ollama antwortet mit
        ├─ RAG-Kontext suchen                  │  Quellen + gekennzeichnetem
        ▼                                      │  allgemeinem KI-Wissen
Ollama + freigegebene Vault-Werkzeuge          └─ keine Uploads, keine Werkzeuge,
        │                                         keine Vault-Änderungen
        ├─ lesen / analysieren
        ├─ schreiben / gezielt ändern
        ├─ Quellen ablegen / einordnen
        └─ Ergebnis serverseitig kontrollieren
```

Der Chatmodus wird im Datensatz des Chats als `purpose` (`vault` oder `ask`)
gespeichert. Das Backend entscheidet anhand dieses gespeicherten Werts über die
Berechtigungen; eine bloße Frontend-Route kann den Modus nicht aufweichen.

Chat-Ordner sind davon unabhängige Organisationsdaten. Sie gruppieren nur
Verläufe in der Seitenleiste und verändern weder den Chatmodus noch Dateien,
Notizen oder Ordner im Obsidian-Vault.

Die wichtigsten Implementierungsebenen sind:

- `backend/routers/chat.py`: Anfrage, Kontext, Streaming, Werkzeugrunden,
  Modustrennung, Fortsetzung und Abschlusskontrolle
- `backend/database.py`: getrennte Arbeits- und Fragenverläufe, Chat-Ordner und
  Archivstatus einschließlich Migration vorhandener Chats
- `backend/routers/uploads.py`: Uploadzugriff ausschließlich für
  **Wissen erweitern**
- `backend/workflow.py`: Erkennung verbindlicher Schreib-, Änderungs- und
  Strukturaufträge
- `backend/tools.py`: begrenzte KI-Werkzeuge und deren Sicherheitslogik
- `backend/vault.py`: sichere Pfade und Dateioperationen innerhalb des Vaults
- `backend/vault_guide.py`: `00 Inhalt.md`, Regeln und automatisch gepflegter
  Vault-Index
- `backend/attachments.py`: Uploads, Extraktion und Bild-/PDF-Aufbereitung
- `backend/knowledge.py` und `backend/search_index.py`: lokaler Wissensindex,
  FTS5, Embeddings und hybride Suche
- `backend/note_templates.py`: Vorlagenauswahl und Notizgrundlagen

---

## Verbindlicher Abschluss eines Auftrags

Ein erkannter Auftrag besitzt ein programmatisch kontrolliertes Mindestresultat.
Eine Aufgabe gilt nicht als erledigt, nur weil das Modell überzeugend darüber
geschrieben hat.

### Erstellen

„Erstelle eine Notiz“ ist erst abgeschlossen, wenn eine neue `.md`-Datei im
Vault existiert. Ein Markdown-Entwurf ausschließlich im Chat genügt nicht.

### Ergänzen

Eine bestehende Notiz wird zuerst gelesen und anschließend wirklich mit
`notiz_ergaenzen` erweitert. Bereits vorhandener Inhalt bleibt erhalten.

### Ändern

Ein ausdrücklicher Änderungsauftrag ist die Freigabe für genau diese Änderung.
Die KI darf nicht erneut für jede Datei oder Textstelle um Bestätigung bitten.

Sie verwendet den kleinsten passenden Umfang:

1. exakte Textstelle ersetzen,
2. benannten Abschnitt ersetzen,
3. vollständige Neustrukturierung nur bei ausdrücklichem Wunsch nach anderer
   Struktur, anderem Aufbau, Layout oder Design.

Bei einer vollständigen Neustrukturierung bleiben YAML-Frontmatter und
fachliche Informationen erhalten. Eine Schutzprüfung lehnt den Vorgang ab,
wenn zu viel vorhandener Inhalt verloren gehen würde.

### Globale Änderungen

Formulierungen wie „alle Dateien“, „sämtliche Notizen“, „gesamter Vault“ oder
auch „aller mds“ bedeuten den vollständigen Vault-Umfang. Die Treffer einer
Wissenssuche sind nur Kontext und dürfen den Auftrag nicht auf drei oder sechs
Suchtreffer verkleinern.

Mechanische Änderungen wie das Entfernen aller Emojis und das Korrigieren
relativer Links laufen als kontrollierter Stapel über jede Markdown-Datei.
Codeblöcke bleiben dabei unverändert. Alle Änderungen werden vorbereitet, bevor
geschrieben wird; bei einem Schreibfehler werden bereits erfolgte Änderungen
zurückgesetzt.

### Strukturaufträge

Verlangt der Nutzer, dass PDFs, Dokumente oder Bilder nicht direkt neben
Markdown-Dateien liegen, kann die KI die Dateien wirklich verschieben. Das
Werkzeug `dateien_in_unterordner_verschieben`:

- prüft vaultweit Dokumente und Bilder,
- legt im jeweiligen Themenordner den Unterordner `Dateien/` an,
- verschiebt passende Originaldateien dorthin,
- aktualisiert betroffene Markdown- und WikiLinks,
- aktualisiert den Index in `00 Inhalt.md`,
- hält die dauerhafte Ablageregel in der Vault-Hauptseite fest,
- bricht bei Zielkonflikten vor dem Schreiben ab,
- setzt einen unvollständig fehlgeschlagenen Vorgang zurück.

Die KI darf bei einem solchen Auftrag nicht behaupten, sie habe keinen
Dateisystemzugriff. Sie besitzt keinen freien Dateisystemzugriff, aber genau
dieses begrenzte und geprüfte Werkzeug.

---

## Vollständige Antworten statt Ankündigungen

Die Chatlogik kontrolliert nicht nur Dateiänderungen, sondern auch den Abschluss
der Antwort.

- Ausführbare Vault-Aufträge aktivieren bei geeigneten Modellen automatisch
  Thinking, auch wenn es für normale Kurzfragen deaktiviert ist.
- Der Ausgaberaum beträgt abhängig von der Kontextgröße mindestens 2.048 und bis
  zu 8.192 Tokens.
- Antworten werden fortgesetzt, wenn Ollama einen Längenstopp meldet.
- Endet eine Antwort mit „Ich beginne“, „Ich werde nun“, „Ich lese zuerst“,
  einem offenen Codeblock, einem Doppelpunkt oder einem erkennbaren Satzfragment,
  wird sie automatisch fortgesetzt.
- Eine unvollständige Antwort kann bis zu drei Fortsetzungen erhalten. Der
  bisherige Text soll dabei nicht wiederholt werden.
- Das Werkzeugbudget beginnt bei 18 Runden, wächst um zwei Runden je Anhang und
  ist bei 120 begrenzt.
- Auch der Werkzeugaufruf der letzten Runde wird noch ausgeführt.
- Nach Erreichen des Werkzeuglimits schließt das Backend eindeutige Aktionen
  deterministisch ab. Bei reinen Wissensfragen erzeugt das Modell ohne weitere
  Werkzeuge eine abschließende Antwort aus den bereits gelesenen Ergebnissen.
- Der Nutzer muss nicht „weiter“, „mach jetzt“ oder denselben Auftrag mehrfach
  schreiben.

Bei mechanischen globalen Aufträgen und eindeutigen Dateiordnungen wartet das
Backend nicht auf eine möglicherweise unzuverlässige Modellentscheidung. Es
führt die freigegebene Operation direkt aus und erzeugt die Abschlussmeldung
aus den gemessenen Werkzeugergebnissen.

---

## Werkzeuge der Vault-KI

Die folgenden Werkzeuge stehen ausschließlich im Bereich **Wissen erweitern**
zur Verfügung:

| Werkzeug | Verbindliche Aufgabe |
|---|---|
| `vault_suchen` | vorhandenes Vault-Wissen suchen |
| `notiz_lesen` | eine bestehende Notiz vor Ergänzung oder Bearbeitung lesen |
| `ordner_auflisten` | tatsächliche Ordner und Dateien prüfen |
| `notiz_erstellen` | eine neue Markdown-Notiz anlegen, niemals überschreiben |
| `notiz_ergaenzen` | eine Notiz ergänzen, optional unter einer Überschrift |
| `notiz_bearbeiten` | explizit freigegebene Text-, Abschnitts- oder Strukturänderung |
| `markdown_dateien_bereinigen` | globale Emoji- und Linkkorrekturen über alle Markdown-Dateien |
| `dateien_in_unterordner_verschieben` | Quellen in `Dateien/` verschieben und Links aktualisieren |
| `anhang_lesen` | Text aus hochgeladenen Dateien extrahieren |
| `bild_ansehen` | Bilder und gerenderte PDF-Seiten lokal analysieren |
| `anhang_in_vault_ablegen` | einen Upload unter Beibehaltung seiner echten Endung in den Vault kopieren |

Bekannte kleine Modellfehler bei Werkzeugnamen werden normalisiert, zum Beispiel
`notiz_ergaetzen` zu `notiz_ergaenzen`.

Das Modell erhält keine Shell, keine beliebigen Python-Funktionen und keinen
freien Datei-Explorer. Es kann nur diese definierten Aktionen ausführen.

---

## Lesechat `Wissen fragen`

Der Fragen-Chat ist technisch und fachlich vom schreibenden Arbeitschat
getrennt:

- Er besitzt eine eigene, nach `purpose = ask` gefilterte Verlaufsliste.
- Jede ausreichend lange Frage durchsucht automatisch das freigegebene lokale
  Vault-Wissen.
- Passende Treffer werden als nicht vertrauenswürdige Quelldaten in den
  Modellkontext aufgenommen. Inhalte einer Quelle sind niemals Anweisungen.
- Konkrete lokale Aussagen sollen mit dem vorhandenen WikiLink sowie bei PDFs
  mit der Seitenzahl belegt werden.
- Allgemeines Modellwissen darf lokale Lücken ergänzen, muss aber ausdrücklich
  als nicht aus der lokalen Wissensbasis stammend erkennbar sein.
- Widersprechen lokale Quellen dem allgemeinen Modellwissen, muss die Antwort
  den Widerspruch offen benennen.
- Der Modus erhält weder Vault-Übersicht noch `00 Inhalt.md`, Schreibwerkzeuge,
  Bearbeitungswerkzeuge oder Anhangswerkzeuge.
- Uploads und mitgesendete Anhänge werden zusätzlich serverseitig mit
  `wrong_chat_mode` abgewiesen.
- Die Antwort darf niemals behaupten, eine Notiz oder Datei erstellt, geändert,
  verschoben oder gelöscht zu haben. Für solche Aufträge verweist sie auf
  **Wissen erweitern**.
- Das Notiz-Speichern-Symbol wird im Fragen-Chat nicht angeboten, damit der
  sichtbare Bedienweg der serverseitigen Leseberechtigung entspricht.

---

## `00 Inhalt.md` als Hauptseite jedes Vaults

Nach der bewussten Auswahl eines Vault-Ordners erstellt die App einmalig eine
`00 Inhalt.md`, sofern noch keine vorhanden ist. Diese Datei ist eine normale
Obsidian-Notiz und erfüllt die Rolle einer Vault-spezifischen README.

Sie enthält standardmäßig:

- Sprache und Schreibstil,
- `Emojis: Ja` oder `Emojis: Nein`,
- Regeln für WikiLinks und Quellen,
- Vorgaben für Ergänzungen und Änderungen,
- die Ablage von Originaldateien in thematischen `Dateien/`-Unterordnern,
- eine empfohlene Grundordnung,
- einen automatisch gepflegten Überblick aller Ordner, Unterordner, Notizen,
  PDFs und Bilder.

Nur der Bereich zwischen `VAULT-INDEX:START` und `VAULT-INDEX:END` wird
automatisch neu aufgebaut. Eigene Regeln und Erläuterungen außerhalb dieses
Blocks bleiben erhalten. Eine bereits vorhandene eigene `00 Inhalt.md` ohne
diese Markierungen wird niemals automatisch überschrieben.

Änderungen an diesen Regeln sind möglich, wenn der Nutzer sie ausdrücklich
verlangt. Beispiel: „Ändere Emojis auf Ja“ oder „Nutze für Quellen den
Unterordner Materialien“. Der Rest der Hauptseite bleibt dabei erhalten.

---

## Dateien, Anhänge und Quellen

### Vor der Antwort auswerten

Bei inhaltlichen Aufgaben werden relevante Anhänge vor der eigentlichen
Modellantwort ausgewertet. Eine eindeutige reine Ablageanweisung kopiert die
Originale dagegen direkt ohne Inhaltsanalyse oder Modellaufruf. Dadurch entscheidet nicht das Modell zufällig, ob es die zehnte
Datei noch liest.

- Text, Markdown und Quellcode werden lokal gelesen.
- PDFs und DOCX werden lokal extrahiert.
- Gescannte PDFs werden seitenweise gerendert und über das lokale Vision-Modell
  betrachtet.
- Mehrere Quellen werden auf Übereinstimmungen, Ergänzungen und Widersprüche
  geprüft.
- Nicht geklärte Widersprüche werden konkret mit Quelle sichtbar gemacht.

### Originaldateien im Vault

Entsteht eine Notiz oder werden Dateien ausdrücklich einsortiert, werden die
verwendeten Uploads in einen fachlich passenden Vault-Ordner kopiert. Neue
thematische Quellen gehören möglichst in `<Themenordner>/Dateien/`.

Die Dateiendung stammt immer vom Original. Ein Modell kann daher kein PDF unter
einer erfundenen `.md`-Endung speichern. Existierende Zieldateien werden nicht
überschrieben; stattdessen wird automatisch nummeriert: `image.png`, `image1.png`,
`image2.png`. Gleichzeitige Kopiervorgänge legen Dateien exklusiv an. Neue
Notizen verwenden dieselbe Nummerierung; explizite Bearbeitungen ändern weiterhin
die ausgewählte bestehende Notiz.

### Quellenlinks

- Quellenlinks müssen auf den tatsächlich vorhandenen vollständigen Vault-Pfad
  zeigen.
- Eindeutige Kurzlinks werden auf den kanonischen Pfad erweitert.
- Nicht vorhandene oder mehrdeutige PDF-, Dokument- und Bildpfade werden beim
  Schreiben abgewiesen.
- Verschobene Quellen erhalten aktualisierte Links in den betroffenen Notizen.
- Bilder werden üblicherweise als `![[Pfad/Bild.png]]` eingebettet.
- Andere Originaldateien werden als `[[Pfad/Datei.pdf|Datei.pdf]]` verlinkt.
- Relative Links werden bei einem entsprechenden Auftrag in korrekte
  vaultweite WikiLinks umgewandelt.
- Ein WikiLink auf einen Ordner wird auf dessen vorhandene `README.md`,
  `00 Inhalt.md` oder Indexnotiz aufgelöst.

Pauschale Metasätze wie „Diese Notiz basiert ausschließlich auf den angehängten
PDFs und Bildern“ werden entfernt. Die Herkunft wird durch konkrete Quellenlinks
und fachlich zugeordnete Belege nachvollziehbar.

---

## V1.3: Aufgabenfokus und Syntaxwissen

`backend/markdown_knowledge.py` liefert dem Arbeitschat eine kompakte, offline
verfügbare Referenz: Überschriften 1–6, fett/kursiv/Markierung, Listen und
Aufgaben, Code, Tabellen mit maskierten Pipes, WikiLinks mit Alias und Ankern,
Einbettungen, Callouts, Fußnoten, YAML-Properties, Tags, Formeln und Mermaid.
Die Regeln basieren auf der offiziellen Obsidian-Hilfe; sie ersetzen keine
Prüfung der Modellqualität. Canvas/Bases und Community-Plugins sind ausdrücklich
von Markdown-Syntax abgegrenzt. Die eigene Vorschau rendert nur einen Teil der
Obsidian-Funktionen.

Die Referenz liegt absichtlich im Code, damit jeder Schreibauftrag sie erhält.
`00 Inhalt.md` enthält weiterhin individuelle Regeln. Ihr großer generierter
Dateiindex wird nicht an das Modell geschickt; Regeln vor und nach dem Index
bleiben erhalten. Vor einem Chat wird eine bestehende Hauptseite nur gelesen.
Dateiänderungen des Chats aktualisieren ihren Index gebündelt am Abschluss,
auch nach einem Abbruch. Eigene Hauptseiten ohne Indexmarkierungen bleiben erhalten.

Im Arbeitschat bleiben alle Nutzereingaben erhalten: Fakten, Zahlen, Einheiten,
Beispiele, Links, Ausnahmen, Bedingungen und offene Fragen. Nur echte
Wiederholungen werden zusammengeführt; spätere Korrekturen ersetzen frühere
Angaben. Die KI soll sinnvoll strukturieren und verständlich ausarbeiten,
ergänzendes Fachwissen kennzeichnen und unbekannte konkrete Fakten offenlassen.
Überschreiten die Nutzereingaben das Zeichenbudget, endet der Auftrag mit einem
Hinweis zur Kontextgröße, bevor Dateiaktionen beginnen. Es gibt keine stille
Kürzung alter Nutzerangaben. Dies ersetzt keine semantische Qualitätsprüfung
des erzeugten Textes.

Der zusätzliche Vault-Kontext konzentriert sich auf ausdrücklich genannte
Dateien und Ordner (`"Projekt/Notiz.md"`, `[[Projekt/Notiz]]`, `Ordner "Projekt"`).
Ohne solche Ziele erhält der Arbeitschat keinen allgemeinen Ordnerindex und
keine automatische Suche im ganzen Vault. Mehrdeutige Basenamen erfordern den
vollständigen Pfad. „Dort“ kann das letzte eindeutig bestätigte Schreibziel
aufgreifen; „weiter“ erhält den ursprünglichen Auftrag. Ein expliziter globaler
Auftrag erweitert den Umfang. Allgemeine Wissensfragen dürfen weiterhin global
suchen, während Fragen mit Pfadangabe innerhalb dieses Ziels bleiben.

Such- und Lesewerkzeuge setzen den Fokus im Backend durch. Die Stichwort- und
Vektorsuche filtert Pfade vor der Trefferauswahl. Lange Notizen werden mit
`naechster_offset` vollständig gelesen. Frühere KI-Prosa und fremde Leseauszüge
entfallen im Arbeitskontext; passende bestätigte Aktionen bleiben als kompakte
Pfade und Status erhalten. Alle Nachrichten bleiben in der lokalen Datenbank.
Globale Gestaltungsregeln aus `00 Inhalt.md` und bewusst gewählte Vorlagen
bleiben als Arbeitsrahmen verfügbar, ohne den generierten Vault-Index.

Reine Ablagebefehle werden nur bei vollständigem, eindeutigem Wortlaut direkt
ausgeführt, z.B. „Datei schnell ablegen“ oder „Kopiere die Dateien in
"Projekt/Dateien"“. Ohne angegebenen Zielordner gilt der konfigurierte
Anhangordner. Es entsteht dabei keine zusätzliche Notiz. Der Chat bestätigt
jeden echten Zielpfad; fehlgeschlagene Kopien bleiben als offene Anhänge erhalten.
Mehrdeutige und zusammengesetzte Aufträge gehen weiter an das Modell.

### Schreibvorschau und Rücknahme

Die standardmäßig aktive Schreibvorschau zeigt vor `notiz_erstellen`,
`notiz_ergaenzen` und `notiz_bearbeiten` den alten/neuen Inhalt, Diff, Quellenlinks
und Zielpfad. „Anpassen“ erlaubt vollständige Inhaltskorrekturen und bei neuen
Notizen auch den Zielpfad. Externe Änderungen erfordern eine erneute Vorschau.
„Abbrechen“ beendet den Auftrag und nimmt seine bisherigen Dateiänderungen
zurück, sofern keine neueren externen Änderungen dagegenstehen. „Stopp“ erhält
den bereits bestätigten Arbeitsstand; er ist über Rückgängig zurücknehmbar.
Mechanische Stapeländerungen und Originalkopien verwenden keine Einzelnotiz-
Vorschau; sie werden durch ihren ausdrücklichen Auftrag und Rücknahme abgesichert.

Das profilgebundene Journal unter `data/profiles/<id>/vault-actions` sichert
Originalinhalte, neue Dateien und Verschiebungen einschließlich reparierter
Links. „Letzten Vault-Auftrag rückgängig“ prüft zuerst sämtliche betroffenen
Dateien auf zwischenzeitliche Änderungen und stellt dann die Originale wieder
her. Rücknahme ist auch nach Neustart möglich; es handelt sich um eine einzelne
Rücknahme, keine vollständige Versionsverwaltung. Leere Ordner dürfen bleiben.
Manuelle Editoraktionen sind keine KI-Aufträge und werden nicht mit zurückgesetzt.

### Bildwissen und serielles Vision-Modell

Nach einer Bild-/Scan-Auswertung erzeugt die App ohne zusätzliche Modellrunde
eine Markdown-Quellennotiz unter `91 Quellenwissen`. Der Quellenkopf ist kurz;
OCR und Bildbeschreibung bleiben vollständig, einschließlich erkannter
Gerätekennungen, Seitenangaben und Unsicherheiten. Ein echter Original-Link
verbindet Notiz und abgelegte Quelle. Die Quellennotiz ist im Wissensindex
auffindbar und ersetzt eine ausdrücklich verlangte ausgearbeitete Wissensnotiz
nicht. Teilanalysen sind als unvollständig gekennzeichnet. Vorschau und Quellen-
ablage sind im Profil und pro Nachricht abschaltbar. „Nur ansehen“ und reine
Direktablage erzeugen keine automatische Bildwissensnotiz.

`ai.separate_vision` ist standardmäßig aus. Nach Aktivierung wird das unter
`ollama.vision_model` gewählte, installierte und bildfähige Modell (Vorgabe
`qwen3-vl:8b`) für den gesamten vorgeschalteten Bild-/Scanblock verwendet.
Vorher wird das Chatmodell entladen; nach allen Seiten wird das Vision-Modell
entladen, bevor das Chatmodell antwortet. Kein automatischer Split und keine
parallelen großen Modelle durch Chat-Aufträge dieser App. Fehlendes VL und
spätere `bild_ansehen`-Werkzeuge fallen auf das bildfähige Chatmodell zurück.
Fehlt auch dort Vision, wird die Auswertung als unvollständig gemeldet.
Es gibt keinen automatischen Modelldownload. Externe Ollama-Clients werden
von der App nicht kontrolliert.

## Inhaltliche Qualität einer Notiz

Die KI soll aus den verfügbaren Informationen einen sofort nutzbaren Text
erstellen und nicht lediglich die Eingabe umformulieren.

Sie soll:

- Ziel, Zielgruppe und gewünschte Notizart erkennen,
- alle verlässlichen Informationen aus Vault und Anhängen nutzen,
- unklare Beschreibungen verständlich ergänzen,
- Fachbegriffe erklären, wenn dies für das Verständnis nötig ist,
- Zusammenhänge und Abhängigkeiten sinnvoll ordnen,
- Dopplungen vermeiden,
- geeignete Überschriften, Listen, Tabellen und Beispiele verwenden,
- passende vorhandene Notizen verlinken,
- keine Fakten erfinden,
- keine leeren Platzhalter oder Chat-Protokolle in den Vault schreiben,
- bei weiteren Quellen den bestehenden Text zuerst lesen und abgleichen.

Vor dem Schreiben prüft die KI still, ob der Text vollständig, fachlich
schlüssig, auffindbar und korrekt verlinkt ist.

---

## Änderungs- und Sicherheitsmodell

### Ohne Änderungsauftrag

Bestehender Inhalt wird nicht überschrieben. Die KI darf suchen, lesen, eine
neue Notiz anlegen oder auf eindeutigen Ergänzungsauftrag Inhalt anhängen.

### Mit Änderungsauftrag

Änderungen sind ausdrücklich möglich. Das gilt unter anderem für:

- Textkorrekturen,
- zusätzliche Quellen,
- andere Struktur oder Reihenfolge,
- Design und Formatierung,
- Entfernen von Emojis, Text oder Links,
- Umstellung der Ordner- und Quellenstruktur.

Die Freigabe gilt für den genannten Umfang, nicht automatisch für andere
Dateien oder Inhalte. Ein global genannter Umfang gilt dagegen tatsächlich für
alle passenden Dateien.

### Löschen

Die Chat-KI kann keine ganzen Dateien löschen. Das Entfernen ausdrücklich
genannter Inhalte innerhalb einer Notiz ist erlaubt. Löschen im Datei-Browser
bleibt eine separate, bestätigungspflichtige Nutzeraktion.

### Pfadsicherheit

Alle Vault-Pfade werden gegen die konfigurierte Vault-Wurzel geprüft. Absolute
Pfade, Laufwerkswechsel, `..`, UNC-Ziele und Ausbrüche aus dem Vault werden
abgewiesen. Versteckte Obsidian-, Versionsverwaltungs- und Systemordner werden
ignoriert.

---

## Wissensindex und RAG

Der Wissensindex ist lokal und profilgebunden. Er verarbeitet Markdown,
Textdateien, Quellcode, DOCX und PDFs in Abschnitte. PDF-Seitenzahlen bleiben
erhalten.

Die Suche kombiniert:

- SQLite FTS5 für genaue Begriffe, Namen und Kennungen,
- lokale Ollama-Embeddings für semantische Ähnlichkeit,
- eine hybride Bewertung beider Signale.

Fehlt das Embedding-Modell oder `sqlite-vec`, bleibt die Volltextsuche
funktionsfähig. Suchtreffer liefern Kontext und Quellen; sie definieren niemals
den Umfang eines globalen Dateiänderungsauftrags.

Im Bereich **Wissen fragen** ist die Wissenssuche nicht optional: Wenn ein Vault
verfügbar ist, wird sie für jede
inhaltliche Frage ausgeführt. Gibt es keine passenden lokalen Treffer, darf das
Modell trotzdem antworten, muss die Ergänzung jedoch als allgemeines KI-Wissen
kenntlich machen. Der RAG-Kontext erteilt niemals Schreibrechte.

Der Datei-Watcher gleicht Änderungen aus Obsidian im Hintergrund mit dem Index
ab. Vor jeder Wissensfrage werden zusätzlich neue/geänderte Dateien abgeglichen,
damit unmittelbar zuvor hinzugefügtes Wissen berücksichtigt wird. Ein manueller
Neuaufbau ist weiterhin möglich.

---

## Profile, Datenschutz und lokaler Betrieb

Jedes Profil besitzt einen eigenen Vault, eine eigene SQLite-Datenbank, eigene
Chats, Uploads, Einstellungen und Wissensindizes. Private und geschäftliche
Inhalte werden nicht zwischen Profilen gemischt.

Innerhalb eines Profils bleiben auch die Verläufe von **Wissen erweitern** und
**Wissen fragen** getrennt. Ein Fragenverlauf erscheint nicht im Arbeitschat und
umgekehrt.

Im normalen Betrieb:

- lauscht das Backend nur lokal,
- kommuniziert Ollama über `localhost` beziehungsweise `127.0.0.1`,
- werden Proxy-Umgebungsvariablen ignoriert,
- gibt es keine Telemetrie, Analytics oder externen CDN-Ressourcen,
- bleiben Protokolle lokal,
- werden Modelle nicht ungefragt aus dem Internet geladen.

---

## Bedienoberfläche

Die Oberfläche stellt dieselben Sicherheits- und Abschlussregeln sichtbar dar:

- Der Produktname lautet **KnowHow Tool**. Das eigene WebView2-Fenster und der
  Edge-/Chrome-App-Modus starten immer als maximiertes Fenster mit Titelleiste
  und Fensterknöpfen; die Windows-Taskleiste bleibt zugänglich.
- Die Hauptnavigation enthält die getrennten Einträge **Wissen erweitern** und
  **Wissen fragen** mit eigenem aktivem Zustand und eigener Verlaufsliste.
- Leere Zustände, Eingabehinweise, Beispielaufträge und die Kontextspalte
  benennen den aktuellen Modus ausdrücklich.
- Im Fragen-Chat steht sichtbar `Wissensbasis + KI · nur lesen`; Datei-Upload und
  das Speichern einer Antwort als Notiz fehlen dort vollständig.
- Im Arbeitschat steht sichtbar `Vault schreiben`; Datei-Upload, Ablage und
  Bearbeitungswerkzeuge bleiben dort verfügbar.
- Lese- und Schreibwerkzeuge erscheinen im Arbeitschat als Schritte.
- Schreibende Schritte sind hervorgehoben.
- Globale Bearbeitung zeigt die Zahl aller geprüften, geänderten und
  unveränderten Markdown-Dateien.
- Dateiordnung zeigt alte und neue Vault-Pfade.
- Antworten laufen beim Ansichtswechsel weiter.
- Ein abgebrochener Browserstream verliert den bereits erzeugten Text nicht.
- Chatverlauf, Anhänge und Werkzeugquellen bleiben nachvollziehbar.
Der reproduzierbare Windows-Build erzeugt weiterhin die von der bestehenden
Desktop-Verknüpfung verwendete `dist/Lokale-Wissens-KI.exe` und zusätzlich die
weitergabefähige One-File-Kopie `dist/KnowHow Tool.exe`. Frontend und
Laufzeit sind in dieser EXE enthalten; persönliche Vaults und der Ordner
`data/` werden nicht in die Weitergabedatei aufgenommen.

### Chat-Ordner und Archiv

Beide Chatbereiche besitzen eine eigene Ordnerstruktur für ihre Verläufe. Diese
Ordner liegen ausschließlich in der profilgebundenen SQLite-Datenbank und sind
nicht mit echten Verzeichnissen im Vault oder auf dem PC zu verwechseln.

- Über das Ordner-plus-Symbol lässt sich im aktuell geöffneten Bereich ein
  neuer Chat-Ordner anlegen.
- Arbeitschat-Ordner gehören zu `purpose = vault`, Fragen-Ordner zu
  `purpose = ask`; beide Listen werden getrennt geladen und dargestellt.
- Chats lassen sich per Drag-and-drop in einen Ordner, zurück auf die oberste
  Ebene `Chats` oder in den Bereich `Archiviert` verschieben.
- Ein Rechtsklick auf einen echten Chat-Ordner öffnet dessen Kontextmenü mit
  `Ordner umbenennen` und `Ordner löschen`. Beide Aktionen bleiben zusätzlich
  über die eingeblendeten Symbolschaltflächen per Maus und Tastatur erreichbar.
- Ordner können ein- und ausgeklappt werden. Die Anzahl der enthaltenen Chats
  bleibt am Ordner sichtbar. Das Kontextmenü lässt sich mit den Pfeiltasten
  bedienen und mit `Escape` oder einem Klick außerhalb schließen.
- Fällt ein Chat auf einen eingeklappten Ordner, wird dieser automatisch
  geöffnet, damit der verschobene Verlauf sichtbar bleibt.
- Das Löschen eines Chat-Ordners löscht niemals seine Chats. Die enthaltenen
  Verläufe werden von `folder_id` gelöst und erscheinen wieder direkt unter
  `Chats`. Vor dem Löschen weist ein Bestätigungsdialog ausdrücklich darauf hin.
- Archivieren löscht keinen Verlauf. Ein archivierter Chat bleibt vollständig
  erhalten und kann über `Aus dem Archiv holen` wiederhergestellt werden.
- Der Ein-/Ausklappzustand echter Chat-Ordner wird in der Datenbank gespeichert;
  die rein virtuellen Gruppen `Chats` und `Archiviert` merken ihren Zustand nur
  als lokale Oberflächeneinstellung.
- Gelöschte, unbekannte oder ungültige Ordnerziele dürfen einen Chat nicht
  unsichtbar machen. Nicht mehr zuordenbare Verläufe fallen auf die oberste
  Ebene ihres jeweiligen Chatmodus zurück.

Die Tabelle `chat_folders` speichert Ordner-ID, Name, Chatmodus, Position,
Klappzustand und Erstellzeit. Ein Chat referenziert seine Gruppe optional über
`folder_id` und besitzt zusätzlich das boolesche Feld `archived`. Diese Felder
ändern ausschließlich die Darstellung und Organisation des Verlaufs; die
Werkzeug- und Uploadberechtigungen ergeben sich weiterhin allein aus
`purpose`.

---

## Gemeinsam umgesetzte Zuverlässigkeitsverbesserungen

Die folgenden Punkte entstanden aus konkreten Fehlersituationen und sind heute
Teil des Programms:

- Eine einzelne klare Änderungsanweisung ist ausreichend; keine wiederholte
  Bestätigung je Datei.
- „Von allen Dateien“ bleibt als Umfang für den direkt folgenden konkreten
  Änderungsauftrag erhalten.
- Suchtreffer werden nicht mehr mit dem Änderungsumfang verwechselt.
- Globale Aufträge benötigen den Nachweis über alle Markdown-Dateien und können
  nicht nach drei zufällig gelesenen README-Dateien als erledigt gelten.
- Häufige Werkzeug-Tippfehler werden normalisiert.
- Entfernen von Inhalten wird nicht mit dem verbotenen Löschen ganzer Dateien
  verwechselt.
- Relative Links und reine Ordner-WikiLinks werden auf vorhandene Notizen
  normalisiert.
- Dateioperationen werden vorbereitet und bei Teilfehlern zurückgesetzt.
- Hochgeladene Originale erhalten echte, geprüfte Vault-Links.
- Unerwünschte pauschale Herkunftssätze werden aus Notizen entfernt.
- Die KI kann bestehende Struktur, Text und Design ausdrücklich ändern, lässt
  aber nicht beauftragte Inhalte bestehen.
- Antworten aus globalen Werkzeugen werden aus gemessenen Ergebnissen erzeugt
  und nicht von einem möglicherweise abbrechenden Modell frei erfunden.
- Die letzte Werkzeugrunde wird nicht mehr verworfen.
- Nach Erreichen eines Limits muss der Nutzer nicht erneut nachfragen.
- Arbeitsankündigungen und Längenstopps lösen eine automatische Fortsetzung aus.
- Vorhandene PDFs können in thematische `Dateien/`-Unterordner verschoben werden,
  während Links und Vault-Hauptseite konsistent bleiben.
- Arbeits- und Fragenchat sind in Navigation, Datenbankabfrage, Systemanweisung,
  Werkzeugzugriff und Uploadberechtigung getrennt; die Trennung beruht nicht nur
  auf unterschiedlichen Beschriftungen.
- Chatverläufe können in modusspezifischen Ordnern gruppiert und verlustfrei
  archiviert werden; das Löschen eines Ordners lässt alle enthaltenen Chats
  bestehen.

---

## Tests und Abnahmekriterien

Die automatisierten Tests unter `tests/` prüfen unter anderem:

- sichere Pfade und Dateioperationen,
- Erstellung, Ergänzung und geschützte Bearbeitung,
- Inhaltserhalt bei Neustrukturierungen,
- globale Emoji- und Linkkorrekturen,
- vollständige Wiederholungsdurchläufe ohne unnötige Änderungen,
- Dateiordnung und Linkaktualisierung,
- Erkennung natürlicher deutscher Auftragsvarianten,
- Fortsetzung unvollständiger Antworten,
- `00 Inhalt.md` und Erhalt eigener Regeln,
- Anhänge und exakte Quellenpfade,
- Migration und Filterung getrennter Arbeits- und Fragenverläufe,
- getrennte Systemanweisungen für schreibenden Arbeitschat und reinen Lesechat,
- Anlegen, Filtern, Umbenennen und Löschen von Chat-Ordnern,
- Verschieben und Archivieren von Chats sowie Inhaltserhalt nach dem Löschen
  eines Ordners,
- Backups und lokaler Wissensindex.

Vor einer Freigabe sollen mindestens ausgeführt werden:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q backend run.py
```

Zusätzlich werden alle JavaScript-Dateien mit `node --check` geprüft. Kritische
Vault-Abläufe sollen außerdem über die echte API und anschließend unabhängig am
Dateisystem kontrolliert werden.

Für V1.2 stehen dafür `tests/manual_local_validation.py` (lokales Ollama mit
synthetischen Bild-/Dokumentdaten) und `tests/manual_frozen_validation.py`
(portable EXE) bereit. Prüfergebnisse: [Release V1.2](docs/RELEASE-V1.2.md),
vorher [Release V1.1](docs/RELEASE-V1.1.md).

---

## Pflege dieser Spezifikation

Diese Datei soll aktualisiert werden, wenn sich das Verhalten der KI, ihre
Werkzeuge, Sicherheitsgrenzen, Abschlusskontrolle oder Vault-Strukturregeln
ändern. Reine Installations- und Bedienungsdetails gehören primär in die
[README](README.md).
