#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KI-Invest Monitor
=================

Ueberwacht die Short-Positionen und das gesamte Umfeld der KI-Capex-These:
Kurse, abgeleitete Indikatoren, Firmennachrichten, SEC-Meldungen,
Regierungsvorhaben und Veroeffentlichungen der KI-Labore.

Betriebsarten:

    --watch     Nur pruefen, bei Auffaelligkeiten warnen (haeufig, tagsueber)
    --report    Vollstaendigen HTML-Bericht bauen und oeffnen (einmal taeglich)
    --test      Alles einmal durchlaufen, Bericht bauen, aber nicht oeffnen

Zusatzschalter:

    --ohne-claude   Die Claude-Einschaetzung ueberspringen

Keine externen Pakete noetig - nur Standardbibliothek plus optional das
claude-Kommandozeilenwerkzeug fuer die Interpretation.
"""

import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, date
from math import log, sqrt, exp
from statistics import pstdev, mean

BASIS = os.path.dirname(os.path.abspath(__file__))
CONFIG_PFAD = os.path.join(BASIS, "config.json")
STATE_PFAD = os.path.join(BASIS, "state.json")
DATEN_PFAD = os.path.join(BASIS, "daten.json")
BERICHT_PFAD = os.path.join(BASIS, "bericht.html")
LOG_PFAD = os.path.join(BASIS, "monitor.log")

STANDARD_KENNUNG = "ki-invest-monitor"


# =============================================================== Hilfsmittel

def log_schreiben(text):
    zeile = "%s  %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), text)
    try:
        with open(LOG_PFAD, "a") as f:
            f.write(zeile)
    except IOError:
        pass
    print(zeile.rstrip())


def json_laden(pfad, standard):
    try:
        with open(pfad, "r") as f:
            return json.load(f)
    except (IOError, ValueError):
        return standard


def json_speichern(pfad, daten):
    with open(pfad, "w") as f:
        json.dump(daten, f, indent=2, ensure_ascii=False)


def abrufen(url, kennung, versuche=3, pause=1.2):
    """Holt eine URL. SEC verlangt eine Kennung mit Kontaktadresse."""
    kopf = {
        "User-Agent": kennung,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
    }
    kontext = ssl.create_default_context()
    letzter = None
    for versuch in range(versuche):
        try:
            anfrage = urllib.request.Request(url, headers=kopf)
            with urllib.request.urlopen(anfrage, timeout=25, context=kontext) as antwort:
                return antwort.read()
        except Exception as fehler:                              # noqa: BLE001
            letzter = fehler
            time.sleep(pause * (versuch + 1))
    raise IOError("Abruf fehlgeschlagen: %s (%s)" % (url[:80], letzter))


def text_saeubern(text):
    """Entfernt HTML-Reste und schneidet Whitespace zusammen."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = (text.replace("&amp;", "&").replace("&quot;", '"')
                .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">")
                .replace("&nbsp;", " "))
    return re.sub(r"\s+", " ", text).strip()


def html_schuetzen(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# =============================================================== Kursdaten

def kurse_holen(ticker, kennung, zeitraum="6mo"):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/%s"
           "?range=%s&interval=1d" % (urllib.parse.quote(ticker), zeitraum))
    rohdaten = json.loads(abrufen(url, kennung).decode("utf-8"))

    ergebnis = rohdaten.get("chart", {}).get("result")
    if not ergebnis:
        raise ValueError("keine Kursdaten")

    block = ergebnis[0]
    reihe = block["indicators"]["quote"][0].get("close") or []
    schluss = [k for k in reihe if k is not None]
    if len(schluss) < 6:
        raise ValueError("zu wenige Kursdaten")

    meta = block.get("meta", {})
    aktuell = meta.get("regularMarketPrice") or schluss[-1]

    # Der Vortagesschluss kommt immer aus der Kursreihe. "chartPreviousClose"
    # waere der Kurs vor Beginn des Abfragezeitraums (bei 6mo also ein halbes
    # Jahr alt) und darf hier nicht als Rueckfallwert dienen.
    if aktuell and abs(schluss[-1] - aktuell) / aktuell < 0.005:
        vortag = schluss[-2]        # letzte Kerze ist der aktuelle Tag
    else:
        vortag = schluss[-1]        # aktueller Kurs ist neuer als die Reihe

    tag_prozent = ((aktuell / vortag) - 1.0) * 100.0 if vortag else 0.0

    renditen = []
    for i in range(1, len(schluss)):
        if schluss[i - 1] > 0:
            renditen.append(log(schluss[i] / schluss[i - 1]))

    fenster = renditen[-30:] if len(renditen) >= 10 else renditen
    sigma_tag = pstdev(fenster) if len(fenster) > 1 else 0.0
    sigma_jahr = sigma_tag * sqrt(252) * 100.0

    heute_rendite = log(aktuell / vortag) if (vortag and aktuell) else 0.0
    z_wert = (heute_rendite / sigma_tag) if sigma_tag > 0 else 0.0

    def seit(tage):
        if len(schluss) > tage and schluss[-(tage + 1)]:
            return ((aktuell / schluss[-(tage + 1)]) - 1.0) * 100.0
        return None

    hoch = max(schluss[-252:]) if schluss else aktuell
    tief = min(schluss[-252:]) if schluss else aktuell

    return {
        "ticker": ticker,
        "kurs": aktuell,
        "tag_prozent": tag_prozent,
        "woche_prozent": seit(5),
        "monat_prozent": seit(21),
        "quartal_prozent": seit(63),
        "sigma_jahr": sigma_jahr,
        "z_wert": z_wert,
        "abstand_hoch": ((aktuell / hoch) - 1.0) * 100.0 if hoch else None,
        "verlauf": schluss[-60:],
        "waehrung": meta.get("currency", ""),
    }


def position_auswerten(position, kurs):
    faktor = position.get("faktor", -2)
    ergebnis = dict(position)
    ergebnis.update({
        "kurs": kurs["kurs"],
        "tag_prozent": kurs["tag_prozent"],
        "woche_prozent": kurs["woche_prozent"],
        "sigma_jahr": kurs["sigma_jahr"],
        "z_wert": kurs["z_wert"],
        "verlauf": kurs["verlauf"],
        "schein_tag_prozent": faktor * kurs["tag_prozent"],
    })

    barriere = position.get("barriere")
    ergebnis["barriere_abstand"] = (
        ((barriere - kurs["kurs"]) / kurs["kurs"]) * 100.0
        if (barriere and kurs["kurs"]) else None)

    einstieg = position.get("einstiegskurs_basiswert")
    if einstieg:
        basis = ((kurs["kurs"] / einstieg) - 1.0) * 100.0
        ergebnis["basiswert_seit_einstieg"] = basis
        ergebnis["schein_seit_einstieg"] = faktor * basis
    else:
        ergebnis["basiswert_seit_einstieg"] = None
        ergebnis["schein_seit_einstieg"] = None

    ergebnis["haltetage"] = None
    ergebnis["drag_prozent"] = None
    if position.get("einstieg_datum"):
        try:
            start = datetime.strptime(position["einstieg_datum"], "%Y-%m-%d").date()
            tage = (date.today() - start).days
            ergebnis["haltetage"] = tage
            if tage > 0:
                sigma = kurs["sigma_jahr"] / 100.0
                exponent = 0.5 * faktor * (1 - faktor) * sigma * sigma * (tage / 365.0)
                ergebnis["drag_prozent"] = (exp(exponent) - 1.0) * 100.0
        except ValueError:
            pass

    return ergebnis


# ====================================================== Abgeleitete Indikatoren

def mittel(werte):
    sauber = [w for w in werte if w is not None]
    return mean(sauber) if sauber else None


