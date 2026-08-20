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

## Was beobachtet wird

**Wertverlauf ganz oben** — zwei Linien mit dem Eurowert beider Positionen.
Durchgezogen ab dem Einstieg, gestrichelt davor (rechnerisch, nicht tatsächlich).
Die waagerechte Linie je Farbe ist der Einsatz, daran ist Gewinn und Verlust
direkt ablesbar.

**Positionen** — Kurs, Tagesbewegung, geschätzte Schein-Bewegung, Abstand zur
Knock-Out-Barriere, aufgelaufener Drag und der **erwartete Drag pro Woche** bei
Seitwärtslauf — die vorausschauende Zahl, mit der sich planen lässt.

**Acht Marktgruppen** — Chips, Neoclouds, Hyperscaler, Rechenzentrums-Bau, Strom,
China-Plattformen, China-Chipfertigung, Marktbreite und Stress.

**Zehn abgeleitete Indikatoren**, die einzelne Kurse nicht zeigen:

| Indikator | Wozu |
|---|---|
| Konzentrations-Spread | Nasdaq 100 gegen gleichgewichteten S&P — verliert der Schwergewichts-Trade? |
| VIX-Terminstruktur | über 1,00 heißt akuter Stress |
| Neocloud-Relativstärke | Frühwarnung, weil schuldenfinanziert |
| Chips gegen Hyperscaler | wo der Markt das Risiko verortet |
| Bau-Relativstärke | die Seite, auf der die Vertiv-Position sitzt |
| Strom-Relativstärke | Engpassfaktor 2026 |
| China-Relativstärke | Alibaba und Baidu, aber als ADR von US-Stimmung gefärbt |
| China-Chipfertigung | SMIC, Cambricon, Hua Hong an den Heimatbörsen — die schärfere Gegenprobe |
| Kreditrisiko-Aufschlag | Hochzins gegen erste Bonität, trennt Ausfallrisiko von Zinsbewegung |
| Speicherpreise | Kostenseite der Capex-Rendite |

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

## Pflege

In `config.json` aktuell halten:

- **`barriere`** je Position — die Reset-Barriere wandert täglich mit. Ohne
  Pflege wird der angezeigte Puffer mit der Zeit falsch.
- **`einstiegskurs_basiswert`** und **`einstieg_datum`** — erst damit rechnen die
  Spalten „seit Einstieg" und „Drag".
- **`verlust_warnung_prozent`** und **`gewinn_ziel_prozent`** — solange `null`,
  wird dafür nicht gewarnt.
- **`termine`** — Quartalszahlen und das Zeitlimit.

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
