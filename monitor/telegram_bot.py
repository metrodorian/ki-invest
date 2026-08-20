#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram-Empfaenger fuer den KI-Invest-Monitor.

Laeuft dauerhaft und wartet auf Befehle. Damit laesst sich der Monitor auch
von unterwegs bedienen, ohne die Weboberflaeche im Heimnetz zu erreichen.

Lange Abfragen (long polling) halten die Verbindung offen, bis etwas kommt -
das ist sparsamer als staendiges Nachfragen und antwortet trotzdem sofort.
"""

import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

BASIS = os.path.dirname(os.path.abspath(__file__))
STOPP = os.path.join(BASIS, "blink.stopp")
LAEUFT = os.path.join(BASIS, "blink.laeuft")
OFFSET_DATEI = os.path.join(BASIS, "telegram.offset")

HILFE = """<b>Befehle</b>

<b>status</b> - Barometer, Positionen, Puffer, Restzeit
<b>kurse</b> - aktuelle Scheinkurse und Ergebnis
<b>bericht</b> - den letzten Bericht als Datei
<b>neu</b> - einen frischen Bericht rechnen (dauert einige Minuten)
<b>termine</b> - was als Naechstes ansteht
<b>tokenpreise</b> - Faehigkeit und Preis je Million Token

<b>ruhe</b> - Alarme bis morgen frueh stumm (Ueberwachung laeuft weiter)
<b>ruhe aus</b> - Stummschaltung sofort aufheben
<b>barriere 324.00 421.08</b> - Reset-Barrieren nachtragen (Nvidia, Vertiv)
<b>notiz Text</b> - Vermerk fuer den naechsten Bericht
<b>notiz weg</b> - Vermerk loeschen
<b>verkauft MG4U8W</b> - Position als geschlossen markieren