def indikatoren_bauen(kurse, gruppen):
    """Baut die Spreads und Verhaeltnisse, die einzelne Kurse nicht zeigen."""

    def gruppe_schnitt(name, feld):
        ticker = gruppen.get(name, {}).get("ticker", [])
        return mittel([kurse[t][feld] for t in ticker
                       if t in kurse and kurse[t].get(feld) is not None])

    def wert(ticker, feld):
        return kurse.get(ticker, {}).get(feld)

    ind = []

    # --- Konzentration: Nasdaq 100 gegen gleichgewichteten S&P
    ndx = wert("^NDX", "monat_prozent")
    rsp = wert("RSP", "monat_prozent")
    if ndx is not None and rsp is not None:
        spread = ndx - rsp
        ind.append({
            "name": "Konzentrations-Spread",
            "wert": spread,
            "einheit": "%-Pkt (1 Monat)",
            "erklaerung": "Nasdaq 100 gegen gleichgewichteten S&P 500. Faellt der "
                          "Wert unter null, verliert der KI-Schwergewichts-Trade "
                          "gegenueber dem breiten Markt.",
            "these": "gut" if spread < 0 else "schlecht",
        })

    # --- Volatilitaets-Terminstruktur
    vix = wert("^VIX", "kurs")
    vix3m = wert("^VIX3M", "kurs")
    if vix and vix3m:
        verhaeltnis = vix / vix3m
        ind.append({
            "name": "VIX-Terminstruktur",
            "wert": verhaeltnis,
            "einheit": "VIX / VIX3M",
            "erklaerung": "Ueber 1,00 bedeutet akuten Stress (Backwardation) - "
                          "typisch fuer den Beginn einer scharfen Korrektur.",
            "these": "gut" if verhaeltnis > 1.0 else "neutral",
            "nachkomma": 3,
        })

    # --- Neoclouds als Frueherkennung
    neo = gruppe_schnitt("Neoclouds", "woche_prozent")
    ndx_w = wert("^NDX", "woche_prozent")
    if neo is not None and ndx_w is not None:
        rs = neo - ndx_w
        ind.append({
            "name": "Neocloud-Relativstaerke",
            "wert": rs,
            "einheit": "%-Pkt vs Nasdaq (1 Woche)",
            "erklaerung": "Die schuldenfinanzierten GPU-Vermieter reagieren als "
                          "Erste auf Refinanzierungsstress. Deutlich negative Werte "
                          "sind ein Fruehsignal fuer die These.",
            "these": "gut" if rs < -2 else ("schlecht" if rs > 2 else "neutral"),
        })

    # --- Chips gegen Hyperscaler
    chips = gruppe_schnitt("Chips und Halbleiter", "monat_prozent")
    hyper = gruppe_schnitt("Hyperscaler", "monat_prozent")
    if chips is not None and hyper is not None:
        spread = chips - hyper
        ind.append({
            "name": "Chips gegen Hyperscaler",
            "wert": spread,
            "einheit": "%-Pkt (1 Monat)",
            "erklaerung": "Wo sieht der Markt das Risiko? Beim DeepSeek-Schock "
                          "verloren Chips 4-5x mehr als Hyperscaler. Ein stark "
                          "negativer Spread zeigt, dass die Verlagerung laeuft.",
            "these": "gut" if spread < -3 else "neutral",
        })

    # --- Bau- und Ausruestungsseite
    bau = gruppe_schnitt("Rechenzentrums-Bau", "monat_prozent")
    strom = gruppe_schnitt("Strom fuer Rechenzentren", "monat_prozent")
    if bau is not None and ndx is not None:
        rs = bau - ndx
        ind.append({
            "name": "Bau-Relativstaerke",
            "wert": rs,
            "einheit": "%-Pkt vs Nasdaq (1 Monat)",
            "erklaerung": "Kuehlung, Strom, Elektroinstallation. Werden Projekte "
                          "storniert, bricht dieser Korb vor den Chips ein - hier "
                          "sitzt die Vertiv-Position.",
            "these": "gut" if rs < -2 else ("schlecht" if rs > 2 else "neutral"),
        })
    if strom is not None and ndx is not None:
        ind.append({
            "name": "Strom-Relativstaerke",
            "wert": strom - ndx,
            "einheit": "%-Pkt vs Nasdaq (1 Monat)",
            "erklaerung": "Strom ist 2026 der Engpassfaktor. Diese Werte preisen "
                          "den erwarteten Bau ein und drehen mit ihm.",
            "these": "gut" if (strom - ndx) < -2 else "neutral",
        })

    # --- China-Gegenprobe
    china = gruppe_schnitt("China und Gegenseite", "monat_prozent")
    if china is not None and ndx is not None:
        rs = china - ndx
        ind.append({
            "name": "China-Relativstaerke",
            "wert": rs,
            "einheit": "%-Pkt vs Nasdaq (1 Monat)",
            "erklaerung": "Die eigentliche Gegenprobe der These: Gewinnt China den "
                          "KI-Wettlauf, sollten Alibaba, Baidu und SMIC den US-Werten "
                          "davonlaufen.",
            "these": "gut" if rs > 2 else ("schlecht" if rs < -2 else "neutral"),
        })

    # --- Kreditumfeld
    hyg = wert("HYG", "monat_prozent")
    if hyg is not None:
        ind.append({
            "name": "Hochzins-Kredite (HYG)",
            "wert": hyg,
            "einheit": "% (1 Monat)",
            "erklaerung": "Die Neoclouds finanzieren GPUs mit Fremdkapital. Faellt "
                          "HYG, wird ihre Refinanzierung teurer - der wunde Punkt "
                          "des Geschaeftsmodells.",
            "these": "gut" if hyg < -1 else "neutral",
        })

    # --- Speicherpreise als Kostenindikator
    mu = wert("MU", "monat_prozent")
    if mu is not None:
        ind.append({
            "name": "Speicher (Micron)",
            "wert": mu,
            "einheit": "% (1 Monat)",
            "erklaerung": "Microsoft nannte 25 Mrd. USD Mehrkosten allein durch "
                          "hoehere Bauteilpreise. Speicher ist der Treiber - steigt "
                          "er weiter, druecken die Kosten die Capex-Rendite.",
            "these": "neutral",
        })

    return ind


def barometer_rechnen(indikatoren, nachrichten):
    """
    Verdichtet alles zu einem Wert 0-100.
    Hoch bedeutet: Das Umfeld arbeitet gerade fuer die Short-These.
    """
    punkte = []

    gewichte = {
        "Neocloud-Relativstaerke": 1.5,
        "Bau-Relativstaerke": 1.5,
        "Chips gegen Hyperscaler": 1.2,
        "Konzentrations-Spread": 1.0,
        "China-Relativstaerke": 0.8,
        "Strom-Relativstaerke": 0.8,
        "Hochzins-Kredite (HYG)": 0.7,
    }

    for ind in indikatoren:
        gewicht = gewichte.get(ind["name"])
        if gewicht is None:
            continue
        roh = ind["wert"]
        if ind["name"] == "China-Relativstaerke":
            roh = -roh          # dort ist Staerke gut fuer die These
        # -10 bis +10 Prozentpunkte auf -1..+1 abbilden, Vorzeichen drehen
        normiert = max(-1.0, min(1.0, -roh / 10.0))
        punkte.append((normiert, gewicht))

    vix = next((i for i in indikatoren if i["name"] == "VIX-Terminstruktur"), None)
    if vix:
        punkte.append((max(-1.0, min(1.0, (vix["wert"] - 0.92) / 0.15)), 1.0))

    # Nachrichtenbilanz
    fuer = sum(1 for n in nachrichten if n["kategorie"] == "these_bestaetigt")
    gegen = sum(1 for n in nachrichten if n["kategorie"] == "these_gefaehrdet")
    if fuer + gegen > 0:
        bilanz = (fuer - gegen) / float(fuer + gegen)
        punkte.append((bilanz, 1.3))

    if not punkte:
        return 50, "keine Daten"

    summe = sum(w * g for w, g in punkte)
    gewicht_summe = sum(g for _, g in punkte)
    wert = int(round(50 + (summe / gewicht_summe) * 50))
    wert = max(0, min(100, wert))

    if wert >= 68:
        lage = "Umfeld arbeitet fuer die These"
    elif wert >= 56:
        lage = "leicht guenstig"
    elif wert > 44:
        lage = "neutral"
    elif wert > 32:
        lage = "leicht unguenstig"
    else:
        lage = "Umfeld arbeitet gegen die These"
    return wert, lage


# =========================================================== Zusammenfassung

def _zahl_de(wert, nachkomma=1, suffix=""):
    """Zahl mit deutschem Dezimalkomma."""
    if wert is None:
        return "?"
    return (("%+." + str(nachkomma) + "f") % wert).replace(".", ",") + suffix


