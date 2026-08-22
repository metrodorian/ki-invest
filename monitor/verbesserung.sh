#!/bin/bash
#
# Woechentlicher Verbesserungslauf.
#
# Laesst claude ohne Rueckfrage die gesammelten Vorschlaege durchgehen und die
# guten umsetzen. Das Ergebnis geht auf den Zweig "test" - NIE auf main.
#
# Der Weg in den Betrieb fuehrt ueber einen Menschen:
#   1. Dieser Lauf pusht nach "test" und meldet per Telegram, was drinsteht.
#   2. Ein Mensch sieht sich den Vergleich auf GitHub an und fuehrt ihn zusammen.
#   3. Der Betrieb holt sich main:  ./betrieb.sh aktualisieren
#
# main ist auf GitHub geschuetzt, dieser Lauf kann es also gar nicht anfassen.
#
# Der wichtigste Gedanke: claude arbeitet NICHT im laufenden Verzeichnis,
# sondern in einem Git-Klon daneben. Der Monitor laeuft alle zehn Minuten - ein
# halb bearbeitetes ki_monitor.py wuerde ihn mitten in der Arbeit zerreissen.
#
# Aufruf:  ./verbesserung.sh            regulaerer Lauf
#          ./verbesserung.sh --trocken  alles bis zur Pruefung, ohne Commit

set -u

LIVE="${KI_LIVE:-/home/Nutzer/ki-invest}"
ARBEIT="${KI_ARBEIT:-/home/Nutzer/ki-invest-arbeit}"
REPO="${KI_REPO:-git@github.com:metrodorian/ki-invest.git}"
ZWEIG="${KI_ZWEIG:-test}"
PYTHON="${KI_PYTHON:-/usr/bin/python3}"
export PATH="/home/Nutzer/.local/node/bin:$PATH"

TROCKEN=0
[ "${1:-}" = "--trocken" ] && TROCKEN=1

PROTOKOLL="$LIVE/verbesserung.log"
notiz() { echo "$(date '+%Y-%m-%d %H:%M:%S')  $*" | tee -a "$PROTOKOLL"; }

# Meldung an Telegram - ueber den Monitor, damit Zugangsdaten an einer Stelle
# bleiben. Schlaegt das fehl, laeuft der Rest trotzdem weiter.
melden() {
    "$PYTHON" - "$1" <<'PY' 2>/dev/null || true
import sys, os
os.chdir(os.environ.get("KI_LIVE", "/home/Nutzer/ki-invest"))
sys.path.insert(0, ".")
import ki_monitor as km
konfig = km.konfig_laden() or {}
km.telegram_senden(konfig, sys.argv[1], still=True)
PY
}

abbrechen() {
    notiz "ABBRUCH: $1"
    melden "🛠 <b>Verbesserungslauf abgebrochen</b>%0A$1"
    exit 1
}

# ------------------------------------------------------------- Arbeitskopie

if [ ! -d "$ARBEIT/.git" ]; then
    notiz "Lege Arbeitskopie an: $ARBEIT"
    git clone --quiet "$REPO" "$ARBEIT" || abbrechen "Klonen fehlgeschlagen"
fi

cd "$ARBEIT" || abbrechen "Arbeitskopie nicht erreichbar"

git reset --quiet --hard HEAD
git clean --quiet -fd
git fetch --quiet origin || abbrechen "git fetch fehlgeschlagen"

# Immer frisch von main abzweigen. Ein alter Testzweig wuerde die Arbeit von
# Wochen aufeinanderstapeln, die nie zusammengefuehrt wurde.
git checkout --quiet -B "$ZWEIG" origin/main || abbrechen "Zweig $ZWEIG nicht anlegbar"
VOR=$(git rev-parse HEAD)
notiz "Zweig $ZWEIG von main abgezweigt, Stand $VOR"

# Die Konfiguration und die Daten kommen aus dem Betrieb - im Repo stehen sie
# nicht, weil sie Laufzeitdaten sind.
cp "$LIVE/daten.json" "$ARBEIT/monitor/" 2>/dev/null || true
cp "$LIVE/claude.json" "$ARBEIT/monitor/" 2>/dev/null || true

