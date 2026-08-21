#!/bin/bash
#
# Woechentlicher Verbesserungslauf.
#
# Laesst claude ohne Rueckfrage die gesammelten Vorschlaege durchgehen und die
# guten umsetzen. Das Ergebnis wird geprueft und committet - aber WEDER GEPUSHT
# NOCH UEBERNOMMEN. Was eine unbeaufsichtigte Sitzung am Code aendert, soll ein
# Mensch gesehen haben, bevor es oeffentlich wird oder den laufenden Monitor
# steuert. Die Meldung darueber kommt per Telegram.
#
# Angenommen wird spaeter von Hand:  ./betrieb.sh verbesserung-annehmen
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
git pull --quiet --ff-only || abbrechen "git pull fehlgeschlagen"
VOR=$(git rev-parse HEAD)
notiz "Stand vor dem Lauf: $VOR"

# Die gesammelten Vorschlaege und die Konfiguration kommen aus dem Betrieb -
# im Repo stehen sie nicht, weil sie Laufzeitdaten sind.
cp "$LIVE/verbesserungen.json" "$ARBEIT/monitor/" 2>/dev/null || true
cp "$LIVE/daten.json" "$ARBEIT/monitor/" 2>/dev/null || true
cp "$LIVE/claude.json" "$ARBEIT/monitor/" 2>/dev/null || true

OFFEN=$("$PYTHON" - <<'PY'
import json, os
try:
    v = json.load(open("monitor/verbesserungen.json"))
except Exception:
    v = []
print(sum(1 for e in v if isinstance(e, dict) and not e.get("erledigt")))
PY
)
notiz "Offene Vorschlaege: $OFFEN"

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

# --------------------------------------------------------------- Sichern
# Committet wird, gepusht NICHT. Was eine unbeaufsichtigte Sitzung an Code
# aendert, soll ein Mensch gesehen haben, bevor es oeffentlich wird oder den
# laufenden Monitor steuert. Der Commit liegt in der Arbeitskopie bereit.

cd "$ARBEIT" || abbrechen "Arbeitskopie verschwunden"
if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit --quiet -m "Woechentlicher Verbesserungslauf" \
        -m "Automatisch erzeugt. Siehe VERBESSERUNG.md." || true
fi
NACH=$(git rev-parse HEAD)
if [ "$VOR" = "$NACH" ]; then
    notiz "Nichts committet."
    melden "🛠 <b>Verbesserungslauf</b>%0AGeprueft, nichts geaendert."
    exit 0
fi

notiz "Committet: $NACH (nicht gepusht, nicht uebernommen)"

# Vorschlaege als behandelt zurueckschreiben, damit sie nicht erneut auflaufen.
cp "$ARBEIT/monitor/verbesserungen.json" "$LIVE/" 2>/dev/null || true

BERICHT=$(sed -n '1,80p' "$ARBEIT/monitor/VERBESSERUNG.md" 2>/dev/null \
          || sed -n '1,80p' "$ARBEIT/VERBESSERUNG.md" 2>/dev/null)
ZUSAMMEN=$(echo "$BERICHT" | head -c 2200)

melden "🛠 <b>Verbesserungslauf liegt zur Durchsicht</b>%0AStand <code>${NACH:0:7}</code> in der Arbeitskopie committet, <b>nicht gepusht</b> und noch nicht uebernommen.%0A%0A$ZUSAMMEN%0A%0AAnnehmen: <code>./betrieb.sh verbesserung-annehmen</code>"

notiz "Fertig. Wartet auf Durchsicht."
