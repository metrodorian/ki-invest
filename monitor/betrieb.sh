#!/bin/bash
#
# Betriebswerkzeug fuer den KI-Monitor.
#
# Dasselbe Programm liegt lokal, auf dem Pi und im Repo. Der Unterschied steckt
# nur im Ziel-Schalter:
#
#   ./betrieb.sh status            wirkt dort, wo es aufgerufen wird
#   ./betrieb.sh status --pi       schickt sich selbst per ssh auf den Pi
#
# Damit entfaellt das Herumkopieren von Wegwerfskripten nach /tmp.
#
# Befehle:
#   status                Prozesse, Cron-Plan, letzte Logzeilen
#   web-neu               Webserver sauber neu starten
#   bot-neu               Telegram-Bot sauber neu starten
#   alles-neu             beide Dienste neu starten
#   logs [anzahl]         letzte Zeilen aus cron.log und monitor.log
#   lauf [--mit-claude]   einen Monitorlauf anstossen (nur auf Zuruf)
#   bericht               Tagesbericht bauen und verschicken
#   probealarm            Meldekette testen (Lampe blinkt!)
#   probealarm-aus        laufenden Alarm abstellen
#   pruefen               Konfiguration auf Vollstaendigkeit pruefen
#
# Rollen: In config.lokal.json steht, wofuer der Rechner da ist.
#   rolle = "betrieb"       ueberwacht, erzeugt Berichte, schickt Alarme (der Pi)
#   rolle = "arbeitsplatz"  entwickelt nur, erzeugt nie einen Bericht (der Mac)
# Die Befehle lauf, bericht und probealarm gibt es deshalb nur im Betrieb. Vom
# Arbeitsplatz aus fuehren sie mit --pi zum Ziel.
#
# Konfiguration in zwei Schichten:
#   config.json        auf jedem Rechner identisch, im Repo, gefahrlos kopierbar
#   config.lokal.json  Mail, Telegram, Hue, Pfade, Rolle, Stummschaltung -
#                      nicht im Repo, wird ueber config.json gelegt

set -u

PI_ZIEL="${KI_PI_ZIEL:-Nutzer@192.168.178.20}"
PI_SCHLUESSEL="${KI_PI_SCHLUESSEL:-$HOME/.ssh/pi_mailsync}"
PI_ORDNER="${KI_PI_ORDNER:-/home/Nutzer/ki-invest}"
PORT="${KI_PORT:-8088}"

HIER="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(command -v python3 || echo /usr/bin/python3)"

# ---------------------------------------------------------------- Ziel klaeren

BEFEHL="${1:-hilfe}"
shift || true

AUF_PI=0
ARGUMENTE=()
for a in "$@"; do
    case "$a" in
        --pi)    AUF_PI=1 ;;
        --lokal) AUF_PI=0 ;;
        *)       ARGUMENTE+=("$a") ;;
    esac
done

if [ "$AUF_PI" = "1" ]; then
    # Sich selbst auf dem Pi aufrufen - dort dann ausdruecklich lokal.
    exec ssh -i "$PI_SCHLUESSEL" "$PI_ZIEL" \
        "cd $PI_ORDNER && ./betrieb.sh $BEFEHL ${ARGUMENTE[*]:-} --lokal"
fi

cd "$HIER" || exit 1

# Rolle dieses Rechners: "betrieb" ueberwacht und erzeugt Berichte,
# "arbeitsplatz" tut das nie. Steht in config.lokal.json.
ROLLE=$("$PYTHON" - <<'PYEND' 2>/dev/null
import json
try:
    print((json.load(open("config.lokal.json")) or {}).get("rolle") or "unbekannt")
except Exception:
    print("unbekannt")
PYEND
)

# Befehle, die einen Bericht erzeugen oder die Meldekette ausloesen, gibt es nur
# im Betrieb. Auf dem Arbeitsplatz entstuenden sonst ein zweites Archiv und ein
# zweiter Zaehlstand - und niemand wuesste, welcher gilt.
nur_im_betrieb() {
    [ "$ROLLE" = "betrieb" ] && return 0
    echo "Dieser Rechner ist '$ROLLE', nicht 'betrieb'."
    echo "'$1' erzeugt einen Bericht oder loest Alarm aus - das geschieht nur auf dem Pi:"
    echo "    ./betrieb.sh $1 --pi"
    return 1
}

# ------------------------------------------------------------------ Werkzeuge

# Beendet alle Prozesse eines Skripts. Das Suchmuster steht in Klammern, damit
# der eigene Aufruf nicht mitgezaehlt und versehentlich beendet wird.
beenden() {
    local muster="$1" pids p
    pids=$(ps -eo pid,args | awk -v m="[${muster:0:1}]${muster:1}" '$0 ~ m {print $1}')
    [ -z "$pids" ] && return 0
    for p in $pids; do kill "$p" 2>/dev/null; done
    sleep 2
    for p in $pids; do kill -9 "$p" 2>/dev/null; done
    sleep 1
}

zaehlen() {
    ps -eo args | awk -v m="[${1:0:1}]${1:1}" '$0 ~ m' | wc -l | tr -d ' '
}

starten_hintergrund() {
    setsid nohup "$@" >> "$2.log" 2>&1 < /dev/null &
}

# ------------------------------------------------------------------- Befehle

case "$BEFEHL" in

