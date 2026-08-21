# KI-Invest Monitor

Beobachtet die beiden Short-Positionen und das gesamte Umfeld der KI-Capex-These.
Läuft über launchd, meldet Auffälligkeiten per Systemmeldung und öffnet einmal
täglich einen HTML-Bericht im Browser.

Keine externen Pakete nötig — nur `/usr/bin/python3` und optional das
`claude`-Kommandozeilenwerkzeug für die Einordnung.

## Einrichten

```bash
cp /Users/lennartduncker/MEGA/MEGAsync/Projekte/ki-invest/monitor/com.lennart.ki-invest.*.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.lennart.ki-invest.watch.plist
launchctl load ~/Library/LaunchAgents/com.lennart.ki-invest.report.plist
```

Prüfen, ob beide geladen sind:

```bash
launchctl list | grep ki-invest
```

Wieder abschalten:

```bash
launchctl unload ~/Library/LaunchAgents/com.lennart.ki-invest.watch.plist
launchctl unload ~/Library/LaunchAgents/com.lennart.ki-invest.report.plist
```

## Zeiten

| Job | Wann | Was |
|---|---|---|
| `watch` | werktags 9:00, 15:45, 17:30, 19:30, 21:30 | prüft still, meldet nur bei Auffälligkeiten |
| `report` | werktags 22:30 | baut den vollen Bericht und öffnet ihn im Browser |

Der `watch`-Lauf meldet jede Auffälligkeit nur einmal pro Tag, damit dieselbe
Nachricht nicht fünfmal piept. Der Tagesbericht setzt diese Sperre zurück.

## Von Hand starten

```bash
/usr/bin/python3 /Users/lennartduncker/MEGA/MEGAsync/Projekte/ki-invest/monitor/ki_monitor.py --report
```

Schalter:

- `--watch` — nur prüfen und warnen (Voreinstellung)
- `--report` — Bericht bauen und im Browser öffnen
- `--test` — Bericht bauen, aber nicht öffnen
- `--nur-claude` — **nur** die Einordnung neu anfragen und den Bericht damit neu
  bauen. Nutzt die zuletzt gesammelten Daten aus `daten.json`, ruft also weder
  Kurse noch Nachrichten erneut ab. Dauert rund zwei Minuten statt der vollen
  Sammelzeit — praktisch, wenn nur der Text nicht überzeugt.
- `--ohne-claude` — die Einordnung überspringen

## Aufbau

Der Bericht ist zweispaltig. **Links** läuft der Inhalt durch: Barometer,
Wertverlauf, Zusammenfassung, Auffälligkeiten, Positionen, Indikatoren, Gruppen,
Nachrichten, Termine. **Rechts** steht eine feste Spalte mit den Kennzahlen, die
den Zustand des Systems beschreiben statt der Richtung einzelner Werte — sie
bleibt beim Scrollen stehen.

Ganz oben in dieser Spalte der **Kreditrisiko-Aufschlag**: Eine Blase platzt über
die Finanzierung, dort zeigt sie sich zuerst. Darunter VIX-Terminstruktur,
Konzentrations-Spread und die Monatsveränderung je Gruppe.

Unter 1080 Pixel Fensterbreite rutscht die rechte Spalte unter den Inhalt.

## Was beobachtet wird

**Wertverlauf ganz oben** — zwei Linien mit dem Eurowert beider Positionen, zum
**Geldkurs**, also so wie das Depot bewertet. Durchgezogen ab dem Einstieg,
gestrichelt davor (rechnerisch). Die waagerechte Linie je Farbe ist der bezahlte
Briefkurs; der Abstand zur Kurve am Einstieg ist die Handelsspanne. Ein Ring um
den letzten Punkt bedeutet: eingetragener Ist-Kurs, kein gerechneter.

Der Graph richtet sich am Einstieg aus — mindestens acht Tage Vorlauf, darüber
hinaus höchstens so viele wie Haltetage. Damit bestimmt die Zeit seit dem Kauf
das Bild, nicht die Vorgeschichte.

In die Rechnung gehen drei Dinge ein: die Tagesbewegung des Basiswerts mal
Faktor, der Wechselkurs EUR/USD (beide Scheine sind **nicht**
währungsgesichert — ein steigender Euro senkt den Eurowert auch bei
stillstehendem Basiswert) und die Handelsspanne.

