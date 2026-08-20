#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dauersignal bei einer Eilmeldung.

Zwei Dinge laufen hier im Fuenf-Sekunden-Takt weiter, bis der Alarm abgestellt
wird: Die Hue-Lampe blinkt, und Telegram bekommt eine kurze Erinnerung. Anders
als ein einmaliger Hinweis laesst sich das nicht verschlafen.

Beendet wird beides ueber die Stopp-Datei, die der Webserver auf Knopfdruck
anlegt. Nachts gilt ein Kontingent - dann schweigen Lampe und Telefon bis zum
Morgen, der Alarm bleibt aber bestehen.
"""

import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

BASIS = os.path.dirname(os.path.abspath(__file__))
STOPP = os.path.join(BASIS, "blink.stopp")
LAEUFT = os.path.join(BASIS, "blink.laeuft")
ALARMTEXT = os.path.join(BASIS, "alarm.txt")
TAKT = 5.0
HOECHSTDAUER = 24 * 3600         # Sicherheitsnetz, falls niemand abstellt

# Nachtruhe: In diesem Fenster blinkt die Lampe nur ein begrenztes Kontingent
# und schweigt danach bis zum Morgen. Der Alarm bleibt aber bestehen und
# nimmt die Arbeit ab dem Weckzeitpunkt wieder auf.
NACHT_VON = 22          # Stunde, ab der die Ruhe gilt
NACHT_BIS = 7           # Stunde, ab der es weitergeht
NACHT_KONTINGENT = 300  # Sekunden, also fuenf Minuten je Nacht


def ist_nacht(jetzt, von, bis):
    """Nachtfenster geht ueber Mitternacht, deshalb die Oder-Verknuepfung."""
    return jetzt.hour >= von or jetzt.hour < bis


def naechster_morgen(jetzt, bis):
    ziel = jetzt.replace(hour=bis, minute=0, second=0, microsecond=0)
    if ziel <= jetzt:
        ziel += timedelta(days=1)
    return ziel


def hue_kontext():
    k = ssl.create_default_context()
    k.check_hostname = False
    k.verify_mode = ssl.CERT_NONE
    return k


def telegram_zugang(konfig):
    einst = konfig.get("telegram", {})
    if not einst.get("aktiv"):
        return None, None

    def lesen(wert, datei):
        if wert:
            return wert
        if datei and os.path.exists(datei):
            return open(datei).read().strip()
        return None

    return (lesen(einst.get("token"), einst.get("token_datei")),
            lesen(einst.get("chat"), einst.get("chat_datei")))


def telegram_abruf(token, offset):
    """Holt neue Nachrichten an den Bot. Ohne Wartezeit, damit die Schleife
    nicht haengt."""
    url = ("https://api.telegram.org/bot%s/getUpdates?timeout=0&offset=%d"
           % (token, offset))
    try:
        with urllib.request.urlopen(url, timeout=8) as antwort:
            return json.loads(antwort.read()).get("result", [])
    except Exception:                                            # noqa: BLE001
        return []


def stopp_per_telegram(konfig, offset):
    """
    Prueft, ob per Telegram 'stop' geschrieben wurde.

    Gibt den neuen Offset zurueck und ob abgebrochen werden soll. So laesst
    sich der Alarm auch dann beenden, wenn man die Weboberflaeche gerade
    nicht erreicht - unterwegs etwa.
    """
    token, chat = telegram_zugang(konfig)
    if not token:
        return offset, False

    abbrechen = False
    for u in telegram_abruf(token, offset):
        offset = max(offset, u.get("update_id", 0) + 1)
        nachricht = u.get("message") or u.get("edited_message") or {}
        text = (nachricht.get("text") or "").strip().lower()
        if text.startswith("stop") or text in ("/stop", "aus", "halt"):
            abbrechen = True
    return offset, abbrechen


def telegram_erinnerung(konfig, text, nummer):
    """Kurze Wiedervorlage, damit der Alarm nicht untergeht."""
    einst = konfig.get("telegram", {})
    if not einst.get("aktiv"):
        return

    def lesen(wert, datei):
        if wert:
            return wert
        if datei and os.path.exists(datei):
            return open(datei).read().strip()
        return None

    token = lesen(einst.get("token"), einst.get("token_datei"))
    chat = lesen(einst.get("chat"), einst.get("chat_datei"))
    if not token or not chat:
        return

    web = (konfig.get("mail", {}) or {}).get("web_adresse", "")
    nachricht = ("\u26a0\ufe0f Alarm laeuft weiter (%d)\n%s\n\nAbstellen: %s"
                 % (nummer, text, web))
    daten = urllib.parse.urlencode({"chat_id": chat, "text": nachricht[:900]}).encode()
    try:
        urllib.request.urlopen(
            "https://api.telegram.org/bot%s/sendMessage" % token,
            data=daten, timeout=8).read()
    except Exception:                                            # noqa: BLE001
        pass


def main():
    konfig = json.load(open(os.path.join(BASIS, "config.json")))
    einst = konfig.get("hue", {})
    lampen = einst.get("dauerblink_lampen") or einst.get("lampen") or []
    if not einst.get("aktiv") or not lampen:
        return 1

    schluessel = einst.get("schluessel")
    if not schluessel and einst.get("schluessel_datei"):
        schluessel = open(einst["schluessel_datei"]).read().strip()
    if not schluessel:
        return 1

    stamm = "https://%s/api/%s/lights/" % (einst["bridge"], schluessel)
    kontext = hue_kontext()

    def setzen(nr, zustand):
        req = urllib.request.Request(
            stamm + "%d/state" % nr, data=json.dumps(zustand).encode(),
            method="PUT", headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=6, context=kontext).read()
        except Exception:                                        # noqa: BLE001
            pass

    def lesen(nr):
        try:
            with urllib.request.urlopen(stamm + str(nr), timeout=6,
                                        context=kontext) as a:
                return json.loads(a.read().decode()).get("state", {})
        except Exception:                                        # noqa: BLE001
            return {}

    # Ausgangszustand merken, damit er am Ende zurueckkommt
    vorher = {nr: lesen(nr) for nr in lampen}

    if os.path.exists(STOPP):
        os.remove(STOPP)
    with open(LAEUFT, "w") as f:
        f.write(str(os.getpid()))

    nacht_von = einst.get("nacht_von", NACHT_VON)
    nacht_bis = einst.get("nacht_bis", NACHT_BIS)
    kontingent = einst.get("nacht_kontingent_sekunden", NACHT_KONTINGENT)

    def warten(sekunden):
        """Wartet, bricht aber sofort ab, wenn der Alarm abgestellt wird."""
        ende = time.time() + sekunden
        while time.time() < ende and not os.path.exists(STOPP):
            time.sleep(0.25)

    alarmtext = ""
    if os.path.exists(ALARMTEXT):
        alarmtext = open(ALARMTEXT).read().strip()[:400]

    # Ausgangsstand der Telegram-Nachrichten merken, damit ein altes "stop"
    # aus dem Verlauf den frischen Alarm nicht sofort beendet.
    telegram_offset = 0
    token_start, _ = telegram_zugang(konfig)
    if token_start:
        for u in telegram_abruf(token_start, 0):
            telegram_offset = max(telegram_offset, u.get("update_id", 0) + 1)
    telegram_takt = einst.get("telegram_takt_sekunden", 5)
    naechste_meldung = 0.0
    meldungen = 0

    start = time.time()
    an = True
    nacht_verbraucht = 0.0
    letzte_nacht = None

    try:
        while not os.path.exists(STOPP) and (time.time() - start) < HOECHSTDAUER:
            jetzt = datetime.now()

            if ist_nacht(jetzt, nacht_von, nacht_bis):
                # Je Nacht ein eigenes Kontingent. Der Schluessel ist der
                # Abend, zu dem die Nacht gehoert.
                kennung = (jetzt.date() if jetzt.hour >= nacht_von
                           else (jetzt - timedelta(days=1)).date())
                if kennung != letzte_nacht:
                    letzte_nacht = kennung
                    nacht_verbraucht = 0.0

                if nacht_verbraucht >= kontingent:
                    for nr in lampen:
                        setzen(nr, {"on": False})
                    morgen = naechster_morgen(jetzt, nacht_bis)
                    print("Nachtruhe: schweigt bis %s"
                          % morgen.strftime("%d.%m. %H:%M"), flush=True)
                    warten(max(30, (morgen - jetzt).total_seconds()))
                    continue
                nacht_verbraucht += TAKT

            for nr in lampen:
                if an:
                    zustand = {"on": True, "bri": 254}
                    if "hue" in vorher.get(nr, {}):
                        zustand.update({"hue": einst.get("hue_kritisch", 0),
                                        "sat": 254})
                    setzen(nr, zustand)
                else:
                    setzen(nr, {"on": False})
            an = not an

            if telegram_takt and time.time() >= naechste_meldung:
                meldungen += 1
                telegram_erinnerung(konfig, alarmtext, meldungen)
                naechste_meldung = time.time() + telegram_takt

            telegram_offset, abbrechen = stopp_per_telegram(konfig, telegram_offset)
            if abbrechen:
                telegram_erinnerung.zuletzt = None
                open(STOPP, "w").close()
                token, chat = telegram_zugang(konfig)
                if token and chat:
                    daten = urllib.parse.urlencode(
                        {"chat_id": chat,
                         "text": "Alarm beendet. Die Lampe geht zurueck in ihren "
                                 "vorherigen Zustand."}).encode()
                    try:
                        urllib.request.urlopen(
                            "https://api.telegram.org/bot%s/sendMessage" % token,
                            data=daten, timeout=8).read()
                    except Exception:                            # noqa: BLE001
                        pass
                break

            warten(TAKT)
    finally:
        for nr, zustand in vorher.items():
            zurueck = {"on": zustand.get("on", False),
                       "bri": zustand.get("bri", 200), "alert": "none"}
            for feld in ("hue", "sat", "ct"):
                if feld in zustand:
                    zurueck[feld] = zustand[feld]
            setzen(nr, zurueck)
        for datei in (LAEUFT, STOPP):
            if os.path.exists(datei):
                os.remove(datei)
    return 0


if __name__ == "__main__":
    sys.exit(main())
