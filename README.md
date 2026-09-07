# KnowHow Tool

Eine vollständig lokale Wissens- und KI-Anwendung für Windows. Sie verbindet
deine Obsidian-Vaults und normalen Ordner direkt mit einem lokal laufenden
Ollama-Modell — ohne Cloud, ohne Konto, ohne Open WebUI.

Die verbindliche Beschreibung des KI-Verhaltens, der Werkzeuge,
Abschlusskontrollen und gemeinsam umgesetzten Verbesserungen steht in
**[KI.md](KI.md)**.

```
Chats · Dateien · Notizen · Suche · Anhänge
                    │
                    ▼
          lokales Backend (FastAPI)
                    │
                    ▼
             Ollama · qwen3.5:9b
```

Die KI arbeitet **im** Vault: Sie durchsucht ihn, liest Notizen, legt neue an,
ergänzt bestehende und sortiert angehängte Dateien ein. Sie beschreibt nicht,
was du tun könntest — sie tut es.

---

## Was die App kann

| Bereich | Stand |
|---|---|
| KI sucht, liest, legt Notizen an und ergänzt sie im Vault | fertig |
| Dateien anhängen (bis 50): Bilder, PDFs, Dokumente, Quellcode | fertig |
| Bildanalyse, Screenshots, gescannte Blätter auswerten | fertig |
| Anhänge in den Vault einsortieren und in Notizen einbetten | fertig |
| Anhänge gelten je Eingabe; abgeschickte belasten die nächste Frage nicht | fertig |
| „Nur ansehen“ verhindert das Ablegen im Vault | fertig |
| Chat mit Streaming, Verlauf, Umbenennen, Löschen, Suchen | fertig |
| Antwort läuft beim Ansichtswechsel weiter, Entwurf bleibt erhalten | fertig |
| Antwort als Obsidian-Notiz speichern | fertig |
| Vault-Browser mit echter Ordnerstruktur | fertig |
| Markdown-Editor mit Live-Vorschau, WikiLinks, Embeds | fertig |
| Volltextsuche über Notizen, Dateien, Ordner, Chats | fertig |
| Getrennte Profile (privat / Unternehmen) | fertig |
| Ollama-Statusanzeige, Modell nachinstallieren | fertig |
| Hell/Dunkel/System-Design | fertig |
| Datei-Watcher: Änderungen aus Obsidian automatisch erkennen | fertig |
| Dateien/Ordner im Vault-Baum per Ziehen verschieben | fertig |
| Semantische, hybride Suche (RAG) mit Datei- und Seitenquelle | fertig |
| Notizvorlagen und automatische Auswahl nach Anforderung | fertig |
| Zentrale `00 Inhalt.md` mit Vault-Regeln und automatisch gepflegtem Überblick | fertig |
| Lokale ZIP-Backups von Vault, Profil und Chatdatenbank | fertig |
| Reproduzierbarer Windows-`.exe`-Build mit PyInstaller | fertig |
| Eigenes App-Fenster (WebView2) statt Systembrowser | fertig |
| Sitzungsschlüssel, wechselnder Port, Host- und Ursprungsprüfung | fertig |
| Separate NAS-Bibliothek: Quellen, Tags, geprüfte Ablage, JSON-Metadaten | umgesetzt, auf bestehenden Profilen zunächst aus |

---

## Was die KI selbst im Vault tun kann

Das Modell bekommt Werkzeuge und benutzt sie von sich aus — du musst den Vault
nicht erwähnen. Es kennt die Ordnerstruktur, weil sie ihm bei jeder Anfrage
mitgegeben wird.

Ein eindeutiger Schreibauftrag wird zusätzlich vom Backend kontrolliert. „Erstelle
eine Notiz“ gilt erst als erledigt, wenn wirklich eine Markdown-Datei geschrieben
wurde. Antwortet ein Modell nur mit einem Entwurf, fordert die App die fehlende
Aktion erneut an und nutzt nach zwei erfolglosen Versuchen ein sicheres
Schreib-Fallback. Du musst den Auftrag deshalb nicht mehrfach wiederholen.

| Werkzeug | Wirkung |
|---|---|
| `vault_suchen` | durchsucht Notizen und Dateien nach einem Stichwort |
| `notiz_lesen` | liest eine Datei, bevor sie ergänzt wird |
| `ordner_auflisten` | findet den passenden Ablageort |
| `notiz_erstellen` | legt eine neue `.md`-Datei an |
| `notiz_ergaenzen` | hängt Text an, optional unter einer Überschrift |
| `notiz_bearbeiten` | ändert nach explizitem Auftrag eine Stelle, einen Abschnitt oder die Struktur |
| `markdown_dateien_bereinigen` | prüft und bearbeitet nach globalem Auftrag sämtliche Markdown-Dateien |
| `dateien_in_unterordner_verschieben` | verschiebt vorhandene PDFs, Dokumente und Bilder aus Notizordnern nach `Dateien/` und aktualisiert ihre Links |
| `anhang_lesen` | holt Text aus einem Anhang (auch PDF, DOCX) |
| `bild_ansehen` | sieht sich ein Bild oder eine PDF-Seite genauer an |
| `anhang_in_vault_ablegen` | kopiert einen Anhang in den passenden Ordner (entfällt bei „nur ansehen“) |

Beispiele:

- „Erstelle mir eine Notiz zu Windows Firewall Grundlagen." → sucht nach
  Vorhandenem, wählt den Ordner, **legt die Datei an**
- „Was habe ich zu Azure Arc notiert?" → durchsucht den Vault und antwortet mit
  den gefundenen Pfaden statt aus dem Gedächtnis
- „Ergänze meine Docker-Notiz um einen Abschnitt Volumes." → liest die Notiz und
  hängt den Abschnitt an, ohne Vorhandenes anzurühren
- „Prüfe die Docker-Notiz gegen diese weitere Quelle und ergänze sie." → liest
  beides, vermeidet Dopplungen und macht Übereinstimmungen oder Widersprüche mit
  Quellenlink nachvollziehbar
- „Ändere den Abschnitt Sicherheit und lass den Rest unverändert." → ersetzt nur
  diesen Abschnitt; „Gib der gesamten Notiz eine andere Struktur." schaltet
  ausdrücklich die geschützte Neustrukturierung frei
- „Entferne in allen Dateien sämtliche Emojis und ersetze relative Links durch
  korrekte WikiLinks.“ → liest **jede** Markdown-Datei des Vaults, nicht nur die
  ersten Suchtreffer, und führt beide mechanischen Änderungen als kontrollierten
  Stapel aus. Diese eine Anweisung ist bereits die vollständige Freigabe.

Jeder Schritt erscheint im Chat als eigene Zeile:

```
VAULT DURCHSUCHT   Zu 'SSH' gibt es im Vault noch nichts.
ORDNER ANGESEHEN   01 Wissen
NOTIZ ERSTELLT     01 Wissen/SSH Grundlagen.md
```

Schreibende Schritte sind farblich hervorgehoben und führen per Klick direkt zur
Datei.

### Verbindliche Vault-Hauptstruktur

Sobald du einen Vault-Ordner ausdrücklich auswählst, legt die App dort einmalig
`00 Inhalt.md` an. Diese normale Obsidian-Notiz ist die Hauptseite des Vaults
und wird der KI bei jedem Chat als maßgebliche Struktur mitgegeben. Sie enthält:

- Gestaltungsregeln wie `Emojis: Ja` oder `Emojis: Nein`, Sprache und Linkstil,
- Regeln für Ablage, Ergänzungen, Änderungen und Quellenprüfung,
- eine empfohlene Grundordnung, ohne bestehende Ordner umzubauen,
- einen automatisch gepflegten Überblick über Ordner, Unterordner und Dateien
  mit echten WikiLinks zu den jeweiligen Notizen, PDFs und Bildern.