**Positionen** — Kurs, Tagesbewegung, geschätzte Schein-Bewegung, Abstand zur
Knock-Out-Barriere, aufgelaufener Drag und der **erwartete Drag pro Woche** bei
Seitwärtslauf — die vorausschauende Zahl, mit der sich planen lässt.

**Acht Marktgruppen** — Chips, Neoclouds, Hyperscaler, Rechenzentrums-Bau, Strom,
China-KI-Modelle, China-Chipfertigung, Marktbreite und Stress.

Die beiden China-Gruppen messen bewusst Verschiedenes: Die Modellseite prüft, ob
chinesische KI durch **Effizienz** aufholt, die Fertigungsseite, ob sie es durch
**eigene Hardware** tut. Beide können unabhängig voneinander recht haben.

**Zehn abgeleitete Indikatoren**, die einzelne Kurse nicht zeigen:

| Indikator | Wozu |
|---|---|
| Konzentrations-Spread | Nasdaq 100 gegen gleichgewichteten S&P — verliert der Schwergewichts-Trade? |
| VIX-Terminstruktur | über 1,00 heißt akuter Stress |
| Neocloud-Relativstärke | Frühwarnung, weil schuldenfinanziert |
| Chips gegen Hyperscaler | wo der Markt das Risiko verortet |
| Bau-Relativstärke | die Seite, auf der die Vertiv-Position sitzt |
| Strom-Relativstärke | Engpassfaktor 2026 |
| China-KI-Relativstärke | Alibaba, Tencent, SenseTime, iFlytek, Kingsoft Cloud, Baidu — die Modellseite, der Kern der China-These |
| China-Chipfertigung | SMIC, Cambricon, Hua Hong — die Hardwareseite. Misst etwas anderes und darf der Modellseite widersprechen |
| Kreditrisiko-Aufschlag | Wie weit Hochzins hinter erster Bonität zurückbleibt. **Steigt er, wird Refinanzierung teuer** — das stützt die These. Als Aufschlag gerechnet (`LQD − HYG`), damit Name und Richtung zusammenpassen |
| Speicherpreise | Kostenseite der Capex-Rendite |
| Preis je Million Token | Der **direkte** Effizienzmesswert. Fallende Preise entwerten Rechenleistung und stützen die These — alles andere misst Effizienz nur über Aktienkurse |

### Feste Alarmschwellen

Claude entscheidet nur zur vollen Stunde über eine Eilmeldung. Damit die
Zwischenläufe nicht stumm bleiben, prüft das Skript zusätzlich harte Schwellen —
konfigurierbar unter `alarmschwellen`:

**Für die These** (Gewinnmitnahme erwägen): Schein gewinnt über 25% am Tag,
Basiswert fällt über 8%, Risikoaufschlag weitet sich über 50 Bp im Monat oder
25 Bp in der Woche, VIX-Terminstruktur über 1,00, Neocloud-Relativstärke unter
−15 Punkte.

**Gegen die These** (Position gefährdet): Schein verliert über 20% am Tag,
Abstand zur Stop-Marke unter 12%, Barriere-Puffer unter 25%, Basiswert steigt
über 8%, Z-Wert über 3 gegen die Position.

**Strukturell:** ein Termin heute oder morgen, Zeitlimit in drei Tagen.

Jede Schwelle meldet höchstens einmal pro Tag. Die Stummschaltung wird
respektiert. Claudes Ermessen bleibt zusätzlich bestehen — die Schwellen sind
das Netz darunter, nicht der Ersatz.

### Token-Preise

Gepflegt unter `tokenpreise` in der Konfiguration, mit Verlauf in
`tokenpreise.json`. Bei jeder Preisänderung wird der alte Stand fortgeschrieben,
sodass eine Zeitreihe entsteht. Telegram-Befehl: **tokenpreise**.

**Barometer 0–100** — verdichtet Relativstärken, Volatilitätsstruktur,
Kreditumfeld und Nachrichtenbilanz. Hoch heißt: Das Umfeld arbeitet für die
Short-These.

**Nachrichten** aus fünf Quellen:

- Yahoo-Finance-Schlagzeilen je Ticker
- dreizehn thematische Google-News-Suchen (Capex-Signale, Stornierungen,
  Blasen-Debatte, China-KI, Exportkontrollen, Zirkelfinanzierung, Strom,
  GPU-Mietpreise, Speicher-Vertragspreise, Netzanschluss-Warteschlange,
  Schulden der KI-Bauherren, Auftragseingang der Ausrüster)
