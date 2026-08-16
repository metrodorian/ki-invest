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
- `--ohne-claude` — die Einordnung durch Claude überspringen

## Was beobachtet wird

**Positionen** — Kurs, Tagesbewegung, geschätzte Schein-Bewegung, Abstand zur
Knock-Out-Barriere, aufgelaufener Volatilitäts-Drag.

**Sieben Marktgruppen** — Chips, Neoclouds, Hyperscaler, Rechenzentrums-Bau,
Strom, China-Gegenseite, Marktbreite und Stress.

**Neun abgeleitete Indikatoren**, die einzelne Kurse nicht zeigen:

| Indikator | Wozu |
|---|---|
| Konzentrations-Spread | Nasdaq 100 gegen gleichgewichteten S&P — verliert der Schwergewichts-Trade? |
| VIX-Terminstruktur | über 1,00 heißt akuter Stress |
| Neocloud-Relativstärke | Frühwarnung, weil schuldenfinanziert |
| Chips gegen Hyperscaler | wo der Markt das Risiko verortet |
| Bau-Relativstärke | die Seite, auf der die Vertiv-Position sitzt |
| Strom-Relativstärke | Engpassfaktor 2026 |
| China-Relativstärke | die eigentliche Gegenprobe der These |
| Hochzins-Kredite | Refinanzierungsdruck bei den Neoclouds |
| Speicherpreise | Kostenseite der Capex-Rendite |

**Barometer 0–100** — verdichtet Relativstärken, Volatilitätsstruktur,
Kreditumfeld und Nachrichtenbilanz. Hoch heißt: Das Umfeld arbeitet für die
Short-These.

**Nachrichten** aus fünf Quellen:

- Yahoo-Finance-Schlagzeilen je Ticker
- acht thematische Google-News-Suchen (Capex-Signale, Stornierungen, Blasen-Debatte,
  China-KI, Exportkontrollen, Zirkelfinanzierung, Strom, GPU-Preise)
- Federal Register — Regierungsvorhaben zu Exportkontrollen und Chips
- SEC EDGAR — 8-K-Pflichtmeldungen von Nvidia, Vertiv, CoreWeave
- Blogs von OpenAI, DeepMind, HuggingFace und DataCenterDynamics

Effizienzdurchbrüche bei Modellen zählen dabei **für** die These, auch wenn sie
positiv klingen — der DeepSeek-Moment begann mit einer Modellveröffentlichung,
nicht mit einer Kurszahl.

## Zusammenfassung und Claude

Ganz oben im Bericht stehen einige Sätze dazu, was die Lage bedeutet und was
heute besonders war. Diese Zusammenfassung wird immer aus den Messwerten erzeugt
und funktioniert ohne Netz und ohne Sprachmodell.

Zusätzlich wird `claude -p` aufgerufen und schreibt eine eigene Einordnung, die
dann darüber steht. Der Aufruf läuft mit `--allowedTools ""`, kann also keine
Werkzeuge benutzen und keine Rückfrage auslösen — er eignet sich für
unbeaufsichtigte Läufe.

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