# Vorgelegt wird, was seit dem letzten Verbesserungslauf dazugekommen ist.
# Alles Aeltere gilt als abgearbeitet - ob claude es umgesetzt oder begruendet
# verworfen hat, spielt keine Rolle. Das ist robuster, als sich darauf zu
# verlassen, dass jeder Eintrag sauber als erledigt markiert wurde: Bricht ein
# Lauf ab, gingen die Vermerke verloren und dieselben Vorschlaege liefen ewig
# wieder auf. Was weiterhin wichtig ist, schlaegt claude ohnehin erneut vor.
STAND_DATEI="$LIVE/verbesserung.stand"
SEIT=$(cat "$STAND_DATEI" 2>/dev/null || true)
notiz "Beruecksichtige Vorschlaege seit: ${SEIT:-Anfang}"

OFFEN=$(SEIT="$SEIT" KI_LIVE="$LIVE" "$PYTHON" "$LIVE/vorschlaege_auswaehlen.py" \
        "$ARBEIT/monitor/verbesserungen.json")
notiz "Neue Vorschlaege seit dem letzten Lauf: ${OFFEN:-0}"

if [ "${OFFEN:-0}" -lt 1 ]; then
    notiz "Nichts zu tun."
    melden "🛠 <b>Verbesserungslauf</b>%0AKeine offenen Vorschlaege, nichts geaendert."
    exit 0
fi

# ------------------------------------------------------------------- claude

cd "$ARBEIT/monitor" || abbrechen "monitor-Ordner fehlt"

notiz "Starte claude ohne Rueckfrage ..."
claude -p "$(cat verbesserung_prompt.md)" \
    --dangerously-skip-permissions \
    --model "${KI_MODELL:-claude-opus-5}" \
    >> "$PROTOKOLL" 2>&1
ERGEBNIS=$?
notiz "claude beendet (Rueckgabewert $ERGEBNIS)"

cd "$ARBEIT" || abbrechen "Arbeitskopie verschwunden"

if git diff --quiet && git diff --cached --quiet && \
   [ -z "$(git status --porcelain)" ]; then
    notiz "Keine Aenderung vorgenommen."
    melden "🛠 <b>Verbesserungslauf</b>%0AClaude hat die Vorschlaege geprueft und nichts geaendert."
    exit 0
fi

# ------------------------------------------------------------------ Pruefung
# Alles muss durchlaufen, sonst wird nichts uebernommen.

notiz "Pruefe die Aenderungen ..."
cd "$ARBEIT/monitor" || abbrechen "monitor-Ordner fehlt"

for datei in ki_monitor.py webserver.py telegram_bot.py hue_blink.py probealarm.py; do
    "$PYTHON" -c "import ast,io,sys; ast.parse(io.open('$datei',encoding='utf-8').read())" \
        || abbrechen "$datei ist syntaktisch kaputt"
done
notiz "  Syntax in Ordnung"

"$PYTHON" -c "
import json,sys
c=json.load(open('config.json'))
for schluessel in ('positionen','gruppen','alarmschwellen','kennzahlen','tokenpreise'):
    if schluessel not in c: sys.exit('config.json: %s fehlt' % schluessel)
if len(c['positionen']) < 2: sys.exit('config.json: Positionen fehlen')
for p in c['positionen']:
    for f in ('wkn','stueck','stop_schein','barriere','einstiegskurs_schein'):
        if not p.get(f): sys.exit('Position %s: %s fehlt' % (p.get('wkn','?'), f))
print('  Konfiguration und Positionen unversehrt')
" || abbrechen "Konfiguration beschaedigt"

# Testlauf mit einer eigenen lokalen Auflage, damit weder Mail noch Telegram
# noch die Lampe ausgeloest werden.
cat > config.lokal.json <<'EOF'
{"rolle": "betrieb", "mail": {"aktiv": false}, "telegram": {"aktiv": false},
 "hue": {"aktiv": false}, "bericht_kopie": ""}