- Federal Register — Regierungsvorhaben zu Exportkontrollen und Chips
- SEC EDGAR — 8-K-Pflichtmeldungen von Nvidia, Vertiv, CoreWeave
- Blogs von OpenAI, DeepMind, HuggingFace, DataCenterDynamics, SemiAnalysis
  (veröffentlicht den GPU-Mietpreisindex), Utility Dive (Netzanschlüsse und
  Versorger) und The Register

Meldungen älter als **14 Tage** werden aussortiert (Fachbeiträge: 42 Tage),
damit keine Altmeldungen als aktuelles Signal durchgehen. Die Stichwortlisten
sind bewusst auf Genauigkeit statt Vollständigkeit getrimmt: lieber wenige
richtige Treffer als viele falsche im Alarmblock. Was der Filter übersieht,
fängt Claude ab — seine Korrektur steht als Hinweis **über** den
Auffälligkeiten.

Effizienzdurchbrüche bei Modellen zählen dabei **für** die These, auch wenn sie
positiv klingen — der DeepSeek-Moment begann mit einer Modellveröffentlichung,
nicht mit einer Kurszahl.

## Zusammenfassung und Claude

Ganz oben im Bericht stehen einige Sätze dazu, was die Lage bedeutet und was
heute besonders war. Diese Zusammenfassung wird immer aus den Messwerten erzeugt
und funktioniert ohne Netz und ohne Sprachmodell.

Zusätzlich wird `claude -p` aufgerufen und schreibt eine eigene Einordnung, die
dann darüber steht.

### Arbeitsteilung

Das **Skript** deckt die feste Grundversorgung ab: immer dieselben Ticker, Feeds
und Suchbegriffe, damit Verläufe über die Wochen vergleichbar bleiben. **Claude**
ergänzt anlassbezogen — es darf selbst im Netz suchen, wenn eine Zahl
erklärungsbedürftig ist oder eine Vermutung belegt werden soll, und es darf
fehlende Daten anfordern.

Beides bleibt im Bericht getrennt: gemessene Werte im grauen Block, Claudes
Recherche in einem eigenen Abschnitt mit gestricheltem Rahmen und dem Hinweis,
dass die Befunde ungeprüft sind. Die Datenwünsche landen unter „Was Claude
fehlt" und lassen sich direkt in die `config.json` übernehmen.

Erlaubt sind ausschließlich `WebSearch` und `WebFetch` — Dateizugriff und Shell
bleiben gesperrt. Damit kann keine Rückfrage nach Berechtigungen auftauchen, der
Lauf bleibt unbeaufsichtigt. Über `"werkzeuge"` im Abschnitt `claude` der
`config.json` lässt sich das ändern, `""` schaltet die Suche ganz ab.

**Vor dem ersten Lauf einmal anmelden:**

```bash
claude -p "Antworte nur mit JSON: {\"status\":\"bereit\"}" --allowedTools ""
```

Kommt hier `Failed to authenticate` statt JSON, einmal `claude` im Terminal
starten und anmelden. Bis dahin läuft der Bericht ohne die Einordnung weiter und
vermerkt das oben sichtbar.

Abschalten lässt sich der Aufruf über `"claude": {"aktiv": false}` in der
`config.json`.

## Betrieb auf dem NAS

Der Monitor läuft auf dem Raspberry Pi (OMV) unter `~/ki-invest`, gesteuert
über cron. Der Mac ist abgeschaltet.

| Wann | Was |
|---|---|
| alle 10 Minuten, rund um die Uhr | Prüflauf ohne Claude; feste Alarmschwellen greifen sofort |
| alle 3 Stunden (0, 3, 6 … 21 Uhr) | Prüflauf mit Claude-Einordnung |
| werktags 22:30 | Tagesbericht mit Mail an l.duncker@posteo.de |
| beim Systemstart | Webserver auf Port 8088, Telegram-Bot |

Rund um die Uhr, weil die **Hongkonger Sitzung von 03:30 bis 10:00** unserer
Zeit läuft — dort handeln Alibaba, Tencent und SenseTime, also der Kern der
China-These. Ein Plan von 7 bis 23 Uhr hätte sie komplett übersehen. Geweckt
wird dabei niemand: Für Lampe und Telegram gilt die Nachtruhe von 22 bis 7 Uhr
mit einem Budget von 300 Sekunden, sodass nachts nur durchkommt, was ein
Wecken wert ist.

