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
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASIS = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(BASIS, "web")
STOPP = os.path.join(BASIS, "blink.stopp")
LAEUFT = os.path.join(BASIS, "blink.laeuft")
PORT = int(os.environ.get("KI_INVEST_PORT", "8088"))


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
        return super().do_GET()

    def log_message(self, form, *args):
        pass                       # kein Zugriffsprotokoll, das Log bleibt lesbar


if __name__ == "__main__":
    os.makedirs(WEB, exist_ok=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