<b>stop</b> - laufenden Alarm beenden
<b>probealarm</b> - die Meldekette einmal ausloesen
<b>hilfe</b> - diese Liste"""


def konfig_laden():
    return json.load(open(os.path.join(BASIS, "config.json")))


def zugang(konfig):
    einst = konfig.get("telegram", {})

    def lesen(wert, datei):
        if wert:
            return wert
        if datei and os.path.exists(datei):
            return open(datei).read().strip()
        return None

    return (lesen(einst.get("token"), einst.get("token_datei")),
            lesen(einst.get("chat"), einst.get("chat_datei")))


def senden(token, chat, text, still=False):
    daten = urllib.parse.urlencode({
        "chat_id": chat, "text": text[:4000], "parse_mode": "HTML",
        "disable_web_page_preview": "true",
        "disable_notification": "true" if still else "false"}).encode()
    try:
        urllib.request.urlopen(
            "https://api.telegram.org/bot%s/sendMessage" % token,
            data=daten, timeout=20).read()
    except Exception as fehler:                                  # noqa: BLE001
        print("senden:", fehler, flush=True)


def datei_senden(konfig, pfad, beschriftung):
    sys.path.insert(0, BASIS)
    import ki_monitor as km
    try:
        with open(pfad) as f:
            inhalt = f.read()
    except IOError:
        return False
    return km.telegram_datei(konfig, inhalt, os.path.basename(pfad),
                             beschriftung, still=True)


# ------------------------------------------------------------------ Befehle

def antwort_status(konfig):
    zustand = json.load(open(os.path.join(BASIS, "state.json"))) \
        if os.path.exists(os.path.join(BASIS, "state.json")) else {}
    pfad = os.path.join(BASIS, "daten.json")
    if not os.path.exists(pfad):
        return "Noch keine Daten. Mit <b>neu</b> einen Bericht rechnen."
    d = json.load(open(pfad))

    wert, lage = d["barometer"]
    zeilen = ["<b>Barometer %d von 100</b> &#183; %s" % (wert, lage), ""]

    gesamt = einsatz = 0.0
    for p in d.get("positionen", []):
        v = p.get("wertverlauf")
        if not v:
            continue
        jetzt = v["punkte"][-1]["wert"]
        gesamt += jetzt
        einsatz += v["einsatz"]
        puffer = p.get("barriere_abstand")
        zeilen.append("%s  <b>%.0f &#8364;</b> (%+.0f)" %
                      (p["name"], jetzt, jetzt - v["einsatz"]))
        zeilen.append("  Basiswert %.2f (%+.2f%%) &#183; Puffer %s" %
                      (p["kurs"], p["tag_prozent"],
                       ("%.1f%%" % puffer) if puffer is not None else "?"))
    if einsatz:
        zeilen += ["", "<b>Gesamt %.0f &#8364;</b> (%+.0f, %+.1f%%)"
                   % (gesamt, gesamt - einsatz, (gesamt / einsatz - 1) * 100)]

    limit = konfig.get("zeitlimit_bis")
    if limit:
        try:
            rest = (datetime.strptime(limit, "%Y-%m-%d").date() - date.today()).days
            zeilen.append("Zeitlimit %s &#183; noch %d Tage"
                          % (datetime.strptime(limit, "%Y-%m-%d").strftime("%d.%m."),
                             rest))
        except ValueError:
            pass
    if zustand.get("letzter_lauf"):
        zeilen.append("Letzter Lauf: %s" % zustand["letzter_lauf"].replace("T", " "))
    if os.path.exists(LAEUFT):
        zeilen += ["", "⚠️ <b>Ein Alarm laeuft.</b> Mit <b>stop</b> beenden."]
    return "\n".join(zeilen)


def antwort_kurse(konfig):
    pfad = os.path.join(BASIS, "daten.json")
    if not os.path.exists(pfad):
        return "Noch keine Daten."
    d = json.load(open(pfad))
    zeilen = ["<b>Scheinkurse</b>", ""]
    for p in d.get("positionen", []):
        if not p.get("scheinkurs"):
            continue
        v = p.get("wertverlauf") or {}
        einstand = (v.get("einsatz", 0) / p["stueck"]) if p.get("stueck") else 0
        zeilen.append("%s (%s)" % (p["name"], p.get("wkn", "")))
        zeilen.append("  %.4f &#8364; &#215; %d Stueck" % (p["scheinkurs"], p["stueck"]))
        if einstand:
            zeilen.append("  Einstand %.4f &#8364; &#183; %+.1f%%"
                          % (einstand, (p["scheinkurs"] / einstand - 1) * 100))
        zeilen.append("  Quelle: %s" % p.get("kurs_quelle", "?"))
        zeilen.append("")
    return "\n".join(zeilen) or "Keine Kurse vorhanden."


def antwort_tokenpreise(konfig):
    """Der direkte Effizienzmesswert - die Preisseite der These."""
    einst = konfig.get("tokenpreise") or {}
    modelle = einst.get("modelle") or []
    if not modelle:
        return "Keine Token-Preise hinterlegt."

    modelle = sorted(modelle, key=lambda x: (-(x.get("faehigkeit") or 0),
                                             x.get("rang") or 999))
    zeilen = ["<b>Faehigkeit und Preis je Mio. Token</b> (Ausgabe, USD)",
              "<i>faehigste zuerst</i>", ""]
    for m in modelle:
        preis = ("%6.2f" % m["ausgabe"]) if m.get("ausgabe") else "     -"
        zeilen.append("<code>%3s %s</code>  %s%s"
                      % (m.get("faehigkeit", "?"), preis, m["modell"],
                         "  (%s)" % m["land"] if m.get("land") else ""))

    verlauf = []
    pfad = os.path.join(BASIS, "tokenpreise.json")
    if os.path.exists(pfad):
        try:
            verlauf = json.load(open(pfad))
        except ValueError:
            verlauf = []
    if len(verlauf) >= 2:
        a, b = verlauf[-2], verlauf[-1]
        if a.get("schnitt_ausgabe"):
            v = (b["schnitt_ausgabe"] / a["schnitt_ausgabe"] - 1) * 100
            zeilen += ["", "Schnitt der Spitzengruppe: <b>%.2f</b> (%+.1f%% seit %s)"
                       % (b["schnitt_ausgabe"], v, a.get("datum", "?"))]
    if verlauf and verlauf[-1].get("luecke"):
        j = verlauf[-1]
        zeilen += ["Gleiche Guete: Westen <b>%.2f</b> gegen China <b>%.2f</b> "
                   "= Faktor <b>%.1f</b>" % (j["preis_us"], j["preis_cn"], j["luecke"])]
    elif verlauf:
        zeilen += ["", "Schnitt der Spitzenklasse: <b>%.2f</b> (erster Stand)"
                   % verlauf[-1]["schnitt_ausgabe"]]

    zeilen += ["", "★ zaehlt zur Spitzenklasse. Fallende Preise entwerten "
               "Rechenleistung und stuetzen die These."]
    return "\n".join(zeilen)


def antwort_termine(konfig):
    heute = date.today()
    zeilen = ["<b>Termine</b>", ""]
    for t in sorted(konfig.get("termine", []), key=lambda x: x.get("datum", "")):
        try:
            tag = datetime.strptime(t["datum"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        rest = (tag - heute).days
        if rest < 0:
            continue
        wann = ("heute" if rest == 0 else "morgen" if rest == 1
                else "in %d Tagen" % rest)
        zeilen.append("%s &#183; %s &#8212; <b>%s</b>"
                      % (tag.strftime("%d.%m."), t["was"], wann))
    return "\n".join(zeilen) if len(zeilen) > 2 else "Keine anstehenden Termine."


def konfig_speichern(konfig):
    with open(os.path.join(BASIS, "config.json"), "w") as f:
        json.dump(konfig, f, indent=2, ensure_ascii=False, default=str)


def antwort_ruhe(konfig, rest):
    """Stummschaltung bis zum naechsten Morgen. Die Ueberwachung laeuft
    weiter, nur Lampe und Erinnerungen schweigen."""
    if rest.strip() in ("aus", "ende", "weg"):
        konfig.pop("ruhe_bis", None)
        konfig_speichern(konfig)
        return "Stummschaltung aufgehoben. Alarme sind wieder scharf."

    bis = konfig.get("hue", {}).get("nacht_bis", 7)
    ziel = datetime.now().replace(hour=bis, minute=0, second=0, microsecond=0)
    if ziel <= datetime.now():
        ziel = ziel.replace(day=ziel.day) + timedelta(days=1)
    konfig["ruhe_bis"] = ziel.isoformat(timespec="seconds")
    konfig_speichern(konfig)
    if os.path.exists(LAEUFT):
        open(STOPP, "w").close()
    return ("Alarme stumm bis <b>%s Uhr</b>. Die Ueberwachung laeuft weiter, "
            "Mail und Bericht kommen wie gewohnt." % ziel.strftime("%d.%m., %H:%M"))


def antwort_barriere(konfig, rest):
    zahlen = []
    for stueck in rest.replace(",", ".").split():
        try:
            zahlen.append(float(stueck))
        except ValueError:
            pass
    positionen = konfig.get("positionen", [])
    if not zahlen:
        zeilen = ["<b>Aktuell hinterlegt</b>", ""]
        for p in positionen:
            zeilen.append("%s (%s): %.2f USD, Stand %s"
                          % (p["name"], p.get("wkn", ""), p.get("barriere", 0),
                             p.get("barriere_stand", "?")))
        zeilen += ["", "Nachtragen mit: <b>barriere %s</b>"
                   % " ".join("%.2f" % p.get("barriere", 0) for p in positionen)]
        return "\n".join(zeilen)

    if len(zahlen) != len(positionen):
        return ("Ich brauche %d Werte in der Reihenfolge %s."
                % (len(positionen), ", ".join(p.get("wkn", "?") for p in positionen)))

    zeilen = ["<b>Barrieren aktualisiert</b>", ""]
    heute = date.today().isoformat()
    for p, neu in zip(positionen, zahlen):
        alt = p.get("barriere")
        p["barriere"] = neu
        p["barriere_stand"] = heute
        zeilen.append("%s: %.2f &#8594; <b>%.2f</b> USD"
                      % (p.get("wkn", "?"), alt or 0, neu))
    konfig_speichern(konfig)
    zeilen += ["", "Beim naechsten Lauf wird damit gerechnet."]
    return "\n".join(zeilen)


def antwort_notiz(konfig, rest):
    text = rest.strip()
    if text.lower() in ("weg", "loeschen", "aus", "leer"):
        konfig.pop("notiz", None)
        konfig_speichern(konfig)
        return "Vermerk geloescht."
    if not text:
        vorhanden = konfig.get("notiz")
        return ("Aktueller Vermerk: <b>%s</b>" % vorhanden) if vorhanden \
            else "Kein Vermerk hinterlegt."
    konfig["notiz"] = {"text": text[:400],
                       "seit": datetime.now().strftime("%d.%m.%Y, %H:%M")}
    konfig_speichern(konfig)
    return "Vermerk gesetzt. Er steht ab dem naechsten Bericht oben."


def antwort_verkauft(konfig, rest):
    kennung = rest.strip().upper()
    positionen = konfig.get("positionen", [])
    if not kennung:
        offen = [p.get("wkn", "?") for p in positionen if not p.get("geschlossen")]
        return ("Welche Position? Offen: <b>%s</b>" % ", ".join(offen)) if offen \
            else "Alle Positionen sind bereits als geschlossen markiert."

    for p in positionen:
        if p.get("wkn", "").upper() == kennung:
            if p.get("geschlossen"):
                p.pop("geschlossen", None)
                konfig_speichern(konfig)
                return ("%s ist wieder als offen markiert." % kennung)
            p["geschlossen"] = date.today().isoformat()
            konfig_speichern(konfig)
            return ("%s als geschlossen markiert. Sie wird nicht mehr bewertet "
                    "und loest keine Alarme mehr aus. Nochmal senden macht es "
                    "rueckgaengig." % kennung)
    return "Kenne <b>%s</b> nicht. Bekannt: %s" % (
        kennung, ", ".join(p.get("wkn", "?") for p in positionen))


def bericht_neu_starten():
    """Der Lauf dauert Minuten, deshalb im Hintergrund - der Empfaenger
    bleibt derweil ansprechbar."""
    subprocess.Popen([sys.executable, os.path.join(BASIS, "ki_monitor.py"),
                      "--report"], cwd=BASIS, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def probealarm_starten():
    subprocess.Popen([sys.executable, os.path.join(BASIS, "probealarm.py")],
                     cwd=BASIS, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def verarbeiten(konfig, token, chat, text):
    befehl = text.strip().lower().lstrip("/")

    if befehl.startswith("stop") or befehl in ("aus", "halt"):
        if os.path.exists(LAEUFT):
            open(STOPP, "w").close()
            return "Alarm wird beendet."
        return "Es laeuft gerade kein Alarm."

    if befehl in ("hilfe", "help", "?", "start"):
        return HILFE
    if befehl in ("status", "lage"):
        return antwort_status(konfig)
    if befehl in ("kurse", "kurs", "depot"):
        return antwort_kurse(konfig)
    if befehl in ("termine", "termin"):
        return antwort_termine(konfig)
    if befehl in ("tokenpreise", "token", "preise"):
        return antwort_tokenpreise(konfig)

    if befehl in ("bericht", "report"):
        pfad = os.path.join(BASIS, "bericht.html")
        if not os.path.exists(pfad):
            return "Noch kein Bericht vorhanden. <b>neu</b> rechnet einen."
        alter = datetime.fromtimestamp(os.path.getmtime(pfad))
        datei_senden(konfig, pfad, "Bericht vom %s"
                     % alter.strftime("%d.%m.%Y, %H:%M"))
        return None

    if befehl in ("neu", "aktualisieren", "lauf"):
        bericht_neu_starten()
        return ("Neuer Bericht wird gerechnet. Das dauert einige Minuten, "
                "danach kommt er per Mail und liegt unter <b>bericht</b> bereit.")

    if befehl in ("probealarm", "testalarm"):
        probealarm_starten()
        return "Probealarm wird ausgeloest."

    # Befehle mit Beiwerk: erstes Wort ist der Befehl, der Rest gehoert dazu
    teile = befehl.split(None, 1)
    kopf = teile[0] if teile else ""
    rest = teile[1] if len(teile) > 1 else ""

    if kopf == "ruhe":
        return antwort_ruhe(konfig, rest)
    if kopf in ("barriere", "barrieren"):
        return antwort_barriere(konfig, rest)
    if kopf in ("notiz", "vermerk"):
        # Grosskleinschreibung des Vermerks erhalten
        roh = text.strip()
        nach = roh.split(None, 1)
        return antwort_notiz(konfig, nach[1] if len(nach) > 1 else "")
    if kopf in ("verkauft", "geschlossen", "zu"):
        return antwort_verkauft(konfig, rest)

    return ("Unbekannter Befehl. <b>hilfe</b> zeigt, was geht.")


# ------------------------------------------------------------------ Schleife

def main():
    konfig = konfig_laden()
    token, chat = zugang(konfig)
    if not token or not chat:
        print("Kein Telegram-Zugang hinterlegt", flush=True)
        return 1

    offset = 0
    if os.path.exists(OFFSET_DATEI):
        try:
            offset = int(open(OFFSET_DATEI).read().strip())
        except ValueError:
            offset = 0

    print("Empfaenger gestartet", flush=True)
    while True:
        try:
            url = ("https://api.telegram.org/bot%s/getUpdates?timeout=50&offset=%d"
                   % (token, offset))
            with urllib.request.urlopen(url, timeout=70) as antwort:
                ergebnis = json.loads(antwort.read()).get("result", [])
        except Exception:                                        # noqa: BLE001
            time.sleep(5)
            continue

        for u in ergebnis:
            offset = max(offset, u.get("update_id", 0) + 1)
            with open(OFFSET_DATEI, "w") as f:
                f.write(str(offset))

            nachricht = u.get("message") or u.get("edited_message") or {}
            if str((nachricht.get("chat") or {}).get("id")) != str(chat):
                continue                     # nur der eigene Chat wird bedient
            text = nachricht.get("text")
            if not text:
                continue

            print("Befehl: %s" % text[:60], flush=True)
            try:
                konfig = konfig_laden()      # frisch lesen, falls geaendert
                rueck = verarbeiten(konfig, token, chat, text)
            except Exception as fehler:                          # noqa: BLE001
                rueck = "Fehler bei der Verarbeitung: %s" % str(fehler)[:200]
            if rueck:
                senden(token, chat, rueck)


if __name__ == "__main__":
    sys.exit(main())
