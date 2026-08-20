#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Loest die vollstaendige Meldekette einmal aus, damit sie sich pruefen laesst."""

import json
import os
import sys

BASIS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASIS)
import ki_monitor as km                                          # noqa: E402

d = km.json_laden(os.path.join(BASIS, "daten.json"), None)
konfig = km.konfig_laden()
if not d or not konfig:
    sys.exit(1)

d["claude"] = {"eilmeldung": {
    "noetig": True, "stufe": "kritisch",
    "ausloeser": "Probealarm, von Hand ausgeloest",
    "betreff": "Probealarm - Pruefung der Meldekette",
    "schlagzeile": "Kein echtes Ereignis, nur ein Test.",
    "was_geschehen_ist": "Dieser Alarm wurde von Hand ausgeloest, um Mail, "
                         "Telegram, Anhang und Lampe einmal gemeinsam zu pruefen.",
    "warum_es_zaehlt": "Wenn alles ankommt, erreicht dich auch eine echte "
                       "Meldung - unterwegs wie zu Hause.",
    "was_du_tun_koenntest": "Mit 'stop' beenden oder ueber den roten Balken "
                            "auf der Berichtsseite.",
    "zahlen": ["Barometer: %d von 100" % d["barometer"][0]],
}}

zustand = km.json_laden(km.STATE_PFAD, {})
zustand["eilmeldungen"] = []
km.eilmeldung_verschicken(konfig, d, zustand)
km.json_speichern(km.STATE_PFAD, zustand)