status)
    echo "Ort:            $HIER"
    echo "Webserver:      $(zaehlen 'webserver.py') Prozess(e)"
    echo "Telegram-Bot:   $(zaehlen 'telegram_bot.py') Prozess(e)"
    if command -v ss > /dev/null; then
        echo "Port $PORT:      $(ss -tln 2>/dev/null | grep -c ":$PORT ") Lauscher"
    fi
    if [ -f blink.laeuft ]; then echo "Alarm:          BLINKT GERADE"; fi
    echo
    echo "--- Cron ---"
    crontab -l 2>/dev/null | grep -v '^#' | grep . || echo "(kein Cron-Plan)"
    echo
    echo "--- letzte Laeufe ---"
    tail -5 cron.log 2>/dev/null || echo "(keine cron.log)"
    ;;

web-neu)
    beenden 'webserver.py'
    setsid nohup "$PYTHON" webserver.py >> web.log 2>&1 < /dev/null &
    sleep 3
    echo "Webserver: $(zaehlen 'webserver.py') Prozess(e), Port $PORT: $(ss -tln 2>/dev/null | grep -c ":$PORT ")"
    ;;

bot-neu)
    beenden 'telegram_bot.py'
    setsid nohup "$PYTHON" telegram_bot.py >> bot.log 2>&1 < /dev/null &
    sleep 4
    echo "Bot: $(zaehlen 'telegram_bot.py') Prozess(e)"
    tail -2 bot.log 2>/dev/null
    ;;

alles-neu)
    "$0" web-neu --lokal
    "$0" bot-neu --lokal
    ;;

logs)
    n="${ARGUMENTE[0]:-20}"
    echo "--- cron.log ---";    tail -"$n" cron.log 2>/dev/null
    echo; echo "--- monitor.log ---"; tail -"$n" monitor.log 2>/dev/null
    echo; echo "--- bot.log ---";     tail -5 bot.log 2>/dev/null
    ;;

lauf)
    nur_im_betrieb lauf || exit 1
    echo "Starte Monitorlauf ${ARGUMENTE[*]:-ohne Claude} ..."
    "$PYTHON" ki_monitor.py --web ${ARGUMENTE[*]:-} 2>&1 | tail -20
    ;;

bericht)
    nur_im_betrieb bericht || exit 1
    "$PYTHON" ki_monitor.py --report 2>&1 | tail -20
    ;;

probealarm)
    nur_im_betrieb probealarm || exit 1
    echo "Loest die volle Meldekette aus - die Lampe blinkt, bis sie abgestellt wird."
    "$PYTHON" probealarm.py 2>&1 | tail -20
    ;;

probealarm-aus)
    if [ -f blink.laeuft ]; then
        touch blink.stopp
        echo "Alarm abgestellt."
    else
        echo "Es blinkt gerade nichts."
    fi
    ;;

pruefen)
    "$PYTHON" - <<'PY'
import json, os, sys
sys.path.insert(0, ".")
import ki_monitor as km
fehlt = []
c = km.konfig_laden()
if c is None:
    print("config.json nicht lesbar"); sys.exit(1)
rolle = c.get("rolle") or "unbekannt"
if rolle != "betrieb":
    # Ein Arbeitsplatz braucht die Meldekette nicht - dort waere ihr Fehlen
    # kein Mangel, sondern der Normalfall.
    modelle = (c.get("tokenpreise") or {}).get("modelle") or []
    ohne = [m["modell"] for m in modelle if not m.get("ausgabe")]
    print("Rolle '%s': geteilte Konfiguration mit %d Modellen%s."
          % (rolle, len(modelle),
             ", ohne Preis: " + ", ".join(ohne) if ohne else ""))
    print("Meldekette wird hier nicht geprueft - die gehoert in den Betrieb.")
    sys.exit(0)

# Die Bloecke, ohne die die Meldekette still bleibt - und zwar ohne Fehlermeldung.
for block, pflicht in (("mail", ("aktiv", "an")),
                       ("telegram", ("aktiv",)),
                       ("hue", ("aktiv", "bridge"))):
    if block not in c:
        fehlt.append("Block '%s' fehlt vollstaendig" % block)
        continue
    for schluessel in pflicht:
        if not c[block].get(schluessel):
            fehlt.append("%s.%s fehlt" % (block, schluessel))

for block, feld, name in (("telegram", "token_datei", "Bot-Token"),
                          ("telegram", "chat_datei", "Chat-Kennung"),
                          ("hue", "schluessel_datei", "Hue-Schluessel")):
    datei = (c.get(block) or {}).get(feld)
    if datei and not os.path.exists(datei):
        fehlt.append("%s (%s) nicht vorhanden" % (datei, name))

kopie = c.get("bericht_kopie") or ""
if kopie and not os.path.isdir(os.path.dirname(kopie)):
    fehlt.append("bericht_kopie zeigt auf %s - Ordner gibt es hier nicht"
                 % os.path.dirname(kopie))

modelle = (c.get("tokenpreise") or {}).get("modelle") or []
ohne = [m["modell"] for m in modelle if not m.get("ausgabe")]
if ohne:
    fehlt.append("Modelle ohne Preis: " + ", ".join(ohne))

if fehlt:
    print("Beanstandungen:")
    for f in fehlt:
        print("  -", f)
    sys.exit(1)
print("Konfiguration vollstaendig: %d Modelle, Meldekette eingerichtet."
      % len(modelle))
PY
    ;;

*)
    sed -n '3,30p' "$0" | sed 's/^# \{0,1\}//'
    ;;
esac