**Bericht im Browser:** http://192.168.178.20:8088/ — mit Archiv, Blättern über
Pfeiltasten oder Knöpfe, dem roten Balken zum Abstellen eines Alarms und einer
Steuerung in der rechten Spalte:

| Knopf | Wirkung |
|---|---|
| Bericht erneuern | voller Lauf samt Einordnung, im Hintergrund |
| Weitere Aktionen | öffnet ein Fenster mit dem Rest |

Im Fenster: Alarme stummschalten oder Probealarm auslösen, Reset-Barrieren
nachtragen, Positionen als geschlossen markieren, einen Vermerk für den Bericht
setzen, und den Bericht per Telegram schicken.

In der Mailfassung fehlen alle Knöpfe — dort wären sie wirkungslos.

Dieselben Funktionen gibt es über Telegram, siehe **hilfe** im Chat.

### Zeitplan der Läufe

Die Datengrundlage wird zu :10, :20, :30, :40 und :50 aufgefrischt, ohne Claude
zu fragen — die zuletzt gesicherte Einordnung bleibt im Bericht stehen, mit
sichtbarem Zeitstempel. Zur vollen Stunde läuft sie zusätzlich mit Claude und
erzeugt einen Archiveintrag. Zwischen 23 und 7 Uhr ruht alles.

### Eilmeldung

Claude entscheidet bei jedem Lauf, ob ein Ereignis nicht bis zum Abendbericht
warten kann. Die Auslöser sind im Prompt genau umrissen: Position in Gefahr,
These gebrochen, These schlagartig bestätigt, Termin mit Folgen, sowie Ermessen
für alles andere. Ausdrücklich **keine** Auslöser sind gewöhnliche Schwankung,
Altmeldungen und Barometerbewegungen unter 15 Punkten.

Wird sie ausgelöst, passiert alles zugleich:

- **Telegram** sofort mit Zahlen und Handlungsmöglichkeiten, danach der Bericht
  als Dokument
- **Telegram alle 5 Sekunden** als Wiedervorlage, bis abgestellt
- **Hue-Lampe** blinkt im selben Takt
- **Mail** mit `X-Priority: 1` und roter Karte

Nachts zwischen 22 und 7 Uhr gilt ein Kontingent von fünf Minuten. Danach
schweigen Lampe und Telefon bis zum Morgen — der Alarm bleibt bestehen und
nimmt um 7 Uhr die Arbeit wieder auf.

**Abstellen** über den roten Balken auf der Berichtsseite. Lampe und
Erinnerungen laufen im selben Vorgang, ein Knopf beendet beides und setzt die
Lampe auf ihren vorherigen Zustand zurück.

### Zugangsdaten

Nichts davon steht im Repo oder in der Konfiguration:

| Datei auf dem Pi | Inhalt |
|---|---|
| `telegram.token` | Bot-Token |
| `telegram.chat` | Chat-Kennung |
| `hue.key` | Schlüssel der Hue-Bridge |

Alle mit Rechten 600. `config.pi.json` im Repo ist eine bereinigte Vorlage.

### Zwei Schichten

Die Konfiguration liegt in zwei Dateien, damit auf allen Rechnern derselbe Code
und dieselbe geteilte Konfiguration laufen kann:

| Datei | Inhalt | Im Repo |
|---|---|---|
| `config.json` | Positionen, Gruppen, Stichworte, Schwellen, Modellpreise | ja, ueberall identisch |
| `config.lokal.json` | Mail, Telegram, Hue, Pfade, **Rolle**, Stummschaltung | nein |

Die lokale Auflage wird ueber `config.json` gelegt. `config.json` ist damit
gefahrlos zwischen den Rechnern kopierbar - genau das ging vorher schief: Ein
`scp` der Mac-Fassung hatte auf dem Pi die Bloecke `mail`, `telegram` und `hue`
geloescht und die Meldekette lautlos stillgelegt.

`config.lokal.beispiel.json` zeigt den Aufbau. Geschrieben wird ebenfalls
getrennt: Was in `LOKALE_SCHLUESSEL` steht, landet in der lokalen Auflage, alles
andere in der geteilten Datei.

### Rollen

In `config.lokal.json` steht, wofuer der Rechner da ist:

- `"rolle": "betrieb"` - ueberwacht, erzeugt Berichte, schickt Alarme (der Pi)
- `"rolle": "arbeitsplatz"` - entwickelt nur, erzeugt **nie** einen Bericht (der Mac)