def zusammenfassung_bauen(positionen, indikatoren, barometer, nachrichten,
                          regierung, sec, blogs, konfig, vorheriges_barometer):
    """
    Schreibt in wenigen Saetzen, was der Bericht bedeutet und was heute
    besonders war. Braucht kein Sprachmodell - liest sich aus den Daten.
    """
    wert, lage = barometer
    saetze = []

    # --- 1. Gesamtlage und Veraenderung
    richtung = ("arbeitet das Umfeld gegen die Short-These" if wert <= 44
                else "arbeitet das Umfeld fuer die Short-These" if wert >= 56
                else "ist das Umfeld weitgehend neutral")
    satz = "Das Barometer steht bei <b>%d von 100</b> (%s), damit %s." % (
        wert, lage, richtung)
    if vorheriges_barometer is not None and vorheriges_barometer != wert:
        diff = wert - vorheriges_barometer
        satz += (" Gegenueber dem letzten Lauf (%d) hat es sich um %d Punkte %s."
                 % (vorheriges_barometer, abs(diff),
                    "verbessert" if diff > 0 else "verschlechtert"))
    saetze.append(satz)

    # --- 2. Was treibt das Barometer
    dafuer = [i for i in indikatoren if i["these"] == "gut"]
    dagegen = [i for i in indikatoren if i["these"] == "schlecht"]
    dagegen.sort(key=lambda i: -abs(i["wert"]))
    dafuer.sort(key=lambda i: -abs(i["wert"]))

    teile = []
    def aufzaehlen(liste):
        return " und ".join("<b>%s</b> (%s)" % (i["name"], _zahl_de(i["wert"], 1))
                            for i in liste)

    if dagegen:
        teile.append("Gegen die These %s vor allem %s." % (
            "laeuft" if len(dagegen[:2]) == 1 else "laufen", aufzaehlen(dagegen[:2])))
    if dafuer:
        teile.append("Dafuer %s %s." % (
            "spricht" if len(dafuer[:2]) == 1 else "sprechen", aufzaehlen(dafuer[:2])))
    if not teile:
        teile.append("Kein Indikator zeigt derzeit klar in eine Richtung.")
    saetze.append(" ".join(teile))

    # --- 3. Positionen
    if positionen:
        bewegungen = ", ".join(
            "%s %s (Schein %s)" % (p["name"].replace(" Short", ""),
                                   _zahl_de(p["tag_prozent"], 2, "%"),
                                   _zahl_de(p["schein_tag_prozent"], 1, "%"))
            for p in positionen)
        satz = "Bei den Positionen: %s." % bewegungen

        puffer = [p for p in positionen if p.get("barriere_abstand") is not None]
        if puffer:
            engster = min(puffer, key=lambda p: p["barriere_abstand"])
            if engster["barriere_abstand"] < 20:
                satz += (" <b>Achtung:</b> Der Barriere-Puffer von %s ist auf %.0f%% "
                         "gefallen." % (engster["name"], engster["barriere_abstand"]))
            elif engster["barriere_abstand"] < 30:
                satz += (" Der knappste Barriere-Puffer liegt bei %.0f%% (%s) und "
                         "verdient Beobachtung."
                         % (engster["barriere_abstand"], engster["name"]))
            else:
                satz += (" Die Barriere-Puffer sind mit mindestens %.0f%% komfortabel."
                         % engster["barriere_abstand"])
        saetze.append(satz)

    # --- 4. Was war besonders: ungewoehnliche Kursbewegungen
    auffaellig = [p for p in positionen if abs(p.get("z_wert", 0)) >= 2.0]
    if auffaellig:
        saetze.append("Ungewoehnlich stark bewegt hat sich %s." % " und ".join(
            "<b>%s</b> mit %s (rund das %.1f-fache der ueblichen Tagesschwankung)"
            % (p["ticker"], _zahl_de(p["tag_prozent"], 2, "%"), abs(p["z_wert"]))
            for p in auffaellig[:2]))

    # --- 5. Nachrichtenbild
    fuer = [n for n in nachrichten if n["kategorie"] == "these_bestaetigt"]
    gegen = [n for n in nachrichten if n["kategorie"] == "these_gefaehrdet"]
    if fuer or gegen:
        satz = ("Von %d gesichteten Meldungen sprechen %d fuer und %d gegen die "
                "These." % (len(nachrichten), len(fuer), len(gegen)))
        wichtigste = None
        if len(gegen) >= len(fuer) and gegen:
            wichtigste = ("Am deutlichsten dagegen", gegen[0])
        elif fuer:
            wichtigste = ("Am deutlichsten dafuer", fuer[0])
        if wichtigste:
            satz += " %s: &bdquo;%s&ldquo;" % (
                wichtigste[0], html_schuetzen(wichtigste[1]["titel"][:130]))
        saetze.append(satz)

    # --- 6. Regierung, SEC, Labore nur wenn wirklich etwas da ist
    besonderes = []
    heikle_regierung = [r for r in regierung if r.get("kategorie") != "neutral"]
    if heikle_regierung:
        besonderes.append("ein Regierungsvorhaben (&bdquo;%s&ldquo;)"
                          % html_schuetzen(heikle_regierung[0]["titel"][:90]))
    if sec:
        besonderes.append("%d neue SEC-Pflichtmeldung%s"
                          % (len(sec), "en" if len(sec) != 1 else ""))
    labor = [b for b in blogs if b.get("kategorie") == "these_bestaetigt"]
    if labor:
        besonderes.append("eine Veroeffentlichung aus den KI-Laboren (&bdquo;%s&ldquo;)"
                          % html_schuetzen(labor[0]["titel"][:90]))
    if besonderes:
        saetze.append("Ausserdem im Blick: %s." % ", ".join(besonderes))

    # --- 7. Naechster Termin
    heute = date.today()
    kommend = []
    for termin in konfig.get("termine", []):
        try:
            tag = datetime.strptime(termin["datum"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        if tag >= heute:
            kommend.append((tag, termin["was"]))
    if kommend:
        kommend.sort()
        tag, was = kommend[0]
        rest = (tag - heute).days
        wann = ("heute" if rest == 0 else "morgen" if rest == 1
                else "in %d Tagen" % rest)
        saetze.append("Naechster Termin: <b>%s</b> &ndash; %s."
                      % (html_schuetzen(was), wann))

    return saetze


# =============================================================== Nachrichten

def rss_lesen(url, kennung, quelle, maximal=15):
    """Liest einen RSS- oder Atom-Feed und liefert vereinheitlichte Eintraege."""
    try:
        rohdaten = abrufen(url, kennung, versuche=2)
        wurzel = ET.fromstring(rohdaten)
    except Exception:                                            # noqa: BLE001
        return []

    eintraege = []

    for element in wurzel.iter():
        marke = element.tag.split("}")[-1]
        if marke not in ("item", "entry"):
            continue

        def feld(*namen):
            for kind in element:
                if kind.tag.split("}")[-1] in namen:
                    if kind.text and kind.text.strip():
                        return kind.text.strip()
                    if kind.get("href"):
                        return kind.get("href")
            return ""

        titel = text_saeubern(feld("title"))
        if not titel:
            continue
        eintraege.append({
            "quelle": quelle,
            "titel": titel,
            "link": feld("link", "id"),
            "datum": feld("pubDate", "published", "updated")[:31],
            "auszug": text_saeubern(feld("description", "summary"))[:300],
        })
        if len(eintraege) >= maximal:
            break
    return eintraege


def google_news(query, kennung, maximal=8):
    url = ("https://news.google.com/rss/search?q=%s&hl=en-US&gl=US&ceid=US:en"
           % urllib.parse.quote(query))
    return rss_lesen(url, kennung, "Google News", maximal)


def yahoo_news(ticker, kennung, maximal=8):
    url = ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=%s&region=US&lang=en-US"
           % urllib.parse.quote(ticker))
    eintraege = rss_lesen(url, kennung, ticker, maximal)
    for e in eintraege:
        e["ticker"] = ticker
    return eintraege


def sec_meldungen(cik, name, kennung, maximal=6):
    """8-K-Meldungen einer Firma ueber den EDGAR-Atom-Feed."""
    url = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=%s"
           "&type=8-K&dateb=&owner=include&count=%d&output=atom" % (cik, maximal))
    eintraege = rss_lesen(url, kennung, "SEC / " + name, maximal)
    for e in eintraege:
        e["firma"] = name
    return eintraege


def regierung_dokumente(begriff, kennung, maximal=5):
    """Vorhaben aus dem US-Bundesanzeiger (Federal Register)."""
    url = ("https://www.federalregister.gov/api/v1/documents.json"
           "?conditions%%5Bterm%%5D=%s&per_page=%d&order=newest"
           "&fields%%5B%%5D=title&fields%%5B%%5D=publication_date"
           "&fields%%5B%%5D=html_url&fields%%5B%%5D=agencies"
           "&fields%%5B%%5D=type&fields%%5B%%5D=abstract"
           % (urllib.parse.quote(begriff), maximal))
    try:
        daten = json.loads(abrufen(url, kennung, versuche=2).decode("utf-8"))
    except Exception:                                            # noqa: BLE001
        return []

    eintraege = []
    for d in daten.get("results", []):
        behoerden = ", ".join(a.get("name", "") for a in (d.get("agencies") or []))
        eintraege.append({
            "quelle": "Federal Register",
            "titel": text_saeubern(d.get("title", "")),
            "link": d.get("html_url", ""),
            "datum": d.get("publication_date", ""),
            "auszug": text_saeubern(d.get("abstract") or "")[:300],
            "behoerde": behoerden,
            "art": d.get("type", ""),
            "suchbegriff": begriff,
        })
    return eintraege


def stichworte_finden(text, stichworte):
    klein = (text or "").lower()
    treffer = []
    for wort in stichworte:
        if re.search(r"\b" + re.escape(wort.lower()) + r"\b", klein):
            treffer.append(wort)
    return treffer


def einordnen(eintrag, fuer_these, gegen_these):
    grundlage = eintrag["titel"] + " " + eintrag.get("auszug", "")
    treffer_gegen = stichworte_finden(grundlage, gegen_these)
    treffer_fuer = stichworte_finden(grundlage, fuer_these)
    if len(treffer_gegen) > len(treffer_fuer):
        eintrag["kategorie"] = "these_gefaehrdet"
        eintrag["treffer"] = treffer_gegen
    elif treffer_fuer:
        eintrag["kategorie"] = "these_bestaetigt"
        eintrag["treffer"] = treffer_fuer
    else:
        eintrag["kategorie"] = "neutral"
        eintrag["treffer"] = []
    return eintrag


# =========================================================== Claude-Einschaetzung

