#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Webserver fuer den Bericht auf dem NAS.

Liefert die Berichte aus dem Ordner web/ aus und beantwortet zwei zusaetzliche
Anfragen, damit sich das Dauerblinken der Lampe im Browser abstellen laesst:

    /blink/status   sagt, ob gerade geblinkt wird
    /blink/stopp    beendet es

Laeuft auf einem hohen Port und braucht deshalb keine Systemrechte.
"""

import json
import os
import subprocess
import sys
import urllib.parse
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASIS = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(BASIS, "web")
STOPP = os.path.join(BASIS, "blink.stopp")
LAEUFT = os.path.join(BASIS, "blink.laeuft")
CONFIG = os.path.join(BASIS, "config.json")
PORT = int(os.environ.get("KI_INVEST_PORT", "8088"))


def konfig_lesen():
    # Gemeinsamer Lader: config.json plus die lokale Auflage darueber.
    sys.path.insert(0, BASIS)
    import ki_monitor as km
    return km.konfig_laden() or {}


def konfig_schreiben(konfig):
    # Schreibt nur die geteilte Schicht - Zugangsdaten bleiben lokal.
    sys.path.insert(0, BASIS)
    import ki_monitor as km
    km.konfig_speichern(konfig)


def ruhe_aktiv(konfig):
    bis = konfig.get("ruhe_bis")
    if not bis:
        return None
    try:
        ziel = datetime.fromisoformat(bis)
    except (TypeError, ValueError):
        return None
    return ziel if datetime.now() < ziel else None


def im_hintergrund(*befehl):
    """Startet einen Lauf, ohne die Antwort aufzuhalten."""
    subprocess.Popen(befehl, cwd=BASIS, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True,
                     env=dict(os.environ,
                              PATH="/home/Nutzer/.local/node/bin:" +
                                   os.environ.get("PATH", "")))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def antwort(self, daten):
        koerper = json.dumps(daten).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(koerper)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(koerper)

    def do_GET(self):
        if self.path.startswith("/blink/status"):
            return self.antwort({"blinkt": os.path.exists(LAEUFT)})
        if self.path.startswith("/blink/stopp"):
            lief = os.path.exists(LAEUFT)
            if lief:
                open(STOPP, "w").close()
            return self.antwort({"gestoppt": lief})
        if self.path.startswith("/aktion/"):
            return self.aktion()
        return super().do_GET()

    def aktion(self):
        zerlegt = urllib.parse.urlparse(self.path)
        was = zerlegt.path[len("/aktion/"):].strip("/")
        werte = urllib.parse.parse_qs(zerlegt.query)
        konfig = konfig_lesen()

        # --- Auskuenfte: dieselben Texte wie im Telegram-Chat
        if was == "info":
            welche = (werte.get("was") or [""])[0]
            try:
                sys.path.insert(0, BASIS)
                import telegram_bot as tb
                text = {"status": tb.antwort_status,
                        "kurse": tb.antwort_kurse,
                        "termine": tb.antwort_termine}[welche](konfig)
                return self.antwort({"ok": True, "html": text})
            except Exception as fehler:                          # noqa: BLE001
                return self.antwort({"ok": False,
                                     "text": "Nicht abrufbar: %s" % str(fehler)[:150]})

        if was == "barriere":
            roh = (werte.get("werte") or [""])[0]
            zahlen = []
            for stueck in roh.replace(",", ".").replace(";", " ").split():
                try:
                    zahlen.append(float(stueck))
                except ValueError:
                    pass
            positionen = konfig.get("positionen", [])
            if len(zahlen) != len(positionen):
                return self.antwort({"ok": False,
                                     "text": "Ich brauche %d Werte in der "
                                             "Reihenfolge %s."
                                             % (len(positionen),
                                                ", ".join(p.get("wkn", "?")
                                                          for p in positionen))})
            heute = datetime.now().strftime("%Y-%m-%d")
            teile = []
            for pos, neu in zip(positionen, zahlen):
                teile.append("%s %.2f \u2192 %.2f" % (pos.get("wkn", "?"),
                                                       pos.get("barriere") or 0, neu))
                pos["barriere"] = neu
                pos["barriere_stand"] = heute
            konfig_schreiben(konfig)
            return self.antwort({"ok": True,
                                 "text": "Barrieren aktualisiert: " + ", ".join(teile)})

        if was == "verkauft":
            kennung = (werte.get("wkn") or [""])[0].upper()
            for pos in konfig.get("positionen", []):
                if pos.get("wkn", "").upper() == kennung:
                    if pos.get("geschlossen"):
                        pos.pop("geschlossen", None)
                        antwort = "%s ist wieder offen." % kennung
                    else:
                        pos["geschlossen"] = datetime.now().strftime("%Y-%m-%d")
                        antwort = ("%s als geschlossen markiert. Sie wird nicht "
                                   "mehr bewertet." % kennung)
                    konfig_schreiben(konfig)
                    return self.antwort({"ok": True, "text": antwort})
            return self.antwort({"ok": False, "text": "Unbekannt: %s" % kennung})

        if was == "telegram-bericht":
            im_hintergrund(sys.executable, "-c",
                           "import sys; sys.path.insert(0, %r);"
                           "import telegram_bot as tb;"
                           "c = tb.konfig_laden();"
                           "tb.datei_senden(c, %r, 'Bericht auf Anforderung')"
                           % (BASIS, os.path.join(BASIS, "bericht.html")))
            return self.antwort({"ok": True,
                                 "text": "Bericht geht per Telegram raus."})

        if was == "positionen":
            return self.antwort({"ok": True, "positionen": [
                {"wkn": p.get("wkn"), "name": p.get("name"),
                 "barriere": p.get("barriere"),
                 "stand": p.get("barriere_stand"),
                 "geschlossen": bool(p.get("geschlossen"))}
                for p in konfig.get("positionen", [])]})

        if was == "stand":
            # Bauzeitpunkt der Startseite. Die Seite vergleicht ihn mit dem
            # eigenen und laedt neu, sobald ein Lauf eine neue Fassung
            # geschrieben hat.
            try:
                return self.antwort({"stand": int(os.path.getmtime(
                    os.path.join(WEB, "index.html")))})
            except OSError:
                return self.antwort({"stand": 0})

        if was == "zustand":
            ruhe = ruhe_aktiv(konfig)
            notiz = konfig.get("notiz") or {}
            return self.antwort({
                "ruhe_bis": ruhe.strftime("%d.%m., %H:%M") if ruhe else None,
                "notiz": notiz.get("text"),
                "blinkt": os.path.exists(LAEUFT),
            })

        if was == "neu":
            im_hintergrund(sys.executable, "ki_monitor.py", "--web", "--mit-claude")
            return self.antwort({"ok": True, "text": "Bericht wird neu gerechnet. "
                                                     "Das dauert ein bis zwei Minuten."})

        if was == "probealarm":
            im_hintergrund(sys.executable, "probealarm.py")
            return self.antwort({"ok": True, "text": "Probealarm wird ausgeloest."})

        # Gegenstueck zum Probealarm: derselbe Knopf stellt ihn wieder ab.
        if was == "probealarm-aus":
            lief = os.path.exists(LAEUFT)
            if lief:
                open(STOPP, "w").close()
            return self.antwort({"ok": True,
                                 "text": "Probealarm abgestellt." if lief
                                         else "Es blinkt gerade nichts."})

        if was == "ruhe":
            bis = konfig.get("hue", {}).get("nacht_bis", 7)
            ziel = datetime.now().replace(hour=bis, minute=0, second=0, microsecond=0)
            if ziel <= datetime.now():
                ziel += timedelta(days=1)
            konfig["ruhe_bis"] = ziel.isoformat(timespec="seconds")
            konfig_schreiben(konfig)
            if os.path.exists(LAEUFT):
                open(STOPP, "w").close()
            return self.antwort({"ok": True, "ruhe_bis": ziel.strftime("%d.%m., %H:%M"),
                                 "text": "Alarme stumm bis %s Uhr."
                                         % ziel.strftime("%d.%m., %H:%M")})

        if was == "ruhe-aus":
            konfig.pop("ruhe_bis", None)
            konfig_schreiben(konfig)
            return self.antwort({"ok": True, "ruhe_bis": None,
                                 "text": "Alarme sind wieder scharf."})

        if was == "notiz":
            text = (werte.get("text") or [""])[0].strip()
            if text:
                konfig["notiz"] = {"text": text[:400],
                                   "seit": datetime.now().strftime("%d.%m.%Y, %H:%M")}
                antwort = "Vermerk gesetzt. Er erscheint beim naechsten Lauf."
            else:
                konfig.pop("notiz", None)
                antwort = "Vermerk geloescht."
            konfig_schreiben(konfig)
            return self.antwort({"ok": True, "text": antwort})

        return self.antwort({"ok": False, "text": "Unbekannte Aktion."})

    def log_message(self, form, *args):
        pass                       # kein Zugriffsprotokoll, das Log bleibt lesbar


if __name__ == "__main__":
    os.makedirs(WEB, exist_ok=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
