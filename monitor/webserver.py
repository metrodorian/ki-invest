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
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except (IOError, ValueError):
        return {}


def konfig_schreiben(konfig):
    with open(CONFIG, "w") as f:
        json.dump(konfig, f, indent=2, ensure_ascii=False, default=str)


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