def claude_fragen(konfig, positionen, indikatoren, barometer, nachrichten,
                  regierung, blogs, sec):
    """
    Uebergibt die Tageslage an das claude-Kommandozeilenwerkzeug und laesst
    sie einordnen. Faellt still aus, wenn claude fehlt oder nicht antwortet.
    """
    einst = konfig.get("claude", {})
    if not einst.get("aktiv", True):
        return None

    befehl_name = einst.get("befehl", "claude")

    def zeilen(liste, anzahl, form):
        return "\n".join(form(x) for x in liste[:anzahl]) or "  (nichts)"

    relevant = [n for n in nachrichten if n["kategorie"] != "neutral"]

    prompt = """Du bist Analyst fuer ein privates Beobachtungs-Dashboard. Ein Anleger haelt zwei
gehebelte Short-Positionen (Faktor -2) auf die These: "Die westlichen KI-Investitionen
erzeugen kaum Gegenwert; China holt mit guenstigerer Hardware auf."

Positionen: Nvidia-Short (Chip-Seite) und Vertiv-Short (Rechenzentrums-Ausruestung).
Zeitlimit %s. Die Positionen verlieren durch taeglichen Reset auch bei Seitwaertslauf.

LAGE HEUTE (%s)

Barometer: %d/100 (%s) - hoch bedeutet, das Umfeld arbeitet fuer die Short-These.

Positionen:
%s

Abgeleitete Indikatoren:
%s

Schlagzeilen mit Stichworttreffern:
%s

Regierungsvorhaben:
%s

Veroeffentlichungen der KI-Labore:
%s

SEC-Meldungen (8-K):
%s

AUFGABE
Ordne die Lage ein. Achte besonders auf Dinge, die ein Stichwortfilter falsch
bewertet: Ironie, Ankuendigungen mit gegenteiliger Wirkung, Wiederholungen alter
Nachrichten, Effizienzdurchbrueche bei Modellen (die stuetzen die These, auch wenn
sie positiv klingen), und Zirkelfinanzierung (Chiphersteller finanzieren ihre
eigenen Kunden - das schwaecht die Umsatzqualitaet).

EIGENE RECHERCHE
Dir steht die Websuche zur Verfuegung. Nutze sie, wenn eine Schlagzeile ohne
Zusammenhang unklar bleibt, wenn du eine Vermutung belegen oder widerlegen willst,
oder wenn eine Zahl im Bericht nach einer Erklaerung verlangt. Ein bis drei gezielte
Suchen sind sinnvoll, mehr selten. Trage jeden Befund im Feld "recherche" ein - er
bekommt im Bericht einen eigenen Abschnitt und ist dort als deine eigene Recherche
gekennzeichnet, getrennt von den gemessenen Daten. Schreibe dort auch hin, wenn eine
Suche deine Vermutung NICHT bestaetigt hat; auch das ist ein Ergebnis.

FEHLENDE DATEN
Wenn dir etwas fehlt, um die Lage sauber zu beurteilen - eine Kennzahl, ein Ticker,
eine Quelle, ein Zeitraum -, dann sag es im Feld "datenwunsch". Der Nutzer kann den
Monitor entsprechend erweitern. Formuliere konkret, also nicht "mehr Daten zu China",
sondern etwa "Kurs von SMIC in Hongkong (0981.HK) als Wochenveraenderung".

STIL
Gutes, klares Deutsch: kurze Hauptsaetze, keine Aufzaehlungsfloskeln, kein Fettdruck,
keine Anglizismen wo ein deutsches Wort passt. Die Zusammenfassung soll erklaeren,
was der Bericht bedeutet und was heute besonders war - so, dass man nach drei Saetzen
Bescheid weiss.

Antworte NUR mit JSON in genau dieser Form, ohne Rahmen und ohne Vorrede:
{"zusammenfassung": ["Satz 1", "Satz 2", "Satz 3"],
 "these_status": "bestaetigt|neutral|gefaehrdet",
 "wichtigste_punkte": ["Punkt 1", "Punkt 2", "Punkt 3"],
 "uebersehen": "Was der Stichwortfilter falsch eingeordnet hat, oder leer",
 "recherche": [{"frage": "Was wolltest du wissen",
                "befund": "Was die Suche ergab, auch wenn sie nichts belegt",
                "folgerung": "Was das fuer die These bedeutet",
                "quelle": "Kurzname oder URL"}],
 "datenwunsch": ["Konkret benannte Kennzahl oder Quelle, die dir fehlt"],
 "handlungsbedarf": "keiner|beobachten|dringend",
 "begruendung": "1-2 Saetze, warum dieser Handlungsbedarf"}
""" % (
        konfig.get("zeitlimit_bis", "offen"),
        date.today().strftime("%d.%m.%Y"),
        barometer[0], barometer[1],
        zeilen(positionen, 5, lambda p: "  %s (%s): Basiswert %.2f, Tag %+.2f%%, "
               "Barriere-Puffer %s" % (
                   p["name"], p.get("wkn", ""), p["kurs"], p["tag_prozent"],
                   ("%.1f%%" % p["barriere_abstand"]) if p.get("barriere_abstand")
                   is not None else "?")),
        zeilen(indikatoren, 12, lambda i: "  %s: %.2f %s" % (
            i["name"], i["wert"], i["einheit"])),
        zeilen(relevant, 25, lambda n: "  [%s] %s (%s)" % (
            "GEGEN" if n["kategorie"] == "these_gefaehrdet" else "FUER",
            n["titel"][:150], n.get("quelle", ""))),
        zeilen(regierung, 8, lambda r: "  %s - %s (%s)" % (
            r["datum"], r["titel"][:150], r.get("behoerde", "")[:60])),
        zeilen(blogs, 10, lambda b: "  [%s] %s" % (b["quelle"], b["titel"][:150])),
        zeilen(sec, 8, lambda s: "  %s: %s" % (s.get("firma", ""), s["titel"][:120])),
    )

    # Nur Websuche und Seitenabruf sind erlaubt und damit vorab genehmigt.
    # Alles andere - Dateien, Shell - bleibt gesperrt, es kann also keine
    # Rueckfrage nach Berechtigungen auftauchen und der Lauf bleibt unbeaufsichtigt.
    werkzeuge = einst.get("werkzeuge", "WebSearch WebFetch")
    aufruf = [befehl_name, "-p", prompt, "--allowedTools", werkzeuge]
    if einst.get("modell"):
        aufruf += ["--model", einst["modell"]]

    # Laeuft der Monitor aus einer Claude-Code-Sitzung heraus, erbt der
    # Unterprozess deren Sitzungsvariablen und versucht mit dem falschen Token
    # zu arbeiten. Deshalb alles Claude-Eigene aus der Umgebung nehmen, damit
    # die CLI ihre eigenen Zugangsdaten aus dem Schluesselbund benutzt.
    umgebung = dict(os.environ)
    for schluessel in list(umgebung):
        if schluessel.startswith("CLAUDE") or schluessel.startswith("ANTHROPIC"):
            umgebung.pop(schluessel, None)

    try:
        lauf = subprocess.run(
            aufruf, capture_output=True, text=True,
            timeout=einst.get("zeitlimit_sekunden", 180),
            cwd=BASIS, env=umgebung)
    except FileNotFoundError:
        return {"fehler": "claude-Kommando nicht gefunden (%s)" % befehl_name}
    except subprocess.TimeoutExpired:
        return {"fehler": "claude hat nicht rechtzeitig geantwortet"}
    except Exception as f:                                       # noqa: BLE001
        return {"fehler": "claude-Aufruf fehlgeschlagen: %s" % f}

    ausgabe = (lauf.stdout or "").strip()
    if not ausgabe:
        meldung = (lauf.stderr or "").strip()[:200] or "leere Antwort"
        return {"fehler": "claude: %s" % meldung}

    # Anmeldeprobleme erkennen und klar benennen, statt sie als JSON-Fehler zu tarnen
    if re.search(r"(authenticat|401|OAuth|login|credit balance|rate limit)",
                 ausgabe, re.I):
        return {"fehler": "claude ist nicht angemeldet oder abgewiesen worden "
                          "(%s). Einmal 'claude' im Terminal starten und "
                          "anmelden, danach laeuft es auch unter launchd."
                          % ausgabe.strip().splitlines()[0][:120]}

    treffer = re.search(r"\{.*\}", ausgabe, re.S)
    if not treffer:
        return {"fehler": "claude-Antwort war kein JSON", "roh": ausgabe[:400]}
    try:
        return json.loads(treffer.group(0))
    except ValueError:
        return {"fehler": "claude-JSON nicht lesbar", "roh": ausgabe[:400]}


# =============================================================== Auffaelligkeiten