Nur der deutlich markierte Indexblock wird automatisch aktualisiert. Eigene
Regeln und Erklärungen außerhalb dieses Blocks bleiben unverändert. Existiert
bereits eine eigene `00 Inhalt.md` ohne diese Markierungen, wird sie weder
ersetzt noch automatisch umgeschrieben. Ihre Regeln liest die KI trotzdem.

Die Grundstruktur ist damit **programmiert vorhanden**, wird aber inhaltlich im
Vault selbst gesteuert: „Ändere in 00 Inhalt Emojis auf Ja“ oder „Passe die
Ordnerregeln an“ bearbeitet die Hauptseite über denselben geschützten
Chat-Workflow wie jede andere Notiz. Es ist kein erneuter Programmeingriff nötig.

---

## Dateien anhängen

Links neben dem Eingabefeld sitzt ein **+**. Damit hängst du bis zu **50 Dateien**
je Chat an — Bilder, PDFs, Word-Dokumente, Tabellen, Quellcode, Markdown, alles
gemischt. Genauso funktionieren:

- **Ziehen und Ablegen** irgendwo über dem Chatbereich
- **Einfügen mit Strg+V** — praktisch für Screenshots aus der Zwischenablage

Angehängte Dateien landen zunächst in einem Zwischenbereich unter
`data/uploads/<chat>/`. Was mit ihnen geschieht, entscheidet dein Prompt:

| Du schreibst | Was passiert |
|---|---|
| „Welche Fehlermeldung zeigt der Screenshot?" | Bild wird gelesen, Antwort im Chat, nichts wird abgelegt |
| „Was steht auf dem gescannten Blatt?" | PDF-Seiten werden als Bild ausgewertet, Tabelle als Markdown zurück |
| „Sortiere diese Dateien ein und schreib eine Notiz dazu" | Dateien wandern in passende Ordner und werden in einer neuen Notiz eingebettet |
| „Fasse die vier PDFs zusammen" | alle werden gelesen, danach in den Vault übernommen |
| „Schau dir den Screenshot **nur an**" | wird gelesen, **nicht** in den Vault kopiert |

Beim Einsortieren übernimmt die KI die **tatsächlichen Inhalte** in die Notiz —
Fehlercodes, Tabellen, Gerätekennungen — nicht bloß die Dateinamen. Bilder
werden als `![[Bild.png]]` eingebettet, andere Dateien als `[[Doku.pdf]]`.

Entsteht aus Anhängen eine Notiz oder Dokumentation, werden die verwendeten
Originaldateien automatisch in einen inhaltlich passenden Vault-Ordner
**kopiert**. Die Notiz verwendet danach den tatsächlich angelegten Vault-Pfad,
zum Beispiel `[[01 Wissen/Docker/Dateien/Volumes.pdf|Volumes.pdf]]`. Eine
abschließende Prüfung ersetzt geratene Kurzlinks wie `[[Volumes.pdf]]` durch den
exakten zurückgegebenen Vault-Pfad und ergänzt fehlende Links unter „Zugehörige
Dateien“. Nicht vorhandene oder mehrdeutige PDF-, Dokument- und Bildpfade werden
beim KI-Schreiben abgewiesen. Damit bleibt keine Dokumentation übrig, die auf
eine Datei in der temporären Upload-Ablage oder auf einen erfundenen Pfad zeigt.

Pauschale Herkunftssätze wie „Diese Notiz basiert ausschließlich auf den
angehängten PDFs und Bildern“ gehören nicht in eine Wissensnotiz. Prompt und
Schreibschicht unterdrücken solche Sätze; nachvollziehbar wird die Herkunft
stattdessen über konkrete, geprüfte Vault-Links.

Gescannte PDFs ohne Textebene — der typische iPhone-Scan — werden seitenweise
gerendert und wie Bilder ausgewertet. Bis zu 8 Seiten je Dokument.

### Ein Anhang gehört zu genau einer Eingabe

Abgeschickte Anhänge verschwinden aus der Anhangsleiste. Der Zähler steht danach
wieder bei `0/50`, und die nächste Eingabe startet ohne Altlasten. Damit bezieht
sich das Modell immer auf das, was du **gerade** mitgegeben hast — oder auf gar
nichts.

Gelöscht wird dabei nichts:

- Die Dateien erscheinen weiterhin **an der abgeschickten Nachricht** im Verlauf
  und lassen sich von dort öffnen.
- Sie bleiben im Zwischenbereich liegen und sind über ihren Namen jederzeit
  wieder ansprechbar: „Welche IP hat SRV-FS02? Sieh in serverliste.png nach."
- Wurden sie in den Vault übernommen, stehen sie ohnehin dauerhaft dort.

So lädst du dieselbe Datei nie zweimal hoch, und zehn alte Screenshots verwässern
keine neue Frage. Auch die Obergrenze von 50 gilt je Eingabe, nicht je Chat.

### Hochladen ist der Normalfall — „nur ansehen" die Ausnahme

Angehängte Dateien werden standardmäßig in einen passenden Vault-Ordner
übernommen. Sagst du ausdrücklich, dass das nicht passieren soll, unterbleibt es:

> „Schau dir den Screenshot **nur an**." · „Bild **nicht hochladen**." ·
> „Nur analysieren, **nicht einsortieren**." · „Lies die PDF nur aus, **ohne sie
> zu speichern**."