Auf einem Arbeitsplatz weigert sich `ki_monitor.py` zu laufen, und `betrieb.sh`
sperrt `lauf`, `bericht` und `probealarm`. Zwei Quellen wuerden zwei Archive und
zwei Zaehlstaende erzeugen. Vom Arbeitsplatz aus fuehrt `--pi` zum Ziel;
`--erzwingen` uebergeht die Sperre bewusst.

Mail geht über den lokalen Postfix, deshalb sind dort keine Zugangsdaten nötig.

## Betrieb

`betrieb.sh` liegt lokal, auf dem Pi und im Repo. Dasselbe Programm, der
Unterschied steckt nur im Ziel-Schalter:

```
./betrieb.sh status            wirkt dort, wo es aufgerufen wird
./betrieb.sh status --pi       schickt sich selbst per ssh auf den Pi
```

| Befehl | Wirkung |
|---|---|
| `status` | Prozesse, Cron-Plan, letzte Laeufe |
| `pruefen` | Konfiguration auf Vollstaendigkeit pruefen |
| `web-neu`, `bot-neu`, `alles-neu` | Dienste sauber neu starten |
| `logs [n]` | letzte Zeilen aus cron.log, monitor.log, bot.log |
| `lauf [--mit-claude]` | Monitorlauf anstossen |
| `bericht` | Tagesbericht bauen und verschicken |
| `probealarm`, `probealarm-aus` | Meldekette testen und wieder abstellen |

`pruefen` meldet auf dem Mac erwartungsgemaess fehlende Bloecke `mail`,
`telegram` und `hue` - die gehoeren nur auf den Pi. Auf dem Pi muss es
`Konfiguration vollstaendig` sagen; tut es das nicht, schweigt die Meldekette.

Ziel und Zugang lassen sich ueber `KI_PI_ZIEL`, `KI_PI_SCHLUESSEL`,
`KI_PI_ORDNER` und `KI_PORT` ueberschreiben.

## Pflege

In `config.json` aktuell halten:

- **`barriere`** je Position — die Reset-Barriere wandert täglich mit. Ohne
  Pflege wird der angezeigte Puffer mit der Zeit falsch.
- **`einstiegskurs_basiswert`** und **`einstieg_datum`** — erst damit rechnen die
  Spalten „seit Einstieg" und „Drag".
- **`verlust_warnung_prozent`** und **`gewinn_ziel_prozent`** — solange `null`,
  wird dafür nicht gewarnt.
- **`termine`** — Quartalszahlen und das Zeitlimit.
- **`isin`** je Position — nötig für den automatischen Kursabruf.

Scheinkurs und Handelsspanne werden bei jedem Lauf selbst geholt und müssen
nicht mehr gepflegt werden. Quelle ist wallstreet-online, weil dort die
Quotierung des **Emittenten** steht — also genau der Kurs, den ING im
Direkthandel stellt. Gegen onvista geprüft: identisch auf den Cent.

Die naheliegenderen Quellen scheiden aus: Morgan Stanley liefert nur einen
WebSocket-Strom, onvista antwortet Skripten mit einer Weiterleitungsschleife,
die Börse Frankfurt und finanzen.net mit 403. Schlägt der Abruf fehl, greifen
`kurs_aktuell` und `spread_prozent` aus der Konfiguration, falls dort gesetzt.

## Dateien

| Datei | Inhalt |
|---|---|
| `ki_monitor.py` | das Skript |
| `config.json` | Positionen, Schwellen, Ticker, Suchbegriffe, Termine |
| `state.json` | letzter Lauf, gemeldete Alarme, letztes Barometer |
| `bericht.html` | der zuletzt erzeugte Bericht |
| `monitor.log` | Verlaufsprotokoll |
| `launchd.out.log` / `launchd.err.log` | Ausgaben der launchd-Jobs |

## Grenzen

Kursdaten kommen von öffentlichen Yahoo-Endpunkten und können verzögert sein —
zur Beobachtung geeignet, nicht zur Orderausführung. Die Schein-Werte sind
Näherungen aus der Basiswert-Bewegung mal Faktor, ohne Produktkosten und ohne
Pfadeffekt; der echte Kurs steht im ING-Depot. Die Stichwort-Einordnung von
Nachrichten ist eine grobe Vorsortierung, keine Bewertung.