def alarme_sammeln(konfig, positionen, kurse, indikatoren, nachrichten,
                   regierung, sec):
    schwellen = konfig.get("schwellen", {})
    z_grenze = schwellen.get("z_score_auffaellig", 2.5)
    tag_grenze = schwellen.get("tagesbewegung_prozent", 5.0)
    b_warn = schwellen.get("barriere_warnung_prozent", 25.0)
    b_alarm = schwellen.get("barriere_alarm_prozent", 15.0)
    verlust = schwellen.get("verlust_warnung_prozent")
    gewinn = schwellen.get("gewinn_ziel_prozent")

    alarme = []

    for pos in positionen:
        name = "%s (%s)" % (pos["name"], pos.get("wkn", ""))
        abstand = pos.get("barriere_abstand")
        if abstand is not None:
            if abstand <= b_alarm:
                alarme.append(("alarm", "%s: nur noch %.1f%% bis zur Knock-Out-Barriere"
                               % (name, abstand)))
            elif abstand <= b_warn:
                alarme.append(("hinweis", "%s: Barriere-Puffer auf %.1f%% geschrumpft"
                               % (name, abstand)))

        pl = pos.get("schein_seit_einstieg")
        if pl is not None:
            if verlust is not None and pl <= -abs(verlust):
                alarme.append(("alarm", "%s: Verlustgrenze erreicht (%.1f%% im Schein)"
                               % (name, pl)))
            if gewinn is not None and pl >= abs(gewinn):
                alarme.append(("alarm", "%s: Gewinnziel erreicht (%.1f%% im Schein)"
                               % (name, pl)))

        if abs(pos.get("z_wert", 0.0)) >= z_grenze:
            richtung = "gegen" if pos["tag_prozent"] > 0 else "fuer"
            alarme.append(("alarm", "%s: ungewoehnliche Bewegung %+.2f%% (Z=%.1f), "
                                    "laeuft %s die These"
                           % (name, pos["tag_prozent"], pos["z_wert"], richtung)))

    for ticker, k in kurse.items():
        if k.get("fehler"):
            continue
        if abs(k.get("z_wert", 0)) >= z_grenze or abs(k.get("tag_prozent", 0)) >= tag_grenze:
            alarme.append(("hinweis", "%s: %+.2f%% (Z=%.1f)"
                           % (ticker, k["tag_prozent"], k["z_wert"])))

    vix = next((i for i in indikatoren if i["name"] == "VIX-Terminstruktur"), None)
    if vix and vix["wert"] > 1.0:
        alarme.append(("hinweis", "VIX-Terminstruktur in Backwardation (%.2f) - "
                                  "akuter Marktstress" % vix["wert"]))

    for n in nachrichten:
        if n["kategorie"] == "these_gefaehrdet":
            alarme.append(("alarm", "Gegen die These: %s" % n["titel"][:160]))
        elif n["kategorie"] == "these_bestaetigt":
            alarme.append(("hinweis", "Fuer die These: %s" % n["titel"][:160]))

    for r in regierung:
        if r.get("kategorie") in ("these_bestaetigt", "these_gefaehrdet"):
            alarme.append(("hinweis", "Regierung: %s" % r["titel"][:160]))

    for s in sec:
        alarme.append(("hinweis", "SEC-Meldung %s: %s"
                       % (s.get("firma", ""), s["titel"][:120])))

    heute = date.today()
    for termin in konfig.get("termine", []):
        try:
            tag = datetime.strptime(termin["datum"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        rest = (tag - heute).days
        if 0 <= rest <= 3:
            wort = {0: "heute", 1: "morgen"}.get(rest, "in %d Tagen" % rest)
            alarme.append(("alarm", "Termin %s: %s" % (wort, termin["was"])))

    return alarme


# =============================================================== Meldungen

def systemmeldung(titel, text, ton=None):
    sicher = re.sub(r'["\\]', "'", text)[:220]
    sicher_titel = re.sub(r'["\\]', "'", titel)[:60]
    befehl = 'display notification "%s" with title "%s"' % (sicher, sicher_titel)
    if ton:
        befehl += ' sound name "%s"' % ton
    try:
        subprocess.run(["osascript", "-e", befehl], check=False,
                       capture_output=True, timeout=10)
    except Exception:                                            # noqa: BLE001
        pass


def neue_alarme(alarme, zustand):
    heute = date.today().isoformat()
    gemeldet = zustand.get("gemeldet", {})
    if gemeldet.get("datum") != heute:
        gemeldet = {"datum": heute, "texte": []}
    frisch = []
    for stufe, text in alarme:
        if text not in gemeldet["texte"]:
            frisch.append((stufe, text))
            gemeldet["texte"].append(text)
    zustand["gemeldet"] = gemeldet
    return frisch


def melden(konfig, frisch):
    einst = konfig.get("benachrichtigung", {})
    if not einst.get("systemmeldung", True) or not frisch:
        return
    echte = [t for stufe, t in frisch if stufe == "alarm"]
    if not echte:
        return
    ton = einst.get("ton_alarm", "Basso") if einst.get("ton", True) else None
    if len(echte) == 1:
        systemmeldung("KI-Invest", echte[0], ton)
    else:
        systemmeldung("KI-Invest: %d Auffaelligkeiten" % len(echte), echte[0], ton)


# =============================================================== HTML-Bericht

def sparkline(werte, breite=110, hoehe=26):
    """Kleiner Verlaufsstrich als eingebettetes SVG."""
    if not werte or len(werte) < 2:
        return ""
    tief, hoch = min(werte), max(werte)
    spanne = (hoch - tief) or 1.0
    schritt = breite / float(len(werte) - 1)
    punkte = []
    for i, w in enumerate(werte):
        x = i * schritt
        y = hoehe - ((w - tief) / spanne) * (hoehe - 3) - 1.5
        punkte.append("%.1f,%.1f" % (x, y))
    steigend = werte[-1] >= werte[0]
    farbe = "var(--schlecht)" if steigend else "var(--gut)"
    return ('<svg class="spark" viewBox="0 0 %d %d" width="%d" height="%d" '
            'preserveAspectRatio="none"><polyline points="%s" fill="none" '
            'stroke="%s" stroke-width="1.5" stroke-linejoin="round"/></svg>'
            % (breite, hoehe, breite, hoehe, " ".join(punkte), farbe))


def barometer_verlauf_balken(verlauf):
    """Balkenreihe der letzten Barometer-Staende. Der Trend sagt mehr als der Stand."""
    if not verlauf or len(verlauf) < 2:
        return ""
    balken = []
    for i, eintrag in enumerate(verlauf[-24:]):
        wert = eintrag.get("wert", 50)
        hoehe = max(3, int(round(wert / 100.0 * 30)))
        klasse = "hoch" if wert >= 56 else ("tief" if wert <= 44 else "")
        if i == len(verlauf[-24:]) - 1:
            klasse += " jetzt"
        balken.append('<i class="%s" style="height:%dpx" title="%s: %d"></i>'
                      % (klasse.strip(), hoehe, eintrag.get("datum", ""), wert))
    return '<div class="verlauf">%s</div>' % "".join(balken)


def klasse_fuer(wert, invertiert=False):
    if wert is None:
        return "neutral"
    gut = (wert < 0) if not invertiert else (wert > 0)
    if abs(wert) < 0.15:
        return "neutral"
    return "gut" if gut else "schlecht"


def zahl(wert, nachkomma=2, suffix=""):
    if wert is None:
        return "&ndash;"
    return ("%+." + str(nachkomma) + "f%s") % (wert, suffix)


STIL = """
:root{--grund:#fff;--flaeche:#f7f8fa;--flaeche2:#eef0f3;--rand:#e2e5ea;
 --text:#16191d;--gedaempft:#68707b;--gut:#15803d;--schlecht:#b91c1c;
 --warn:#b45309;--akzent:#1d4ed8;--schatten:0 1px 2px rgba(0,0,0,.05)}
@media(prefers-color-scheme:dark){:root{--grund:#131619;--flaeche:#1b1f24;
 --flaeche2:#22272d;--rand:#2b3138;--text:#e9ebee;--gedaempft:#98a1ac;
 --gut:#4ade80;--schlecht:#f87171;--warn:#fbbf24;--akzent:#7aa2ff;
 --schatten:none}}
*{box-sizing:border-box}
body{margin:0;padding:28px 20px 60px;background:var(--grund);color:var(--text);
 font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.huelle{max-width:1080px;margin:0 auto}
h1{font-size:24px;margin:2px 0 2px;letter-spacing:-.01em}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.08em;
 color:var(--gedaempft);margin:34px 0 12px;font-weight:600}
h3{font-size:14px;margin:20px 0 8px;font-weight:600}
.kopf{color:var(--gedaempft);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:14px;background:var(--flaeche);
 border-radius:10px;overflow:hidden;box-shadow:var(--schatten)}
th{text-align:left;font-weight:600;font-size:11px;text-transform:uppercase;
 letter-spacing:.05em;color:var(--gedaempft);padding:9px 12px;
 border-bottom:1px solid var(--rand);white-space:nowrap}
td{padding:9px 12px;border-bottom:1px solid var(--rand);vertical-align:middle}
tr:last-child td{border-bottom:none}
td.z,th.z{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.gut{color:var(--gut)}.schlecht{color:var(--schlecht)}.warn{color:var(--warn)}
.neutral{color:var(--gedaempft)}
.karte{background:var(--flaeche);border:1px solid var(--rand);border-radius:10px;
 padding:13px 16px;margin-bottom:9px;box-shadow:var(--schatten)}
.karte.alarm{border-left:4px solid var(--schlecht)}
.karte.hinweis{border-left:4px solid var(--warn)}
.karte.ruhig{border-left:4px solid var(--gut)}
.klein{font-size:12px;color:var(--gedaempft)}
.spark{display:block}
.baro{display:flex;gap:18px;align-items:center;background:var(--flaeche);
 border:1px solid var(--rand);border-radius:12px;padding:18px 20px;
 margin:16px 0 4px;box-shadow:var(--schatten)}
.baro .wert{font-size:40px;font-weight:650;line-height:1;letter-spacing:-.02em;
 font-variant-numeric:tabular-nums}
.baro .rest{flex:1}
.skala{height:9px;border-radius:5px;margin:9px 0 6px;position:relative;
 background:linear-gradient(90deg,var(--schlecht),var(--flaeche2) 45%,
 var(--flaeche2) 55%,var(--gut))}
.skala i{position:absolute;top:-3px;width:3px;height:15px;border-radius:2px;
 background:var(--text)}
.gitter{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
 gap:9px}
.ind{background:var(--flaeche);border:1px solid var(--rand);border-radius:10px;
 padding:12px 14px;box-shadow:var(--schatten)}
.ind .oben{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.ind .name{font-weight:600;font-size:13.5px}
.ind .zahl{font-variant-numeric:tabular-nums;font-size:17px;font-weight:600}
.ind .txt{font-size:12px;color:var(--gedaempft);margin-top:6px;line-height:1.45}
.marke{display:inline-block;font-size:10.5px;text-transform:uppercase;
 letter-spacing:.05em;padding:2px 7px;border-radius:20px;
 background:var(--flaeche2);color:var(--gedaempft);font-weight:600}
.marke.gut{color:var(--gut)}.marke.schlecht{color:var(--schlecht)}
a{color:var(--akzent);text-decoration:none}a:hover{text-decoration:underline}
ul.liste{list-style:none;padding:0;margin:0}
ul.liste li{padding:9px 0;border-bottom:1px solid var(--rand)}
ul.liste li:last-child{border-bottom:none}
.fuss{border:1px solid var(--rand);border-radius:10px;padding:13px 16px;
 color:var(--gedaempft);font-size:12.5px;margin-top:32px;line-height:1.5}
.claude{background:var(--flaeche);border:1px solid var(--akzent);border-radius:12px;
 padding:16px 18px;box-shadow:var(--schatten)}
.claude .lage{font-size:15px;margin-bottom:10px}
.fazit{background:var(--flaeche);border:1px solid var(--rand);border-radius:12px;
 padding:16px 20px;margin-bottom:4px;box-shadow:var(--schatten);
 font-size:15.5px;line-height:1.62}
.fazit p{margin:0 0 9px}
.fazit p:last-child{margin-bottom:0}
.fazit b{font-weight:640}
.fazit .quelle{font-size:11px;text-transform:uppercase;letter-spacing:.06em;
 color:var(--gedaempft);border-top:1px solid var(--rand);
 padding-top:11px;margin:13px 0 10px;font-weight:600}
.fazit p.gemessen{font-size:14px;color:var(--gedaempft);line-height:1.55}
.fazit p.gemessen b{color:var(--text);font-weight:600}
.warnfeld{background:var(--flaeche2);border:1px dashed var(--warn);
 border-radius:10px;padding:11px 15px;margin-bottom:10px;font-size:12.5px;
 color:var(--gedaempft);line-height:1.5}
.karte.recherche{border-left:4px solid var(--warn);background:var(--flaeche)}
.karte.recherche .frage{font-weight:600;font-size:13px;color:var(--warn)}
.tabelle{overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:10px}
.tabelle table{min-width:640px}
.neu{display:inline-block;font-size:9.5px;font-weight:700;letter-spacing:.06em;
 text-transform:uppercase;background:var(--akzent);color:#fff;border-radius:3px;
 padding:1px 5px;margin-right:6px;vertical-align:1px}
.verlauf{display:flex;align-items:flex-end;gap:2px;height:30px;margin-top:2px}
.verlauf i{width:5px;border-radius:1px;background:var(--rand);display:block}
.verlauf i.hoch{background:var(--gut)}
.verlauf i.tief{background:var(--schlecht)}
.verlauf i.jetzt{outline:1.5px solid var(--text);outline-offset:1px}
@media(max-width:640px){
 body{padding:18px 12px 50px}
 .baro{flex-wrap:wrap;gap:12px}
 .baro .wert{font-size:34px}
 .gitter{grid-template-columns:1fr}
}
"""


def bericht_bauen(konfig, positionen, kurse, gruppen_ansicht, indikatoren,
                  barometer, nachrichten, regierung, blogs, sec, alarme,
                  claude_urteil, fehler, zusammenfassung=None,
                  barometer_verlauf=None):
    jetzt = datetime.now()
    heute = date.today()
    t = []

    limit_text = ""
    if konfig.get("zeitlimit_bis"):
        try:
            limit = datetime.strptime(konfig["zeitlimit_bis"], "%Y-%m-%d").date()
            limit_text = " &middot; Zeitlimit %s, noch %d Tage" % (
                limit.strftime("%d.%m."), (limit - heute).days)
        except ValueError:
            pass

    t.append('<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1">'
             '<title>KI-Invest Monitor</title><style>%s</style></head>'
             '<body><div class="huelle">' % STIL)

    t.append('<div class="kopf">%s%s</div><h1>KI-Invest Monitor</h1>'
             % (jetzt.strftime("%A, %d.%m.%Y, %H:%M Uhr"), limit_text))

    # ---- Barometer
    wert, lage = barometer
    balken = barometer_verlauf_balken(barometer_verlauf)
    trend = ""
    if barometer_verlauf and len(barometer_verlauf) >= 2:
        vorher = barometer_verlauf[-2].get("wert")
        if vorher is not None and vorher != wert:
            trend = ' <span class="klein">(zuvor %d)</span>' % vorher
    t.append('<div class="baro"><div class="wert %s">%d</div><div class="rest">'
             '<div style="font-weight:600">%s%s</div>'
             '<div class="skala"><i style="left:calc(%d%% - 1px)"></i></div>'
             '<div class="klein">0 = Umfeld arbeitet gegen die Short-These, '
             '100 = dafuer. Verdichtet Relativstaerken, Volatilitaetsstruktur, '
             'Kreditumfeld und die Nachrichtenbilanz.</div></div>%s</div>'
             % ("gut" if wert >= 56 else ("schlecht" if wert <= 44 else "neutral"),
                wert, lage, trend, wert,
                ('<div style="text-align:right"><div class="klein" '
                 'style="margin-bottom:3px">Verlauf</div>%s</div>' % balken)
                if balken else ""))

    # ---- Zusammenfassung in Worten
    claude_saetze = []
    if claude_urteil and not claude_urteil.get("fehler"):
        claude_saetze = claude_urteil.get("zusammenfassung") or []

    if claude_saetze or zusammenfassung:
        t.append('<div class="fazit">')
        if claude_saetze:
            for satz in claude_saetze:
                t.append("<p>%s</p>" % html_schuetzen(satz))
            t.append('<div class="quelle">Einordnung von Claude &middot; '
                     'die gemessenen Werte darunter</div>')
        for satz in (zusammenfassung or []):
            t.append('<p class="%s">%s</p>'
                     % ("gemessen" if claude_saetze else "", satz))
        t.append("</div>")

    # ---- Claude
    if claude_urteil:
        t.append("<h2>Einordnung</h2>")
        if claude_urteil.get("fehler"):
            t.append('<div class="karte hinweis klein">Claude-Einschaetzung nicht '
                     'verfuegbar: %s<br>Der Bericht laeuft ohne sie weiter &ndash; '
                     'die Zusammenfassung oben stammt dann aus den Messwerten.</div>'
                     % html_schuetzen(claude_urteil["fehler"]))
        else:
            status = claude_urteil.get("these_status", "neutral")
            bedarf = claude_urteil.get("handlungsbedarf", "keiner")
            klasse = {"bestaetigt": "gut", "gefaehrdet": "schlecht"}.get(status, "neutral")
            t.append('<div class="claude">')
            t.append('<div style="margin:0 0 10px"><span class="marke %s">These %s</span> '
                     '<span class="marke %s">Handlungsbedarf: %s</span></div>'
                     % (klasse, html_schuetzen(status),
                        "schlecht" if bedarf == "dringend" else "neutral",
                        html_schuetzen(bedarf)))
            punkte = claude_urteil.get("wichtigste_punkte") or []
            if punkte:
                t.append('<ul class="liste">')
                for p in punkte:
                    t.append("<li>%s</li>" % html_schuetzen(p))
                t.append("</ul>")
            if claude_urteil.get("uebersehen"):
                t.append('<div class="klein" style="margin-top:10px"><b>Vom '
                         'Stichwortfilter falsch eingeordnet:</b> %s</div>'
                         % html_schuetzen(claude_urteil["uebersehen"]))
            if claude_urteil.get("begruendung"):
                t.append('<div class="klein" style="margin-top:6px">%s</div>'
                         % html_schuetzen(claude_urteil["begruendung"]))
            t.append("</div>")

        # ---- Eigene Recherche und Datenwuensche
        recherche = (claude_urteil.get("recherche") or []
                     if not claude_urteil.get("fehler") else [])
        wuensche = (claude_urteil.get("datenwunsch") or []
                    if not claude_urteil.get("fehler") else [])

        if recherche:
            t.append("<h2>Eigene Recherche von Claude</h2>")
            t.append('<div class="warnfeld">Dieser Abschnitt stammt <b>nicht</b> aus '
                     'den ueberwachten Quellen. Claude hat hier auf eigene Faust im '
                     'Netz gesucht, um eine Vermutung zu pruefen. Die Befunde sind '
                     'ungeprueft und koennen falsch sein &ndash; behandle sie als '
                     'Anhaltspunkt, nicht als Messwert.</div>')
            for r in recherche:
                if not isinstance(r, dict):
                    t.append('<div class="karte recherche">%s</div>' % html_schuetzen(r))
                    continue
                t.append('<div class="karte recherche">'
                         '<div class="frage">%s</div>'
                         '<div style="margin:7px 0">%s</div>' % (
                             html_schuetzen(r.get("frage", "")),
                             html_schuetzen(r.get("befund", ""))))
                if r.get("folgerung"):
                    t.append('<div class="klein"><b>Folgerung:</b> %s</div>'
                             % html_schuetzen(r["folgerung"]))
                if r.get("quelle"):
                    quelle = str(r["quelle"])
                    if quelle.startswith("http"):
                        t.append('<div class="klein">Quelle: <a href="%s">%s</a></div>'
                                 % (html_schuetzen(quelle), html_schuetzen(quelle[:90])))
                    else:
                        t.append('<div class="klein">Quelle: %s</div>'
                                 % html_schuetzen(quelle))
                t.append("</div>")

        if wuensche:
            t.append("<h2>Was Claude fehlt</h2>")
            t.append('<div class="klein" style="margin-bottom:8px">Vorschlaege zur '
                     'Erweiterung des Monitors &ndash; umsetzbar in '
                     '<code>config.json</code>.</div><ul class="liste">')
            for w in wuensche:
                t.append("<li>%s</li>" % html_schuetzen(w))
            t.append("</ul>")

    # ---- Auffaelligkeiten
    t.append("<h2>Auffaelligkeiten</h2>")
    echte = [a for a in alarme if a[0] == "alarm"]
    hinweise = [a for a in alarme if a[0] == "hinweis"]
    if not alarme:
        t.append('<div class="karte ruhig">Nichts Ungewoehnliches. Alle Werte '
                 'innerhalb der ueblichen Schwankung.</div>')
    for _, text in echte[:14]:
        t.append('<div class="karte alarm">%s</div>' % html_schuetzen(text))
    if hinweise:
        t.append('<details><summary class="klein" style="cursor:pointer;'
                 'margin:6px 0 10px">%d weitere Hinweise</summary>' % len(hinweise))
        for _, text in hinweise[:40]:
            t.append('<div class="karte hinweis klein">%s</div>' % html_schuetzen(text))
        t.append("</details>")

    # ---- Positionen
    t.append("<h2>Positionen</h2><div class='tabelle'><table><tr><th>Position</th><th>WKN</th>"
             "<th>Verlauf 3 Monate</th><th class='z'>Kurs</th><th class='z'>Tag</th>"
             "<th class='z'>Schein Tag</th><th class='z'>seit Einstieg</th>"
             "<th class='z'>Puffer</th><th class='z'>Drag</th></tr>")
    for p in positionen:
        puffer = p.get("barriere_abstand")
        pk = "neutral"
        if puffer is not None:
            pk = "schlecht" if puffer < 20 else ("warn" if puffer < 30 else "gut")
        t.append("<tr><td>%s</td><td class='klein'>%s</td><td>%s</td>"
                 "<td class='z'>%.2f</td><td class='z %s'>%s</td>"
                 "<td class='z %s'>%s</td><td class='z %s'>%s</td>"
                 "<td class='z %s'>%s</td><td class='z neutral'>%s</td></tr>" % (
                     p["name"], p.get("wkn", ""), sparkline(p.get("verlauf")),
                     p["kurs"],
                     klasse_fuer(p["tag_prozent"]), zahl(p["tag_prozent"], 2, "%"),
                     klasse_fuer(p["schein_tag_prozent"], True),
                     zahl(p["schein_tag_prozent"], 2, "%"),
                     klasse_fuer(p.get("schein_seit_einstieg"), True),
                     zahl(p.get("schein_seit_einstieg"), 1, "%"),
                     pk, ("%.1f%%" % puffer) if puffer is not None else "&ndash;",
                     zahl(p.get("drag_prozent"), 1, "%")))
    t.append("</table></div>")
    t.append('<div class="klein" style="margin-top:8px">Schein-Werte sind '
             'Naeherungen (Basiswert-Bewegung mal Faktor, ohne Produktkosten). '
             'Die Reset-Barriere wandert taeglich &ndash; Stand laut Konfiguration: '
             '%s. Einstiegskurse in <code>config.json</code> eintragen, damit die '
             'Spalten "seit Einstieg" und "Drag" rechnen.</div>'
             % ", ".join("%s&nbsp;%s" % (p.get("wkn", ""), p.get("barriere_stand", "?"))
                         for p in positionen))

    # Veraltete Barrieren sind gefaehrlich: der angezeigte Puffer stimmt dann nicht.
    veraltet = []
    for p in positionen:
        try:
            stand = datetime.strptime(p.get("barriere_stand", ""), "%Y-%m-%d").date()
        except ValueError:
            continue
        alter = (heute - stand).days
        if alter > 5:
            veraltet.append("%s (%d Tage)" % (p.get("wkn", ""), alter))
    if veraltet:
        t.append('<div class="karte hinweis klein" style="margin-top:8px">'
                 'Die hinterlegte Reset-Barriere ist veraltet: %s. Sie wandert '
                 'taeglich mit, der oben gezeigte Puffer ist daher zu optimistisch '
                 'oder zu pessimistisch. Aktuellen Wert im ING-Depot oder auf '
                 'onvista ablesen und in <code>config.json</code> eintragen.</div>'
                 % ", ".join(veraltet))

    # ---- Indikatoren
    t.append("<h2>Abgeleitete Indikatoren</h2><div class='gitter'>")
    for i in indikatoren:
        nk = i.get("nachkomma", 2)
        marke = {"gut": "fuer die These", "schlecht": "gegen die These"}.get(
            i["these"], "neutral")
        t.append('<div class="ind"><div class="oben"><span class="name">%s</span>'
                 '<span class="zahl %s">%s</span></div>'
                 '<div class="klein">%s &middot; <span class="marke %s">%s</span></div>'
                 '<div class="txt">%s</div></div>' % (
                     i["name"],
                     "gut" if i["these"] == "gut" else ("schlecht" if i["these"] == "schlecht" else "neutral"),
                     ("%." + str(nk) + "f") % i["wert"],
                     i["einheit"], i["these"], marke, i["erklaerung"]))
    t.append("</div>")

    # ---- Gruppen
    t.append("<h2>Marktumfeld nach Gruppen</h2>")
    for gruppe, info in gruppen_ansicht:
        t.append("<h3>%s</h3>" % gruppe)
        if info.get("rolle"):
            t.append('<div class="klein" style="margin-bottom:7px">%s</div>' % info["rolle"])
        t.append("<div class='tabelle'><table><tr><th>Ticker</th><th>Verlauf</th><th class='z'>Kurs</th>"
                 "<th class='z'>Tag</th><th class='z'>Woche</th><th class='z'>Monat</th>"
                 "<th class='z'>Quartal</th><th class='z'>vom Hoch</th>"
                 "<th class='z'>Vola</th><th class='z'>Z</th></tr>")
        for w in info["werte"]:
            if w.get("fehler"):
                t.append("<tr><td>%s</td><td colspan='9' class='klein'>%s</td></tr>"
                         % (w["ticker"], html_schuetzen(w["fehler"])))
                continue
            t.append("<tr><td>%s</td><td>%s</td><td class='z'>%.2f</td>"
                     "<td class='z %s'>%s</td><td class='z %s'>%s</td>"
                     "<td class='z %s'>%s</td><td class='z %s'>%s</td>"
                     "<td class='z neutral'>%s</td><td class='z neutral'>%.0f%%</td>"
                     "<td class='z %s'>%.1f</td></tr>" % (
                         w["ticker"], sparkline(w.get("verlauf"), 70, 20), w["kurs"],
                         klasse_fuer(w["tag_prozent"]), zahl(w["tag_prozent"], 2, "%"),
                         klasse_fuer(w.get("woche_prozent")), zahl(w.get("woche_prozent"), 1, "%"),
                         klasse_fuer(w.get("monat_prozent")), zahl(w.get("monat_prozent"), 1, "%"),
                         klasse_fuer(w.get("quartal_prozent")), zahl(w.get("quartal_prozent"), 1, "%"),
                         ("%.0f%%" % w["abstand_hoch"]) if w.get("abstand_hoch") is not None else "&ndash;",
                         w["sigma_jahr"],
                         "schlecht" if abs(w["z_wert"]) >= 2.5 else "neutral", w["z_wert"]))
        t.append("</table></div>")

    # ---- Nachrichten
    t.append("<h2>Nachrichten mit Bezug zur These</h2>")
    relevant = [n for n in nachrichten if n["kategorie"] != "neutral"]
    if not relevant:
        t.append('<div class="karte klein">Keine Schlagzeile mit passenden '
                 'Stichworten gefunden.</div>')
    neue_anzahl = sum(1 for n in relevant if n.get("neu"))
    if neue_anzahl:
        t.append('<div class="klein" style="margin-bottom:8px"><span class="neu">neu</span>'
                 ' kennzeichnet die %d Meldungen, die seit dem letzten Bericht '
                 'dazugekommen sind.</div>' % neue_anzahl)
    relevant.sort(key=lambda n: (not n.get("neu"), n["kategorie"] != "these_gefaehrdet"))
    for n in relevant[:30]:
        stufe = "alarm" if n["kategorie"] == "these_gefaehrdet" else "hinweis"
        richtung = ("spricht <b>gegen</b> die These" if n["kategorie"] == "these_gefaehrdet"
                    else "spricht <b>fuer</b> die These")
        if n.get("neu"):
            t.append('<div class="karte %s"><span class="neu">neu</span>'
                     '<a href="%s">%s</a><div class="klein">' % (
                         stufe, html_schuetzen(n.get("link", "")),
                         html_schuetzen(n["titel"])))
            t.append('%s &middot; %s &middot; %s &middot; Stichworte: %s</div></div>'
                     % (html_schuetzen(n.get("quelle", "")),
                        html_schuetzen(n.get("thema", "")), richtung,
                        html_schuetzen(", ".join(n["treffer"]))))
            continue
        t.append('<div class="karte %s"><a href="%s">%s</a><div class="klein">'
                 '%s &middot; %s &middot; %s &middot; Stichworte: %s</div></div>'
                 % (stufe, html_schuetzen(n.get("link", "")),
                    html_schuetzen(n["titel"]), html_schuetzen(n.get("quelle", "")),
                    html_schuetzen(n.get("thema", "")), richtung,
                    html_schuetzen(", ".join(n["treffer"]))))

    # ---- Regierung
    t.append("<h2>Regierungsvorhaben (Federal Register)</h2>")
    if not regierung:
        t.append('<div class="karte klein">Keine neuen Vorhaben zu den '
                 'hinterlegten Suchbegriffen.</div>')
    for r in regierung[:12]:
        t.append('<div class="karte"><a href="%s">%s</a><div class="klein">'
                 '%s &middot; %s &middot; %s</div></div>'
                 % (html_schuetzen(r["link"]), html_schuetzen(r["titel"]),
                    html_schuetzen(r["datum"]), html_schuetzen(r.get("art", "")),
                    html_schuetzen(r.get("behoerde", ""))))

    # ---- KI-Labore
    t.append("<h2>Veroeffentlichungen der KI-Labore und Branche</h2>")
    t.append('<div class="klein" style="margin-bottom:8px">Effizienzdurchbrueche '
             'sind der staerkste Ausloeser fuer die These &ndash; der DeepSeek-Moment '
             'begann mit einer Modellveroeffentlichung, nicht mit einer Kurszahl.</div>')
    if not blogs:
        t.append('<div class="karte klein">Keine neuen Beitraege abrufbar.</div>')
    for b in blogs[:16]:
        stufe = ("hinweis" if b.get("kategorie") == "these_bestaetigt"
                 else ("alarm" if b.get("kategorie") == "these_gefaehrdet" else ""))
        t.append('<div class="karte %s"><a href="%s">%s</a><div class="klein">'
                 '%s &middot; %s</div></div>'
                 % (stufe, html_schuetzen(b.get("link", "")),
                    html_schuetzen(b["titel"]), html_schuetzen(b["quelle"]),
                    html_schuetzen(b.get("datum", ""))))

    # ---- SEC
    t.append("<h2>SEC-Meldungen (8-K)</h2>")
    t.append('<div class="klein" style="margin-bottom:8px">Ad-hoc-Pflichtmeldungen. '
             'Hier taucht Wesentliches auf, bevor es in den Nachrichten steht.</div>')
    if not sec:
        t.append('<div class="karte klein">Keine aktuellen 8-K-Meldungen.</div>')
    for s in sec[:12]:
        t.append('<div class="karte"><a href="%s">%s</a><div class="klein">'
                 '%s &middot; %s</div></div>'
                 % (html_schuetzen(s.get("link", "")), html_schuetzen(s["titel"]),
                    html_schuetzen(s.get("firma", "")), html_schuetzen(s.get("datum", ""))))

    # ---- Termine
    t.append("<h2>Termine</h2><ul class='liste'>")
    for termin in sorted(konfig.get("termine", []), key=lambda x: x.get("datum", "")):
        try:
            tag = datetime.strptime(termin["datum"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        rest = (tag - heute).days
        wann = ("vorbei" if rest < 0 else "<b>heute</b>" if rest == 0
                else "morgen" if rest == 1 else "in %d Tagen" % rest)
        t.append("<li>%s &middot; %s &mdash; %s</li>"
                 % (tag.strftime("%d.%m.%Y"), html_schuetzen(termin["was"]), wann))
    t.append("</ul>")

    if fehler:
        t.append("<h2>Abruf-Probleme</h2>")
        for f in fehler[:15]:
            t.append('<div class="karte hinweis klein">%s</div>' % html_schuetzen(f))

    t.append('<div class="fuss">Automatisch erzeugt vom KI-Invest-Monitor. '
             'Kursdaten koennen verzoegert sein und dienen der Beobachtung, nicht '
             'der Orderausfuehrung. Die Stichwort-Einordnung ist eine grobe '
             'Vorsortierung &ndash; die Bewertung bleibt bei dir. '
             'Konfiguration: <code>monitor/config.json</code>.</div>')
    t.append("</div></body></html>")
    return "\n".join(t)


# =============================================================== Sammellauf

def alles_sammeln(konfig, mit_claude=True, vorheriges_barometer=None):
    kennung = konfig.get("kennung", STANDARD_KENNUNG)
    fehler = []
    kurse = {}

    def hole(ticker):
        if ticker not in kurse:
            try:
                kurse[ticker] = kurse_holen(ticker, kennung)
            except Exception as f:                               # noqa: BLE001
                kurse[ticker] = {"ticker": ticker, "fehler": str(f)}
                fehler.append("Kurs %s: %s" % (ticker, f))
        return kurse[ticker]

    gruppen = konfig.get("gruppen", {})

    # Kurse
    for info in gruppen.values():
        for ticker in info.get("ticker", []):
            hole(ticker)

    positionen = []
    for pos in konfig.get("positionen", []):
        daten = hole(pos["ticker"])
        if daten.get("fehler"):
            fehler.append("Position %s ohne Kurs" % pos.get("name", "?"))
            continue
        positionen.append(position_auswerten(pos, daten))

    gute_kurse = {k: v for k, v in kurse.items() if not v.get("fehler")}
    indikatoren = indikatoren_bauen(gute_kurse, gruppen)

    gruppen_ansicht = []
    for name, info in gruppen.items():
        gruppen_ansicht.append((name, {
            "rolle": info.get("rolle", ""),
            "werte": [kurse[t] for t in info.get("ticker", []) if t in kurse],
        }))

    # Nachrichten
    fuer_these = konfig.get("news_stichworte_these_bestaetigt", [])
    gegen_these = konfig.get("news_stichworte_these_gefaehrdet", [])
    nachrichten, gesehen = [], set()

    def aufnehmen(eintraege, thema=""):
        for e in eintraege:
            schluessel = e["titel"][:110].lower()
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            e["thema"] = thema
            nachrichten.append(einordnen(e, fuer_these, gegen_these))

    for ticker in konfig.get("news_ticker", []):
        aufnehmen(yahoo_news(ticker, kennung), "Ticker " + ticker)
    for suche in konfig.get("news_suchen", []):
        aufnehmen(google_news(suche["query"], kennung), suche["thema"])

    # Regierung
    regierung = []
    for begriff in konfig.get("regierung_suchen", []):
        for d in regierung_dokumente(begriff, kennung):
            if d["titel"][:110].lower() in gesehen:
                continue
            gesehen.add(d["titel"][:110].lower())
            regierung.append(einordnen(d, fuer_these, gegen_these))

    # KI-Labore und Branche
    blogs = []
    for eintrag in konfig.get("blogs", []):
        for b in rss_lesen(eintrag["url"], kennung, eintrag["quelle"], 8):
            blogs.append(einordnen(b, fuer_these, gegen_these))
    if not blogs:
        fehler.append("Keine Blog-Beitraege abrufbar")

    # SEC
    sec = []
    for firma in konfig.get("sec_firmen", []):
        sec.extend(sec_meldungen(firma["cik"], firma["name"], kennung))

    barometer = barometer_rechnen(indikatoren, nachrichten)

    zusammenfassung = zusammenfassung_bauen(
        positionen, indikatoren, barometer, nachrichten, regierung, sec, blogs,
        konfig, vorheriges_barometer)

    claude_urteil = None
    if mit_claude:
        claude_urteil = claude_fragen(konfig, positionen, indikatoren, barometer,
                                      nachrichten, regierung, blogs, sec)

    alarme = alarme_sammeln(konfig, positionen, gute_kurse, indikatoren,
                            nachrichten, regierung, sec)

    if claude_urteil and not claude_urteil.get("fehler"):
        if claude_urteil.get("handlungsbedarf") == "dringend":
            alarme.insert(0, ("alarm", "Claude: %s"
                              % claude_urteil.get("begruendung", "dringender Handlungsbedarf")))

    return {
        "positionen": positionen, "kurse": kurse, "gruppen": gruppen_ansicht,
        "indikatoren": indikatoren, "barometer": barometer,
        "zusammenfassung": zusammenfassung,
        "nachrichten": nachrichten, "regierung": regierung, "blogs": blogs,
        "sec": sec, "alarme": alarme, "claude": claude_urteil, "fehler": fehler,
    }


def neuheiten_markieren(nachrichten, zustand):
    """Kennzeichnet Meldungen, die seit dem letzten Bericht dazugekommen sind."""
    bekannt = set(zustand.get("gesehene_meldungen", []))
    aktuell = []
    for n in nachrichten:
        schluessel = n["titel"][:110].lower()
        aktuell.append(schluessel)
        n["neu"] = bool(bekannt) and schluessel not in bekannt
    # Nur die letzten Laeufe behalten, damit die Datei nicht waechst
    zustand["gesehene_meldungen"] = list(dict.fromkeys(
        aktuell + list(bekannt)))[:800]


def bericht_schreiben(konfig, d, oeffnen, barometer_verlauf=None):
    html = bericht_bauen(konfig, d["positionen"], d["kurse"], d["gruppen"],
                         d["indikatoren"], d["barometer"], d["nachrichten"],
                         d["regierung"], d["blogs"], d["sec"], d["alarme"],
                         d.get("claude"), d["fehler"], d.get("zusammenfassung"),
                         barometer_verlauf)
    with open(BERICHT_PFAD, "w") as f:
        f.write(html)
    if oeffnen:
        subprocess.run(["open", BERICHT_PFAD], check=False)


def nur_claude_neu(konfig, oeffnen):
    """
    Fragt allein die Claude-Einordnung neu an und baut den Bericht damit neu.
    Nutzt die zuletzt gesammelten Daten - kein erneuter Abruf von Kursen,
    Nachrichten, SEC-Meldungen und Regierungsvorhaben.
    """
    d = json_laden(DATEN_PFAD, None)
    if d is None:
        log_schreiben("FEHLER: keine gespeicherten Daten. Erst --report oder "
                      "--test laufen lassen.")
        return 1

    alter = d.get("gesammelt_am", "unbekannt")
    d["claude"] = claude_fragen(konfig, d["positionen"], d["indikatoren"],
                                d["barometer"], d["nachrichten"], d["regierung"],
                                d["blogs"], d["sec"])
    zustand = json_laden(STATE_PFAD, {})
    bericht_schreiben(konfig, d, oeffnen,
                      zustand.get("barometer_verlauf"))

    if d["claude"] and d["claude"].get("fehler"):
        log_schreiben("nur-claude: fehlgeschlagen (%s), Daten von %s"
                      % (d["claude"]["fehler"][:80], alter))
    else:
        log_schreiben("nur-claude: neue Einordnung, Daten von %s" % alter)
    return 0


def main():
    modus = ("nur-claude" if "--nur-claude" in sys.argv
             else "report" if "--report" in sys.argv
             else "test" if "--test" in sys.argv else "watch")
    mit_claude = "--ohne-claude" not in sys.argv and modus != "watch"

    konfig = json_laden(CONFIG_PFAD, None)
    if konfig is None:
        log_schreiben("FEHLER: config.json nicht lesbar")
        systemmeldung("KI-Invest", "config.json fehlt oder ist fehlerhaft", "Basso")
        return 1

    if modus == "nur-claude":
        return nur_claude_neu(konfig, oeffnen="--test" not in sys.argv)

    zustand = json_laden(STATE_PFAD, {})

    try:
        d = alles_sammeln(konfig, mit_claude=mit_claude,
                          vorheriges_barometer=zustand.get("letztes_barometer"))
    except Exception as f:                                       # noqa: BLE001
        log_schreiben("Unerwarteter Fehler: %s" % f)
        zustand["fehler_in_folge"] = zustand.get("fehler_in_folge", 0) + 1
        if zustand["fehler_in_folge"] in (3, 10):
            systemmeldung("KI-Invest", "Datenabruf faellt seit %d Laeufen aus"
                          % zustand["fehler_in_folge"], "Basso")
        json_speichern(STATE_PFAD, zustand)
        return 1

    zustand["fehler_in_folge"] = 0 if len(d["fehler"]) < 5 else \
        zustand.get("fehler_in_folge", 0) + 1

    if modus == "watch":
        frisch = neue_alarme(d["alarme"], zustand)
        melden(konfig, frisch)
        log_schreiben("watch: Barometer %d, %d Auffaelligkeiten (%d neu), "
                      "%d Abrufprobleme" % (d["barometer"][0], len(d["alarme"]),
                                            len(frisch), len(d["fehler"])))
    else:
        verlauf = zustand.get("barometer_verlauf", [])
        verlauf.append({"datum": date.today().strftime("%d.%m."),
                        "wert": d["barometer"][0]})
        zustand["barometer_verlauf"] = verlauf[-40:]
        neuheiten_markieren(d["nachrichten"], zustand)
        bericht_schreiben(konfig, d, oeffnen=(modus == "report"),
                          barometer_verlauf=zustand["barometer_verlauf"])
        # Datenstand sichern, damit --nur-claude ohne erneuten Abruf arbeiten kann
        d["gesammelt_am"] = datetime.now().strftime("%d.%m.%Y %H:%M")
        try:
            json_speichern(DATEN_PFAD, d)
        except (TypeError, ValueError) as f:
            log_schreiben("Hinweis: Daten nicht sicherbar (%s)" % f)
        zustand["gemeldet"] = {"datum": date.today().isoformat(), "texte": []}
        log_schreiben("%s: Barometer %d, %d Auffaelligkeiten, %d Nachrichten, "
                      "%d Abrufprobleme -> %s"
                      % (modus, d["barometer"][0], len(d["alarme"]),
                         len(d["nachrichten"]), len(d["fehler"]), BERICHT_PFAD))

    zustand["letzter_lauf"] = datetime.now().isoformat(timespec="seconds")
    zustand["letztes_barometer"] = d["barometer"][0]
    json_speichern(STATE_PFAD, zustand)
    return 0


if __name__ == "__main__":
    sys.exit(main())