In diesen Fällen bekommt das Modell das Ablage-Werkzeug gar nicht erst
angeboten — es kann also auch nicht versehentlich etwas ablegen. Die Erkennung
ist bewusst eng gefasst: Steht im selben Satz ein Schreibauftrag
(„Lies die PDF und erstelle **nur eine kurze** Notiz"), wird ganz normal abgelegt.

### Warum die Auswertung vorab passiert

Anhänge werden **immer vollständig ausgewertet, bevor das Modell antwortet** —
jedes Bild angesehen, jedes Dokument gelesen. Erst dann bekommt das Modell die
Frage, mit den Inhalten bereits im Kontext.

Das ist bewusst so gebaut. Überlässt man dem Modell die Entscheidung, ob es ein
Bild ansieht, trifft es sie bei wenigen Anhängen richtig — bei zehn Bildern aber
behauptet es, sie zu sehen, und erfindet den Inhalt. Gemessen an zehn Etiketten
mit eindeutigen Gerätekennungen:

| | Modell entscheidet selbst | Vorab ausgewertet |
|---|---|---|
| korrekt gelesene Kennungen | 0 von 10 | **10 von 10** |
| korrekte Standorte | 0 von 10 | **10 von 10** |
| Dauer | 9 s (erfunden) | 36 s (gelesen) |

Deshalb dauert eine Antwort mit vielen Anhängen länger — die Zeit geht in das
tatsächliche Lesen. Der Fortschritt steht im Chat:
„3/10 — etikett-03.png wird ausgewertet …".

Jeder Anhang wird nur **einmal** ausgewertet; das Ergebnis bleibt im Chat
hinterlegt. Folgefragen zu denselben Dateien sind deshalb sofort da.

Grenzen: 50 Dateien, 40 MB je Datei, 400 MB je Chat. Der Zwischenbereich wird
nach einer Woche automatisch geräumt; der Vault bleibt davon unberührt.

### Grenzen — bewusst gesetzt

- Ohne ausdrücklichen Änderungsauftrag bleiben bestehende Inhalte unangetastet:
  Die KI darf dann nur neu anlegen oder ergänzen.
- Ein ausdrücklicher Auftrag zum Entfernen von Text, Emojis oder Links ist eine
  Inhaltsbearbeitung und benötigt keine weitere Bestätigung. Nur das Löschen
  vollständiger Dateien bleibt gesondert geschützt.
- Globale Aufträge mit „alle Dateien“, „sämtliche Notizen“ oder „gesamter Vault“
  werden gegen jede Markdown-Datei geprüft. Such- oder RAG-Treffer dürfen den
  Umfang nicht auf wenige Dateien verkleinern.
- Verlangst du ausdrücklich eine Änderung, liest die KI die betroffene Notiz
  zuerst und bearbeitet den kleinstmöglichen Umfang: eine exakte Textstelle,
  einen benannten Abschnitt oder — nur bei ausdrücklich gewünschter anderer
  Struktur beziehungsweise anderem Design — die gesamte Anordnung.
- Bei einer vollständigen Neustrukturierung bleiben YAML-Metadaten erhalten. Ein
  Schutzmechanismus weist den Schreibvorgang zurück, wenn zu viele vorhandene
  fachliche Begriffe verloren gingen. Nicht betroffene Inhalte sollen nicht
  nebenbei verändert werden.
- **Löschen bleibt der KI verwehrt.** Entfernen über den Datei-Browser erfordert
  weiterhin deine ausdrückliche Bestätigung.
- Existiert eine Datei bereits, schlägt `notiz_erstellen` fehl; die KI muss dann
  ergänzen oder einen anderen Namen wählen.
- Neu hochgeladene Originaldateien werden beim Einsortieren **kopiert, nie aus
  dem Upload entfernt**. Ein ausdrücklicher Strukturauftrag darf bereits im
  Vault vorhandene PDFs, Dokumente und Bilder in den Unterordner `Dateien/`
  verschieben; dabei werden alle erkannten Links transaktional aktualisiert.
- Beim Ablegen bestimmt **immer das Original** die Dateiendung. Die KI darf nur
  den Namen vorschlagen — ein PDF kann so nie als `.md` im Vault landen.
- Alle Pfade laufen durch dieselbe Prüfung wie der Datei-Browser: außerhalb des
  Vaults geht nichts.
- Keine Shell, keine Kommandoausführung, kein freier Dateisystemzugriff.
- Die Zahl der Modell-Werkzeugschritte wächst mit der Zahl der Anhänge (18 + 2
  je Datei, höchstens 120). Auch der letzte zulässige Werkzeugaufruf wird noch
  ausgeführt. Danach schließt das Backend eindeutige Aktionen deterministisch
  ab oder erzeugt aus den bereits gelesenen Ergebnissen eine vollständige
  Antwort; der Nutzer muss nicht erneut „weiter“ schreiben.
- Antworten, die mit „Ich beginne“, „Ich werde nun …“ oder einem Längenstopp
  enden, werden automatisch fortgesetzt. Bei ausführbaren Vault-Aufträgen ist
  außerdem Thinking automatisch aktiv und die Antwort erhält ein größeres
  Ausgabelimit. Eine bloße Arbeitsankündigung gilt nicht als fertige Antwort.

Ohne konfigurierten Vault verhält sich die App wie ein normaler Chat. Bei einem
Modell ohne Werkzeug-Unterstützung sind Suche und intelligente Ablagewahl
eingeschränkt; eindeutige Erstellaufträge kann das Backend dennoch als neue
Notiz unter `02 KI-Notizen/` sichern.

---

## Chat-Verhalten

- **Antworten laufen weiter**, wenn du den Chat verlässt. Kommst du zurück,
  steht der aktuelle Stand da und schreibt weiter. In der Chatliste zeigt ein
  pulsierender Punkt, welcher Chat gerade antwortet.
- **Angefangene Eingaben bleiben erhalten**, wenn du wegnavigierst. Sie liegen
  nur im Arbeitsspeicher, nicht im Browser-Storage — damit sie die
  Profiltrennung nicht unterlaufen. Ein Neuladen der Seite verwirft sie.
- **Während einer Antwort kannst du weiterschreiben.** Das Eingabefeld bleibt
  bedienbar.
- Reißt die Verbindung ab (Neuladen, Fenster zu), wird der bis dahin erzeugte
  Text trotzdem gespeichert.

---

## Wissensindex und RAG

Der Bereich **Wissen** baut pro Profil einen persistenten Index in dessen
`app.db` auf. Markdown, lesbare Text- und Codedateien, DOCX und PDFs werden in
überschaubare Abschnitte zerlegt. Für PDFs bleibt die Seitenzahl am Abschnitt
erhalten.

Die Suche ist hybrid:

- Stichworttreffer sorgen für präzise Namen, Begriffe und Kennungen.
- Lokale Embeddings über das konfigurierte Ollama-Modell finden inhaltlich
  ähnliche Formulierungen.
- Beide Signale werden kombiniert; fehlt das Embedding-Modell, funktioniert die
  Stichwortsuche weiter.

Der Index wird im Hintergrund mit neuen, geänderten und gelöschten
Vault-Dateien abgeglichen. Eine Chat- oder Wissenssuchanfrage liest nur die
Suchindizes; sie startet keinen NAS-Scan. FTS5 und das optionale sqlite-vec
liefern begrenzte Treffermengen direkt aus SQLite, ohne die frühere Grenze
von 20.000 geladenen Abschnitten. Passende Abschnitte gelangen mit ihrem
Pfad und — bei PDFs — der Seitenzahl in den Modellkontext. Konkrete Aussagen
können dadurch als `[[Ordner/Notiz]]` beziehungsweise mit PDF-Seite belegt
werden. Der Button „Neu aufbauen“ im Wissensbereich erzwingt eine vollständige
Neuindizierung.

## NAS-Bibliothek: eigene Ordnung für PC und UGREEN-NAS

Die **NAS-Bibliothek** ist vom bisherigen Vault-Browser getrennt. Windows
betreibt App, SQLite, Ollama und Dokumentverarbeitung. Das UGREEN DXP2800
stellt normale SMB-Freigaben bereit; auf dem NAS sind weder Docker noch
ein KI-Dienst nötig. Dateien bleiben gewöhnliche Dateien. Es gibt keine
Tags in Dateinamen, keine Änderung eingebetteter Metadaten und keine
JSON-Datei neben jedem Original.

### Einrichten und arbeiten

1. Im gewünschten Profil **NAS-Bibliothek → Für dieses Profil aktivieren**
   wählen. Bestehende Profile bleiben bis dahin deaktiviert. Die Aktivierung
   erfasst keine Ordner automatisch.
2. Unter **Quellen & Sicherung → Quelle hinzufügen** gezielt PC-Ordner und
   NAS-Freigaben registrieren. Beispiele: `D:\Eingang` und
   `\\UGREEN\Archiv`. Die Freigabe muss bereits im Windows-Explorer erreichbar
   sein. SMB-Anmeldung und Zugangsdaten verwaltet Windows, nicht die App.
   UNC-Pfade sind als konfigurierte **Wurzel** zulässig; Datei-API-Pfade
   innerhalb dieser Wurzel müssen relativ sein. Keine Freigabe mehrfach
   unter unterschiedlichen Laufwerks-/UNC-Aliasen registrieren.
3. Für jede Quelle **Nur lesen**, **Ablage freigeben**, Überwachung und ggf.
   **JSON-Sicherungsziel** bewusst einstellen. Die Sicherung benötigt
   Schreibzugriff. Möglichst eine eigene NAS-Freigabe verwenden; weder das
   gesamte Systemlaufwerk noch das App-Datenverzeichnis freigeben.
4. **Erfassen** startet einen Hintergrundscan. Er liest Verzeichnisnamen,
   Größen und Änderungszeiten, kopiert nichts und verändert keine Originale.
   Es entsteht noch kein Inhaltsindex und keine KI-Analyse.
5. Unter **Struktur & Tags** eigene Zielordner, Tag-Gruppen und Ablageregeln
   anlegen. Ein vorhandener Ordner kann als Ziel registriert werden; ein
   neuer Ordner entsteht erst nach Vorschau und Freigabe. Die App übernimmt
   keine PC-Ordnerstruktur auf das NAS. Zielbezeichnungen und Zuordnungen
   lassen sich später bearbeiten, ohne damit physische Ordner umzubenennen.
6. In **Bibliothek** nach Quelle, relativem Ordner, Dateiendung, Tag,
   Prüfstatus oder exakten Duplikaten filtern. Die Suche erfasst Namen,
   Pfade, bestätigte Tags und Beschreibungen. Gespeicherte Filter sind
   virtuelle Sammlungen; sie bewegen keine Dateien. Auch die globale Suche
   zeigt Bibliothekstreffer als eigene Gruppe.
7. Dateien ausdrücklich auswählen. **Tags bearbeiten** funktioniert ohne
   Ollama. **KI-Vorschläge** analysiert nur die Auswahl und erstellt Entwürfe.
   Unter **Prüfen** vorhandene Metadaten mit dem Vorschlag vergleichen,
   bearbeiten, ablehnen oder übernehmen. Bei mehreren ausgewählten Dateien
   ersetzt die gemeinsame Metadateneingabe deren Tags und Beschreibung;
   die Vorschau zeigt jeden betroffenen Eintrag. Ungeprüfte KI-Entwürfe
   bleiben auch nach einem Neustart ungeprüft.
8. Erst **Ablage planen** erstellt einen separaten Vorschlag für Kopieren,
   Verschieben oder Umbenennen. Standard ist **Kopieren – Original behalten**.
   Aktion, Quelle, Ziel und Auswahl prüfen, dann **Diese Ablage freigeben**.
   Eine KI- oder Tag-Freigabe ist niemals zugleich eine Ablagefreigabe.

Die Ansicht lädt 100 Katalogeinträge pro Seite (API maximal 200). Ein
Arbeitsauftrag umfasst bis zu 500 ausdrücklich ausgewählte Dateien;
Obsidian-Notizen bis zu 100. Checkboxen, Schaltflächen und Dialoge sind
mit Tab, Umschalt+Tab, Leertaste/Enter erreichbar; Escape schließt Dialoge.
Die Datei-Detailansicht zeigt Vorschau, stabile ID und bestätigte Metadaten
in der Kontextspalte. Falls diese verborgen ist, oben **Kontextspalte** öffnen.

Tag-Gruppen beschreiben die eigene Taxonomie. Ablageregeln ordnen eine
ausdrücklich festgelegte Tag-Kombination einem freigegebenen Ziel zu. Passende
Regeln erscheinen beim Prüfen einer Datei; sie führen keine Aktionen aus.
KI-Vorschläge dürfen nur registrierte Ziele nennen und können niemals
Schreibfreigaben, Suchfreigaben oder Freigabeschritte verändern.

### Inhaltssuche und Obsidian

Alle Dateitypen lassen sich katalogisieren und manuell taggen. Programme
werden nicht ausgeführt, Archive nicht automatisch entpackt. Eine fehlende
Inhaltsauswertung wird als solche gemeldet, statt Inhalte zu erfinden.

**Inhaltssuche** gibt die ausgewählten Dateien ausdrücklich für Extraktion,
FTS5, lokale Embeddings und den Chat-Kontext frei. Unter **Struktur & Tags**
können stattdessen bestimmte Ordner einschließlich künftig erfasster Dateien
freigegeben werden. Ein expliziter Ausschluss einer Datei hat Vorrang vor
einer Ordnerfreigabe. Widerrufen entfernt ihren Suchindex. Metadaten bleiben
im Katalog. Die Dateien werden erst nach einem Scan oder expliziten
Indexauftrag verarbeitet, nicht durch eine Suche.

**Inhalte durchsuchen** durchsucht diese freigegebenen Inhalte. Die
Wissenssuche und RAG unterscheiden Vault- und Bibliotheksquellen; vorhandene
PDF-Seitenangaben bleiben erhalten. Ohne Embedding-Modell funktioniert die
Volltextsuche weiter. Nach Einrichtung eines Modells die betreffende Auswahl
erneut für Inhaltssuche freigeben, um fehlende Embeddings nachzuholen.

**Obsidian-Notiz** erzeugt nach Vorschau eine neue Markdown-Notiz im
ausgewählten Vault mit bestätigten Beschreibungen, Tags, Datei-IDs und
geprüften `file:`-Verweisen. Bestehende Notizen werden nicht überschrieben.
Originale bleiben außerhalb des Vaults. Dateiverweise sind Momentaufnahmen:
nach späteren Verschiebungen eine neue Notizvorschau erzeugen; die stabile
Bibliotheks-ID hilft beim Wiederfinden. Obsidian/Windows müssen das Öffnen
lokaler bzw. SMB-Dateilinks erlauben. Das gesamte NAS wird niemals zum Vault.

### Speicherorte, Sicherung und Wiederherstellung

| Ort | Inhalt |
|---|---|
| PC: `data/profiles/<profil>/app.db` | Führender Katalog, Tags, Struktur, Entwürfe, Aufträge, Vorgangsprotokoll und selektiver Suchindex |
| NAS-Sicherungsquelle: `.wissens-ki/<profil>/catalog.json` | Zuletzt geprüfte JSON-Metadatensicherung |
| Derselbe Ordner: `catalog.previous.json` | Vorherige Sicherungsversion |
| PC: `app.before-library-v1.db`, `app.before-catalog-v1.db` neben `app.db` | Konsistente Datenbankkopien vor den additiven Schemaänderungen |

SQLite gehört auf den PC, nicht auf SMB. Die JSON-Datei ist keine zweite
Datenbank und kein Mehrgeräte-Sync. Pro Profil nur eine verwaltende
App-Instanz betreiben. Quellen, Tags und Jobs bleiben profilgebunden;
ausstehende Aufträge behalten ihr ursprüngliches Profil bei einem Wechsel.

JSON enthält bestätigte Metadaten, stabile Datei-IDs, relative Speicherorte
und eigene Struktur. Vollständige extrahierte Texte, Embeddings und
ungeprüfte Vorschläge sind ausgeschlossen. Änderungen werden gebündelt
gesichert. Erst nach vollständigem Schreiben und erneutem Einlesen wird die
temporäre Version veröffentlicht. Bei einem NAS-Ausfall bleibt die lokale
Änderung erhalten und **JSON-Sicherung ausstehend** sichtbar. Der Dienst
versucht offene Sicherungen erneut; **JSON jetzt sichern** stößt dies auch
manuell an. Der Verwaltungsordner wird bei Scans ausgeschlossen.

Zum Wiederherstellen im **gleichen Profil** die Quellen registrieren und
erfassen, dann **Quellen & Sicherung → Wiederherstellen → Sicherung lesen**.
Alte Quellen den aktuell registrierten Orten zuordnen, Vorschau prüfen und
erst dann übernehmen. Optional steht die vorherige JSON-Version bereit.
Nicht zuordenbare Dateien und vorhandene Struktureinträge werden nicht
überschrieben. Stabile IDs bleiben bei eindeutiger Zuordnung erhalten.
Suchfreigaben müssen nach der Wiederherstellung erneut erteilt werden.
Bei Verlust der ganzen App zuerst die Profilkonfiguration aus dem lokalen
ZIP-Backup zurückholen, damit die ursprüngliche Profil-ID erhalten bleibt.

Manuell verschobene Dateien werden nicht heimlich zusammengeführt:
Quellen neu erfassen, beim alten fehlenden Eintrag **Verschobene Datei
zuordnen** öffnen und die ID des neu erfassten Eintrags angeben. Die Vorschau
zeigt die Zuordnung; vorhandene SHA-256-Werte werden geprüft. Ohne einen
früheren Hash ist die Identität nicht beweisbar und muss vom Nutzer anhand
der Dateien bestätigt werden. Gleiche Namen in verschiedenen Quellen und
identische Kopien bleiben ansonsten getrennte Einträge. **Duplikate prüfen**
berechnet Hashes nur für die ausgewählten Dateien und löscht nichts.

**Die Metadatensicherung ersetzt kein Backup der NAS-Originaldateien.**
Auch das vorhandene App-ZIP-Backup umfasst Vault, Profil und Datenbank,
aber nicht sämtliche Bibliotheksquellen. NAS-Originale separat sichern.

### Unterbrechungen und Sicherheit

Unter **Aufträge** lassen sich Arbeiten pausieren, fortsetzen und Fehler
einsehen. Die Warteschlange liegt dauerhaft in SQLite. Beim Neustart
werden unterbrochene laufende Aufträge pausiert angeboten; wartende,
bereits beauftragte Arbeiten können anlaufen. Scans beginnen erneut,
mehrteilige Analyse-/Hashaufträge setzen am gespeicherten Eintrag fort.
Analyse pausiert spätestens zwischen Dateien bzw. nach dem laufenden
Modell-/Parseraufruf, Kopieren an Blockgrenzen. Ein Windows-SMB-Aufruf kann
bis zum Betriebssystem-Timeout blockieren. Navigation und Chat bleiben
unabhängig bedienbar.

Nur registrierte Wurzeln sind zugänglich. Relative Pfade werden gegen
Traversal, Laufwerkswechsel, NTFS-Datenströme, Symlinks und Junctions geprüft.
Der ausgewählte Vault ist vom Bibliothekszugriff ausgeschlossen. Die API
verlangt Profil-, Datei- und Revisionsbezug. Chatwerkzeuge erhalten keine
Möglichkeit, Bibliotheksfreigaben zu erteilen.

Dateiaktionen prüfen Quelle, Ziel, Freigaben und Revision erneut. Kopieren
schreibt gestreamt in eine eigene `.lka-*.partial`-Datei, prüft SHA-256 und
veröffentlicht ohne Überschreiben. Verschieben entfernt die Quelle erst
nach erfolgreicher Zielprüfung und erneuter Prüfung der Quelle. Das
Vorgangsprotokoll hält Zwischenstände fest. Bei Konflikten stoppen; unter
**Aufträge → Details** prüfen und erst nach Klärung fortsetzen. Geschützte
Zwischendateien nicht eigenständig verschieben oder verändern. Bereits
veröffentlichte Kopien können bei einem Fehler neben dem Original bleiben.

Unter **Prüfen → Angewendet** können unveränderte Metadatenänderungen
zurückgenommen werden. Abgeschlossene Verschiebungen/Umbenennungen erzeugen
für das Rückgängigmachen eine neue Vorschau. Belegte ursprüngliche Ziele
oder später veränderte Dateien verhindern die Rücknahme. Kopien werden
nicht durch eine automatische Löschfunktion zurückgenommen. Eine nicht
erreichbare NAS-Quelle behält ihren Katalog; sie gilt nicht als leer.

### GitHub-Bausteine und vollständig lokaler Betrieb

| Projekt | Verwendung in dieser App |
|---|---|
| [TagSpaces](https://github.com/tagspaces/tagspaces) | Bedienvorbild; kein eingebetteter Code, keine Abhängigkeit oder verpflichtende Formatkompatibilität |
| [Watchdog](https://github.com/gorakhargosh/watchdog) | Windows-Dateiüberwachung; NAS-Quellen und UNC-Wurzeln verwenden `PollingObserver` (standardmäßig 300 Sekunden) |
| [sqlite-vec](https://github.com/asg017/sqlite-vec) | Auf **0.1.9** fixierter lokaler Vektorindex, ergänzt durch SQLite FTS5; Windows-DLL in der EXE enthalten |
| [Docling](https://github.com/docling-project/docling) | Optionales separates Analysepaket **2.123.1**, EasyOCR **1.7.2**, ohne Laufzeit-Download |
| [Ollama Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs) | JSON-Schema für KI-Vorschläge plus serverseitige Pydantic-Prüfung; keine Tool-Ausführung im Klassifikationsaufruf |

Tags und Struktur hängen nicht von sqlite-vec ab. Falls die Erweiterung
fehlt, bleiben Katalog und Volltextsuche verfügbar. Vektoren sind
wiederherstellbarer Cache; nach zwischenzeitlichem Betrieb ohne Erweiterung
werden die Vektortabellen aus den lokal gespeicherten Embeddings neu aufgebaut.

Ohne Docling bleiben die vorhandenen Text-, DOCX- und PDF-Parser verfügbar.
Einfache Textdateien werden bis 5 MiB verarbeitet. KI-Vorschläge erhalten
maximal 32.000 Zeichen mit sichtbarem Kürzungshinweis. Für komplexe PDFs,
OCR, XLSX, PPTX und weitere unterstützte Dokumentformate ist Docling optional.
Wenn eingerichtet, übernimmt es auch PDF/DOCX. Der getrennte Worker ist
auf 200 MiB, 300 Seiten und 180 Sekunden je Dokument begrenzt. Nicht
unterstützte bzw. zu große Dateien bleiben manuell verwaltbar.

Docling wird **nicht** beim normalen Start installiert. Nur bewusst ausführen
(dieser Einrichtungsschritt benötigt Internet und zusätzlichen Speicher):

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-docling.ps1
# Bei Verwendung der EXE: Pfad zu separat installiertem Python 3.12 angeben
powershell -ExecutionPolicy Bypass -File .\setup-docling.ps1 -Python 'C:\Python312\python.exe'
```

Das Skript erstellt `.venv-docling`, installiert `requirements-docling.txt`
und lädt Layout-, Tabellen- und deutsche/englische OCR-Modelle nach
`data/models/docling`. Unter **Docling einrichten** die ausgegebenen Python-
und Modellpfade eintragen. Mit `-WithoutModels` lassen sich nur die Pakete
einrichten und bereits vorhandene Modelle anschließend manuell zuordnen.
Die normale EXE bleibt ohne dieses Paket nutzbar. Fehlende Modelle führen
im Betrieb zu einem Fehler, niemals zu einem automatischen Download.

Der Worker verwendet ausschließlich lokale Dateien und Modelle, deaktiviert
Remote-Services sowie OCR-Downloads und blockiert Python-Netzwerkverbindungen.
Das folgt den [Docling-Hinweisen zum Offlinebetrieb](https://docling-project.github.io/docling/usage/advanced_options/).
Für zusätzliche Absicherung kann die getrennte Python-Umgebung per
Windows-Firewall vom Internet ausgeschlossen werden. App und Ollama bleiben
auf dem PC, nur SMB-Verkehr geht zum NAS. Keine Telemetrie, CDN-Schriften
oder Cloud-Analyse. Ersteinrichtung von Python-Paketen und ausdrücklich
gestartete Modell-Downloads sind von diesem Offlinebetrieb zu unterscheiden.

### Prüfstand und Grenzen

Das [Prüfprotokoll](docs/NAS-VALIDIERUNG.md) dokumentiert Testumfang,
Windows-Paketprüfung und die separat am Zielgerät zu prüfenden Punkte.

Die automatisierten Tests prüfen read-only Scans/Analysen, persistente
Entwürfe, Profiltrennung, sichere Pfade, Zielkonflikte, Quellenänderungen,
Wiederaufnahme nach Veröffentlichung, Rücknahme, JSON-Wiederherstellung,
100.000 paginierte Katalogeinträge und Treffer hinter der früheren
20.000-Abschnittsgrenze. Bestehende Chat-, Anhang-, Vault- und Backup-Tests
bleiben Teil derselben Suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

KI-Antworten werden in den Sicherheitstests simuliert; die Qualität eines
konkreten Ollama-Modells ist damit nicht bewertet. Bei einem Update einer
vorhandenen Python-Installation neue Abhängigkeiten einmal ausdrücklich mit
`.\.venv\Scripts\python.exe -m pip install -r requirements.txt` installieren.
Der normale Start lädt fehlende Pakete oder Modelle nicht nach.

Die UI wird mit isolierten PC-/NAS-Testordnern geprüft. Vor produktiven
Verschiebungen auf einem konkreten UGREEN-Gerät zuerst eine eigene
Testfreigabe verwenden: Scan und Tagging, Kopie, NAS-Trennung während einer
Kopie, erneute Verbindung/Fortsetzen, Zielkonflikt und Rücknahme einer
Verschiebung durchspielen. Echte SMB-Ausfälle, Gerätegeschwindigkeit und
Docling mit heruntergeladenen Modellen müssen auf dem Zielsystem separat
geprüft werden. Der 100.000-Einträge-Test misst die lokale Katalogabfrage,
nicht den Durchsatz eines NAS-Vollscans. Die App ist kein Schutz gegen
gleichzeitige absichtliche Dateimanipulation durch andere Programme.

## Vorlagen

Mitgeliefert werden **Standard**, **Vokabeln**, **IT-Wissen**, **Projekt**,
**Meeting** und **Lernzettel**. Bei einem Schreibauftrag wählt die App anhand der
Anforderung automatisch die passendste Vorlage. Das Modell übernimmt sinnvolle
Abschnitte, ersetzt Platzhalter, lässt Unpassendes weg und darf fehlende
Erklärungen ergänzen.

Eigene Markdown-Vorlagen im konfigurierten Vault-Ordner (standardmäßig
`00 Templates`) überschreiben eine gleichnamige mitgelieferte Vorlage. Im
Bereich **Vorlagen** lassen sich die Standarddateien einmalig in den Vault
kopieren und direkt als neue Notiz verwenden.

## Backups und Windows-EXE

Unter **Einstellungen → Daten → Backup** entsteht eine ZIP-Datei mit:

- dem vollständigen Vault,
- der Profilkonfiguration,
- einer konsistenten Kopie der SQLite-Chat- und Wissensdatenbank.

Backups liegen unter `data/backups/<profil>/` und werden nie automatisch in eine
Cloud übertragen.

Für eine eigenständige Windows-Datei ist ein reproduzierbarer PyInstaller-Build
enthalten:

```powershell
powershell -ExecutionPolicy Bypass -File .\build-exe.ps1
```

Das Skript installiert nur die Build-Abhängigkeit aus
`requirements-build.txt` und erzeugt `dist/Lokale-Wissens-KI.exe` sowie die
identische Weitergabekopie `dist/KnowHow Tool v1.0.exe`. Liegt eine dieser
EXE dort innerhalb dieses Projektordners, verwendet sie automatisch das bereits
vorhandene `data/` des Projekts und damit dieselben Profile, Chats und
Einstellungen wie `start.bat`. Wird die EXE an einen anderen Ort kopiert, legt
sie ihre beschreibbaren `data/`-Dateien weiterhin portabel neben sich ab.
Frontend und Standardvorlagen sind eingebettet. Das Build-Skript legt README und optionale
Docling-Einrichtung neben die EXE. Ollama und das gewählte Modell bleiben weiterhin lokale
Voraussetzungen.

`Lokale-Wissens-KI.exe --self-test "C:\Temp\wissens-ki-test.json"` prüft
Offline-Import, FTS5, sqlite-vec und gebündelte Dateien ohne Start von Ollama
oder Öffnen eines Profils. Die EXE ist ohne eigenes Zertifikat nicht digital
signiert; Windows SmartScreen kann daher eine Warnung anzeigen.

---

## Voraussetzungen

- Windows 10/11
- Python 3.10 oder neuer
- [Ollama](https://ollama.com) installiert
- Ein Chat-Modell, empfohlen `qwen3.5:9b` (Text **und** Bilder, ~6,6 GB)

Modell installieren, falls noch nicht vorhanden:

```bash
ollama pull qwen3.5:9b
```

Die App kann das Modell auch selbst herunterladen — sie bietet den Download an,
sobald sie merkt, dass es fehlt.

---

## Starten

Doppelklick auf `start.bat`. Beim ersten Start legt das Skript die
Python-Umgebung an und installiert die Abhängigkeiten; danach dauert der Start
nur noch wenige Sekunden.

Der Starter prüft der Reihe nach:

1. Läuft die App bereits? Dann wird nur ihr Fenster geöffnet.
2. Läuft Ollama? Falls nicht, wird der Dienst gestartet.
3. Welcher Port ist frei? Das Betriebssystem vergibt bei jedem Start einen
   anderen.

Die Oberfläche erscheint anschließend **als maximiertes Fenster** in einem eigenen
Fenster (WebView2) — ohne Adresszeile, ohne Tabs, ohne fremde Seiten daneben.
Titelleiste, Fensterknöpfe und die Windows-Taskleiste bleiben zugänglich.
Fehlt WebView2, weicht die App auf Edge oder Chrome im maximierten App-Modus mit eigenem, leerem Profil
aus, und erst danach auf den Standardbrowser.

### Desktop-Verknüpfung mit Programm-Icon

Einmalig in PowerShell im Projektordner ausführen:

```bash
powershell -ExecutionPolicy Bypass -File .\Verknuepfung-erstellen.ps1
```

Das legt „KnowHow Tool" auf dem Desktop an — mit dem Programm-Icon aus
`assets/Lokale-Wissens-KI.ico`. Ein Doppelklick startet über
`start-hidden.vbs` bevorzugt die aktuelle `dist/Lokale-Wissens-KI.exe` ohne
sichtbares Konsolenfenster. Fehlt die EXE, dient `start.bat` als Rückfall.

| Aufruf | Ergebnis |
|---|---|
| ohne Schalter | aktuelle EXE verdeckt, `start.bat` als Rückfall |
| `-MitFenster` | `start.bat` sichtbar — praktisch zum Mitlesen bei Problemen |
| `-Exe` | zeigt auf `dist\Lokale-Wissens-KI.exe` (erst `build-exe.ps1` ausführen) |
| `-Name "KI"` | anderer Name auf dem Desktop |

Alle Varianten bekommen dasselbe Icon. Fehlt die `.ico`-Datei, erzeugt das
Skript sie automatisch neu.

Das Icon selbst entsteht aus dem App-Logo und lässt sich jederzeit neu bauen:

```bash
.venv\Scripts\python.exe assets\icon_erzeugen.py
```

Es enthält alle Größen von 16 bis 256 Pixeln, die Windows für Desktop,
Taskleiste und Explorer braucht. Dieselbe Datei verwendet auch die EXE.

### Von Hand starten

```bash
.venv\Scripts\python.exe run.py
```

Optionen: `--port 5050`, `--host 127.0.0.1`, `--no-browser`, `--reload`.
Mit `--no-ollama` startet die App ohne automatischen Ollama-Dienststart,
zum Beispiel für reines Katalogisieren und Tagging.

---

## Erste Schritte in der App

1. **Vault auswählen** — auf der Übersicht auf „Ordner auswählen" klicken und
   deinen Obsidian-Vault wählen, zum Beispiel `D:\AI-Wissen`.
   Die Vault-Funktionen lesen und schreiben ausschließlich innerhalb dieses
   Ordners; die App legt dort die zentrale `00 Inhalt.md` an.
2. **Wissen erweitern** — im gleichnamigen Arbeitschat Informationen eingeben
   oder Dateien über das **+**, per Ziehen oder mit `Strg+V` anhängen. Dieser
   Bereich darf Notizen im Vault anlegen, ergänzen und organisieren.
3. **Wissen fragen** — im getrennten Fragen-Chat Antworten aus der lokalen
   Wissensbasis und ergänzendem, klar gekennzeichnetem KI-Wissen erhalten. Dieser
   Bereich besitzt keinen Schreibzugriff auf den Vault.
4. **Antwort sichern** — im Arbeitschat landet eine Antwort über das Notiz-Symbol
   als normale `.md`-Datei im Vault.
5. **Dateien bearbeiten** — im Bereich „Dateien" mit Live-Vorschau; `Strg+S`
   speichert.

Deine bestehende Ordnerstruktur bleibt unverändert. Obsidian kann parallel
weiterlaufen: Die App schreibt normales Markdown in UTF-8. Ihre einzige
Vault-Hauptdatei `00 Inhalt.md` ist selbst eine sichtbare und bearbeitbare
Obsidian-Notiz, kein verstecktes App-Format. Der Ordner `.obsidian` wird komplett
ignoriert.

---

## Datenschutz

Standardmäßig verlässt nichts diesen Rechner.

- Der Server lauscht nur auf `127.0.0.1`, auf einem bei jedem Start neu
  vergebenen Port.
- **Sitzungsschlüssel**: Jeder Start erzeugt einen neuen Schlüssel. Nur das
  App-Fenster bekommt ihn — über die Startadresse und danach als Cookie mit
  `HttpOnly` und `SameSite=Strict`. Ohne ihn liefert die App keinerlei Daten,
  auch nicht an eine andere Seite im selben Browser.
- **Host-Prüfung**: Anfragen, die über eine fremde Domain hereinkommen, werden
  abgewiesen. Das schließt DNS-Rebinding aus, bei dem eine Angreiferseite auf
  `127.0.0.1` zeigt und dem Browser dadurch als gleicher Ursprung gilt.
- **Ursprungs-Prüfung**: Jeder schreibende Zugriff, der von einer anderen Seite
  ausgelöst wurde, wird abgewiesen (CSRF) — für alle Bereiche, nicht nur die
  NAS-Bibliothek.
- Die Oberfläche läuft in einem eigenen Fenster statt im Systembrowser: keine
  Tabs, keine Erweiterungen, keine fremden Seiten in derselben Umgebung.
- Abgewiesene Zugriffe stehen mit Grund in `data/logs/app.log`.
- Im **Offline-Modus** (Standardeinstellung) sind ausschließlich Verbindungen zu
  `localhost` / `127.0.0.1` erlaubt. Ein entfernter Ollama-Server lässt sich gar
  nicht erst speichern.
- Eine strikte Content-Security-Policy verhindert, dass die Oberfläche externe
  Ressourcen nachlädt. Es gibt keine CDN-Abhängigkeiten: Schriften kommen aus
  Windows, Markdown-Rendering ist selbst geschrieben.
- Bildanalyse und Textextraktion laufen vollständig lokal — die Bildanalyse über
  dein Ollama-Modell, PDF und DOCX über lokale Python-Bibliotheken.
- Keine Telemetrie, keine Analytics, kein Crash-Reporting. Protokolle bleiben in
  `data/logs/app.log`.
- Der HTTP-Client ignoriert Proxy-Umgebungsvariablen (`trust_env=False`).

Bewusst gestartete Einrichtungsschritte können Internet benötigen: der
Download eines Ollama-Modells, die Python-Ersteinrichtung und das optionale
Docling-Setup. Im regulären Betrieb werden Modelle nie automatisch geladen.

### Dateizugriff

- Für Vault-Werkzeuge ist nur der konfigurierte Vault-Ordner freigegeben.
  Die separate NAS-Bibliothek greift ausschließlich auf ihre ausdrücklich
  registrierten Quellen zu; Dateiaktionen erfordern dort eigene Freigaben.
- Jeder Pfad wird gegen die Vault-Wurzel geprüft. `..`, absolute Pfade,
  Laufwerksangaben und UNC-Pfade werden abgewiesen.
- Das Modell kann keine Dateien selbst auswählen, keine Shell-Befehle ausführen
  und keine Pfade außerhalb des Vaults erreichen. Dateiänderungen laufen
  ausschließlich über klar umrissene Backend-Funktionen.
- Löschen im Datei-Browser erfordert immer eine ausdrückliche Bestätigung.
- Ein gelöschter Chat nimmt seine Anhänge mit: Originaldateien und der daraus
  gewonnene Text unter `data/uploads/` werden zusammen mit dem Verlauf entfernt.
- Anhänge sind an ihr Profil gebunden. Ein Chat eines anderen Profils ist auch
  über seine Kennung nicht lesbar.

---

## Profile: privat und Unternehmen getrennt

Jedes Profil hat einen eigenen Vault **und** eine eigene Datenbank:

```
data/profiles/privat/app.db
data/profiles/unternehmen/app.db
```

Chats, Nachrichten, Anhänge, Wissensindex und Bibliothekskatalog werden nie zwischen
Profilen geteilt. Ein Profil sieht ausschließlich seinen Vault und seine
eigenen Bibliotheksquellen. Auf einem Firmenrechner richtest du einfach nur das Unternehmensprofil
ein.

Die farbige Kante am linken Bildschirmrand und die Beschriftung neben dem Logo
zeigen jederzeit, in welchem Profil du gerade arbeitest.

Wird ein Profil gelöscht, verschwindet nur seine Konfiguration — die Datenbank
bleibt unter `data/profiles/<id>/` liegen, damit kein Verlauf verloren geht.

---

## Multi-Device

Die App übernimmt **keinen** Sync. Der Vault ist ein normaler Ordner und bleibt
mit Obsidian Sync, iCloud oder jeder anderen Ordner-Synchronisation kompatibel.

Gedachte Arbeitsteilung:

- **iPhone** — Blätter digitalisieren, Fotos, schnelle Notizen
- **iPad** — lesen, lernen, Notizen ergänzen
- **Windows-PC** — Programmieren, große Dateien, KI, Ollama, Hauptverwaltung

Ein per iPhone gescanntes PDF, das über den Sync im Vault landet, lässt sich am
PC anhängen und auswerten.

---

## Projektstruktur

```
Ollama-Obsidian-UI/
├── KI.md                  verbindliche KI-, Werkzeug- und Verhaltensspezifikation
├── backend/
│   ├── main.py            FastAPI-App, Sicherheits-Header, Frontend-Auslieferung
│   ├── config.py          Profile und Einstellungen (data/config.json)
│   ├── deps.py            gemeinsame Abhängigkeiten der Router
│   ├── ollama_client.py   Ollama-REST-Anbindung inkl. Offline-Schutz
│   ├── vault.py           sichere Pfadauflösung, Ordnerbaum, Datei-I/O
│   ├── vault_guide.py     00-Inhalt-Hauptseite, Regeln und Vault-Index
│   ├── tools.py           Werkzeuge, die das Modell benutzen darf
│   ├── workflow.py        erkennt/prüft verbindliche Erstell- und Ablageaufträge
│   ├── attachments.py     Anhänge: Ablage, Textextraktion, Bildaufbereitung
│   ├── knowledge.py       Chunking, lokale Embeddings, hybride RAG-Suche
│   ├── search_index.py    FTS5 und optionale sqlite-vec-Suche ohne Korpuslimit
│   ├── knowledge_worker.py Hintergrundabgleich des ausgewählten Vaults
│   ├── library_*.py       NAS-Katalog, sichere Pfade, Jobs, Ablage, Sicherung
│   ├── docling_worker.py  isolierte optionale Offline-Analyse
│   ├── note_templates.py  Vorlagenbibliothek und automatische Auswahl
│   ├── watcher.py         erkennt externe Änderungen aus Obsidian
│   ├── backups.py         konsistente lokale ZIP-Backups
│   ├── database.py        SQLite pro Profil, getrennte Arbeits-/Fragen-Chats
│   └── routers/
│       ├── system.py      Status, Modelle, Modell-Download, Explorer
│       ├── chat.py        Chats, Anhang-Auswertung, Antwort-Streaming
│       ├── files.py       Dateien und Ordner
│       ├── uploads.py     Anhänge hochladen und verwalten
│       ├── search.py      Volltextsuche
│       ├── knowledge.py   Wissensindex, Neuaufbau und hybride Suche
│       ├── library.py     profilgebundene /api/library-Schnittstellen
│       ├── templates.py   Vorlagen anzeigen und in den Vault kopieren
│       ├── backups.py     Backups anlegen und herunterladen
│       └── settings.py    Einstellungen und Profile
├── frontend/
│   ├── index.html
│   ├── css/app.css
│   └── js/
│       ├── api.js         Backend-Zugriff, SSE-Streams, Upload
│       ├── chatstream.js  laufende Antworten und Entwürfe
│       ├── markdown.js    Markdown mit WikiLinks und Embeds
│       ├── store.js       Zustand, Dateiindex, Navigation, Design
│       ├── util.js        DOM-Helfer, Dialoge, Meldungen
│       └── views/         dashboard, chat, files, Wissen, Bilder, Notizen, Vorlagen
├── data/                  config.json, profiles/, uploads/, backups/, logs/
├── templates/             mitgelieferte Markdown-Notizvorlagen
├── tests/                 Workflow- und Wissensindex-Tests
├── run.py                 Starter mit Port- und Ollama-Prüfung
├── Lokale-Wissens-KI.spec PyInstaller-Konfiguration
├── assets/
│   ├── Lokale-Wissens-KI.ico   Programm-Icon (Verknuepfung und EXE)
│   └── icon_erzeugen.py        erzeugt das Icon aus dem App-Logo neu
├── build-exe.ps1          reproduzierbarer Windows-EXE-Build
├── start.bat              Windows-Start inkl. Ersteinrichtung
├── start-hidden.vbs       Start ohne Konsolenfenster
└── Verknuepfung-erstellen.ps1
```

---

## Einstellungen

Erreichbar über das Zahnrad oben rechts.

| Bereich | Inhalt |
|---|---|
| Profile | anlegen, wechseln, löschen |
| Ollama | Server, Chat-Modell, Embedding-Modell |
| Daten | Vault-, Anhang- und Vorlagenordner, ZIP-Backup |
| KI | Temperatur, Kontextgröße, RAG-Treffer, Gedankengang, System-Anweisung |
| Datenschutz | Offline-Modus, externe Links, Telemetrie |
| Oberfläche | Hell / Dunkel / System |

Alles landet in `data/config.json`. `config.example.json` zeigt eine
Beispielkonfiguration mit zwei Profilen.

### Empfehlungen für RTX 3060 (12 GB)

- Chat-Modell: `qwen3.5:9b` — passt vollständig in den VRAM
- Kontextgröße: 8192 als Ausgangswert; 16384 geht meist noch gut.
  Bei Anhängen hebt die App den Wert automatisch an (bis 32768), damit die
  ausgewerteten Inhalte hineinpassen.
- Gedankengang für normale Chats: **aus** lassen. Mit Thinking dauert eine kurze
  Antwort rund 50 Sekunden statt 2. Bei ausführbaren Vault-Aufträgen aktiviert
  die App Thinking automatisch, damit sie den vollständigen Auftrag zuverlässig
  plant, ausführt und abschließt.
- Embedding-Modell: `nomic-embed-text` (274 MB) reicht für die lokale
  semantische Suche völlig

---

## Tastenkürzel

| Kürzel | Wirkung |
|---|---|
| `Strg + K` | Suche fokussieren |
| `Strg + V` | Screenshot oder Datei aus der Zwischenablage anhängen |
| `Strg + S` | Notiz speichern |
| `Enter` | Nachricht senden |
| `Umschalt + Enter` | Zeilenumbruch im Chat |

---

## Wenn etwas nicht funktioniert

**„Ollama konnte nicht erreicht werden"**
Der Dienst läuft nicht. Die App bietet „Ollama starten" an; alternativ in einem
Terminal `ollama serve` ausführen.

**„qwen3.5:9b ist nicht installiert"**
Über „Modell herunterladen" in der App oder mit `ollama pull qwen3.5:9b`.

**„Der konfigurierte Vault ist nicht erreichbar"**
Der Ordner wurde verschoben oder ein Netzlaufwerk ist nicht verbunden. In den
Einstellungen den Pfad neu auswählen.

**Die KI legt keine Dateien an, sondern gibt nur Code aus**
Prüfe zuerst, ob der Vault in der Statusleiste als erreichbar angezeigt wird.
Bei einem eindeutigen Auftrag wie „Erstelle eine Notiz …“ kontrolliert die App
selbst, ob eine Datei geschrieben wurde, und korrigiert eine bloße Chatantwort
automatisch. Modelle mit `tools`-Fähigkeit wie `qwen3.5:9b` können zusätzlich
vorhandene Notizen suchen, lesen und den Ablageort intelligent wählen.

**Antworten mit vielen Anhängen dauern lange**
Das ist erwartet: Jede Datei wird wirklich gelesen, bevor geantwortet wird. Der
Fortschritt steht im Chat.

**Die Adresse ist jedes Mal eine andere**
So ist es gewollt: `server.port` steht auf `0`, das Betriebssystem vergibt bei
jedem Start einen freien Port. Ein fester, überall gleicher Port wäre von jeder
Webseite im selben Browser adressierbar. Wer trotzdem einen festen Port
braucht, trägt ihn in `data/config.json` unter `server.port` ein.

**Ein Lesezeichen auf die App funktioniert nicht mehr**
Ebenfalls gewollt. Jede Sitzung hat einen eigenen Schlüssel, den nur das
App-Fenster beim Start erhält. Eine ohne diesen Schlüssel geöffnete Adresse
bekommt keine Daten, sondern eine Erklärung. Die App bitte über ihre
Verknüpfung starten.

**Die Oberfläche sieht nach einem Update seltsam aus**
Die App liefert ihre Dateien ohne Caching aus; ein normales Neuladen genügt.

Details zu jedem Fehler stehen in `data/logs/app.log`.

---

## Fahrplan

- **Phase 1 — Grundgerüst** ✔ Backend, Ollama-Anbindung, Chat, Vault, Editor, Suche
- **Phase 2 — Dateien** ✔ Anhänge, Datei-Watcher und Verschieben per Ziehen
- **Phase 3 — Wissen/RAG** ✔ persistenter Index, lokale Embeddings, hybride
  Suche, Datei- und PDF-Seitenquellen
- **Phase 4 — Bilder** ✔ Bildanalyse, Screenshots, iPhone-Scans, Einsortieren
- **Phase 5 — Vorlagen** ✔ Standard, Vokabeln, IT-Wissen, Projekt, Meeting,
  Lernzettel, eigene Vault-Vorlagen und automatische Auswahl
- **Phase 6 — Komfort** ✔ Dashboard, Dark Mode, Startverknüpfung, ZIP-Backup und
  reproduzierbarer `.exe`-Build