EOF

rm -f bericht.html
timeout 900 "$PYTHON" ki_monitor.py --web --ohne-claude >> "$PROTOKOLL" 2>&1 \
    || abbrechen "Testlauf fehlgeschlagen"
[ -s bericht.html ] || abbrechen "Testlauf hat keinen Bericht geschrieben"

"$PYTHON" -c "
import io,sys
h=io.open('bericht.html',encoding='utf-8').read()
fehlt=[a for a in ('Positionen','Abgeleitete Indikatoren','Marktumfeld nach Gruppen')
       if a not in h]
if fehlt: sys.exit('Bericht unvollstaendig: ' + ', '.join(fehlt))
print('  Testlauf erzeugt einen vollstaendigen Bericht (%.0f kB)' % (len(h)/1024))
" || abbrechen "Bericht unvollstaendig"

# Nur die Spuren des Testlaufs wegraeumen. Ein "git checkout -- monitor/" waere
# hier fatal: Es wuerde alles verwerfen, was claude noch nicht committet hat.
rm -f config.lokal.json bericht.html daten.json claude.json state.json

if [ "$TROCKEN" = "1" ]; then
    notiz "Trockenlauf: nicht gepusht, nicht uebernommen."
    cd "$ARBEIT" && git status --short | tee -a "$PROTOKOLL"
    exit 0
fi

# ------------------------------------------------------- Sichern und pushen
# Committet und auf den Testzweig gepusht. main bleibt unberuehrt - was eine
# unbeaufsichtigte Sitzung schreibt, geht erst nach menschlicher Durchsicht in
# den Betrieb.

cd "$ARBEIT" || abbrechen "Arbeitskopie verschwunden"

# Den Bericht datiert ablegen, bevor der naechste Lauf ihn ueberschreibt.
# Ohne das gaebe es immer nur den letzten - und damit keine Moeglichkeit
# nachzusehen, was vor drei Wochen entschieden wurde und warum.
for QUELLE in "$ARBEIT/monitor/VERBESSERUNG.md" "$ARBEIT/VERBESSERUNG.md"; do
    if [ -f "$QUELLE" ]; then
        mkdir -p "$ARBEIT/monitor/verbesserungen"
        cp "$QUELLE" "$ARBEIT/monitor/verbesserungen/VERBESSERUNG-$(date +%Y-%m-%d).md"
        break
    fi
done

if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit --quiet -m "Woechentlicher Verbesserungslauf (Rest)" \
        -m "Was claude nicht selbst committet hat. Siehe VERBESSERUNG.md." || true
fi
NACH=$(git rev-parse HEAD)
if [ "$VOR" = "$NACH" ]; then
    notiz "Nichts committet."
    melden "🛠 <b>Verbesserungslauf</b>%0AGeprueft, nichts geaendert."
    exit 0
fi

git push --quiet --force-with-lease origin "$ZWEIG" \
    || abbrechen "Push auf $ZWEIG fehlgeschlagen"
notiz "Auf $ZWEIG gepusht: $NACH"

# Stand fortschreiben: Alles bis hierher gilt ab jetzt als abgearbeitet.
date -Iseconds > "$STAND_DATEI"
notiz "Stand fortgeschrieben auf $(cat "$STAND_DATEI")"

BERICHT=$(cat "$ARBEIT/monitor/VERBESSERUNG.md" 2>/dev/null \
          || cat "$ARBEIT/VERBESSERUNG.md" 2>/dev/null)
VERGLEICH="https://github.com/metrodorian/ki-invest/compare/main...$ZWEIG"

melden "🛠 <b>Verbesserungslauf auf Zweig <code>$ZWEIG</code></b>%0A$(cd "$ARBEIT" && git log --format=%s -1)%0A%0A$(echo "$BERICHT" | head -c 1800)%0A%0A<a href=\"$VERGLEICH\">Vergleich auf GitHub ansehen</a>%0ADanach im Betrieb: <code>./betrieb.sh aktualisieren</code>"

notiz "Fertig. Wartet auf Durchsicht: $VERGLEICH"
