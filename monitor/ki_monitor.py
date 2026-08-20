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
from datetime import datetime, date, timedelta
from math import log, sqrt, exp
from statistics import pstdev, mean

BASIS = os.path.dirname(os.path.abspath(__file__))
CONFIG_PFAD = os.path.join(BASIS, "config.json")
STATE_PFAD = os.path.join(BASIS, "state.json")
DATEN_PFAD = os.path.join(BASIS, "daten.json")
CLAUDE_PFAD = os.path.join(BASIS, "claude.json")
TOKEN_PFAD = os.path.join(BASIS, "tokenpreise.json")
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
    # default=str wandelt Datumsobjekte in ISO-Text, damit die Kursreihen
    # und der Wertverlauf sicherungsfaehig bleiben.
    with open(pfad, "w") as f:
        json.dump(daten, f, indent=2, ensure_ascii=False, default=str)


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
    stempel = block.get("timestamp") or []
    paare = [(t, k) for t, k in zip(stempel, reihe) if k is not None]
    schluss = [k for _, k in paare]
    datumsreihe = [date.fromtimestamp(t) for t, _ in paare]
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
        "verlauf_datum": datumsreihe[-60:],
        "waehrung": meta.get("currency", ""),
    }


def scheinkurs_holen(isin, kennung):
    """
    Holt Geld- und Briefkurs des Zertifikats.

    Quelle ist wallstreet-online, weil dort die Quotierung des Emittenten steht -
    also genau der Kurs, den ING im Direkthandel stellt. Gegen onvista geprueft:
    identisch auf den Cent. Die Emittentenseite selbst liefert nur einen
    WebSocket-Strom, onvista und die Boerse Frankfurt sperren Skripte aus.
    """
    url = "https://www.wallstreet-online.de/zertifikat/%s" % isin.lower()
    try:
        rohdaten = abrufen(url, kennung, versuche=2)
    except IOError:
        return None
    text = rohdaten.decode("utf-8", "ignore")

    def feld(name):
        m = re.search(r'<div id="%s"[^>]*>\s*<span[^>]*>\s*([\d.,]+)' % name, text)
        if not m:
            return None
        try:
            return float(m.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            return None

    geld, brief = feld("bid"), feld("ask")
    if geld is None and brief is None:
        return None
    return {"geld": geld, "brief": brief,
            "spread_prozent": ((brief - geld) / brief * 100.0)
                              if (geld and brief) else None}


def tokenpreise_auswerten(konfig):
    """
    Verfolgt den Preis je Million Token der guenstigsten Spitzenmodelle.

    Das ist der einzige direkte Messwert fuer die Effizienzseite der These:
    Fallen die Preise schnell, wird Rechenleistung entwertet - und genau
    darauf setzt die Wette. Alles andere misst Effizienz nur ueber den Umweg
    von Aktienkursen, also gar nicht.

    Bei jeder Preisaenderung wird der alte Stand fortgeschrieben, sodass
    ueber die Wochen eine Zeitreihe entsteht.
    """
    einst = konfig.get("tokenpreise") or {}
    modelle = einst.get("modelle") or []
    spitze = [m for m in modelle if m.get("spitzenklasse")]
    if not spitze:
        return None

    schnitt_ein = sum(m["eingabe"] for m in spitze) / len(spitze)
    schnitt_aus = sum(m["ausgabe"] for m in spitze) / len(spitze)
    guenstigstes = min(spitze, key=lambda m: m["ausgabe"])

    verlauf = json_laden(TOKEN_PFAD, [])
    if not isinstance(verlauf, list):
        verlauf = []

    jetzt = {
        "datum": date.today().isoformat(),
        "schnitt_eingabe": round(schnitt_ein, 4),
        "schnitt_ausgabe": round(schnitt_aus, 4),
        "guenstigstes": "%s %s" % (guenstigstes["anbieter"], guenstigstes["modell"]),
        "guenstigster_preis": guenstigstes["ausgabe"],
        "modelle": len(spitze),
    }

    # Nur fortschreiben, wenn sich etwas geaendert hat - sonst waechst die
    # Datei mit identischen Zeilen zu.
    letzter = verlauf[-1] if verlauf else None
    if (not letzter
            or abs(letzter.get("schnitt_ausgabe", 0) - jetzt["schnitt_ausgabe"]) > 0.001
            or abs(letzter.get("schnitt_eingabe", 0) - jetzt["schnitt_eingabe"]) > 0.001):
        verlauf.append(jetzt)
        json_speichern(TOKEN_PFAD, verlauf[-200:])

    veraenderung = None
    vergleich = None
    if len(verlauf) >= 2:
        vorher = verlauf[-2]
        if vorher.get("schnitt_ausgabe"):
            veraenderung = ((jetzt["schnitt_ausgabe"] / vorher["schnitt_ausgabe"]) - 1) * 100
            vergleich = vorher.get("datum")

    return {
        "jetzt": jetzt, "veraenderung": veraenderung, "vergleich": vergleich,
        "modelle": modelle, "stand": einst.get("stand"), "verlauf": verlauf[-30:],
    }


def fred_reihe(kennung, reihe="BAMLH0A0HYM2", tage=140):
    """
    Holt eine Zeitreihe der US-Notenbank von St. Louis.

    Die Voreinstellung ist der optionsbereinigte Risikoaufschlag fuer
    US-Hochzinsanleihen - der Preis, den schlechte Schuldner ueber sichere
    zahlen muessen. Anders als ein Vergleich zweier Aktienkurse ist das die
    Groesse selbst, in Basispunkten, mit eindeutiger Richtung: steigt sie,
    wird Fremdkapital teurer.
    """
    url = ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=%s&cosd=%s"
           % (reihe, (date.today() - timedelta(days=tage)).isoformat()))
    try:
        roh = abrufen(url, kennung, versuche=2).decode("utf-8", "ignore")
    except IOError:
        return []
    werte = []
    for zeile in roh.strip().splitlines()[1:]:
        teile = zeile.split(",")
        if len(teile) < 2 or teile[1] in (".", ""):
            continue
        try:
            werte.append((teile[0], float(teile[1])))
        except ValueError:
            continue
    return werte


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

    # Erwarteter Wertverlust pro Woche bei Seitwaertslauf des Basiswerts.
    # Vorausschauend, also planbar - anders als der aufgelaufene Drag.
    sigma = kurs["sigma_jahr"] / 100.0
    ergebnis["drag_woche_prozent"] = (
        exp(0.5 * faktor * (1 - faktor) * sigma * sigma * (7.0 / 365.0)) - 1.0) * 100.0

    # Abstand zur Verlustschwelle: der Barrierepuffer sagt darueber nichts,
    # weil der Stop lange vor der Barriere greift.
    ergebnis["abstand_verlustschwelle"] = None
    stop = position.get("stop_schein")
    jetzt_schein = position.get("kurs_aktuell")
    if stop and jetzt_schein:
        ergebnis["abstand_verlustschwelle"] = (stop / jetzt_schein - 1.0) * 100.0

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


def indikatoren_bauen(kurse, gruppen, zusatz=None):
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

    # --- China-Gegenprobe ueber die Plattformen
    china = gruppe_schnitt("China KI-Modelle und Software", "monat_prozent")
    if china is not None and ndx is not None:
        rs = china - ndx
        ind.append({
            "name": "China-KI-Relativstaerke",
            "wert": rs,
            "einheit": "%-Pkt vs Nasdaq (1 Monat)",
            "erklaerung": "Chinesische Modell- und Softwarefirmen gegen den "
                          "Nasdaq: Alibaba, Tencent, SenseTime, iFlytek, Kingsoft "
                          "Cloud, Baidu. Das ist der Kern der China-These - "
                          "Effizienz durch bessere Modelle, nicht durch eigene "
                          "Fabriken.",
            "these": "gut" if rs > 2 else ("schlecht" if rs < -2 else "neutral"),
        })

    # --- China-KI auf Wochenfrist, damit sie mit den Neoclouds vergleichbar wird
    china_w = gruppe_schnitt("China KI-Modelle und Software", "woche_prozent")
    if china_w is not None and ndx_w is not None:
        rs_w = china_w - ndx_w
        ind.append({
            "name": "China-KI, Woche",
            "wert": rs_w,
            "einheit": "%-Pkt vs Nasdaq (1 Woche)",
            "erklaerung": "Dieselbe Gruppe auf kurzer Frist. Ein Monatswert kann "
                          "eine starke und eine schwache Woche verdecken - erst "
                          "der Vergleich beider Fristen zeigt, ob sich etwas "
                          "gerade dreht.",
            "these": "gut" if rs_w > 2 else ("schlecht" if rs_w < -2 else "neutral"),
        })

    # --- China-Gegenprobe ueber die Fertigung
    chipfert = gruppe_schnitt("China Chipfertigung", "monat_prozent")
    if chipfert is not None and ndx is not None:
        rs = chipfert - ndx
        ind.append({
            "name": "China-Chipfertigung",
            "wert": rs,
            "einheit": "%-Pkt vs Nasdaq (1 Monat)",
            "erklaerung": "SMIC, Cambricon und Hua Hong an ihren Heimatboersen. "
                          "Nur zur Kenntnis, nicht als Richtungssignal: Die These "
                          "behauptet Effizienz durch bessere Modelle, nicht eigene "
                          "Fabriken. Schwaeche hier ist mit ihr sogar vereinbar - "
                          "gute Modelle auf schwaecheren Chips ist genau der "
                          "DeepSeek-Fall.",
            "these": "neutral",
        })

    # --- Kreditrisiko am eigentlichen Mass, nicht am Aktienersatz
    aufschlag = zusatz.get("hochzins_aufschlag") if zusatz else None
    if aufschlag:
        jetzt_bp = aufschlag["jetzt"] * 100
        monat_bp = aufschlag["monat"] * 100
        woche_bp = aufschlag["woche"] * 100
        ind.append({
            "name": "Hochzins-Risikoaufschlag",
            "wert": jetzt_bp,
            "einheit": "Basispunkte (%+.0f Bp Woche, %+.0f Bp Monat)" % (woche_bp, monat_bp),
            "erklaerung": "Was schlechte Schuldner ueber sichere zahlen muessen "
                          "(ICE BofA, optionsbereinigt). <b>Steigt er, wird "
                          "Fremdkapital teuer</b> &ndash; und die "
                          "schuldenfinanzierten Rechenzentrumsbauer sind darauf "
                          "angewiesen. Eine Blase platzt ueber die Finanzierung. "
                          "Langfristiger Schnitt liegt bei rund 500 Basispunkten.",
            "these": ("gut" if monat_bp > 25
                      else "schlecht" if monat_bp < -25 else "neutral"),
            "nachkomma": 0,
            "veraenderung_monat": monat_bp,
        })

    # --- Preis je Million Token: der direkte Effizienzmesswert
    token = zusatz.get("tokenpreise") if zusatz else None
    if token:
        v = token.get("veraenderung")
        ind.append({
            "name": "Preis je Million Token",
            "wert": token["jetzt"]["schnitt_ausgabe"],
            "einheit": ("USD Ausgabe, Schnitt von %d Spitzenmodellen%s"
                        % (token["jetzt"]["modelle"],
                           ", %+.1f%% seit %s" % (v, token["vergleich"])
                           if v is not None else "")),
            "erklaerung": "Was ein Spitzenmodell je Million ausgegebener Token "
                          "kostet. <b>Fallende Preise entwerten Rechenleistung</b> "
                          "und stuetzen damit die These - das ist der einzige "
                          "direkte Messwert fuer die Effizienzseite. Guenstigstes "
                          "Modell derzeit: " + token["jetzt"]["guenstigstes"],
            "these": ("gut" if (v is not None and v < -5)
                      else "schlecht" if (v is not None and v > 5) else "neutral"),
            "nachkomma": 2,
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
        "China-KI-Relativstaerke": 1.0,
        "Strom-Relativstaerke": 0.8,
        "Hochzins-Risikoaufschlag": 1.0,
        "Hochzins-Kredite (HYG)": 0.7,
    }

    for ind in indikatoren:
        gewicht = gewichte.get(ind["name"])
        if gewicht is None:
            continue
        # Beim Risikoaufschlag zaehlt die Bewegung, nicht der absolute Stand:
        # 273 Basispunkte sind fuer sich genommen keine Richtungsaussage.
        roh = ind.get("veraenderung_monat", ind["wert"])
        if ind["name"] == "Hochzins-Risikoaufschlag":
            roh = -roh / 5.0          # 50 Bp Ausweitung entsprechen 10 Punkten
        if ind["name"] == "China-KI-Relativstaerke":
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


SEC_PUNKTE = {
    "1.01": ("Wesentliche Vereinbarung geschlossen", True),
    "1.02": ("Wesentliche Vereinbarung beendet", True),
    "1.03": ("Insolvenzverfahren", True),
    "2.01": ("Erwerb oder Veraeusserung von Vermoegen", True),
    "2.02": ("Quartals- oder Jahreszahlen", True),
    "2.03": ("Neue Finanzverbindlichkeit", True),
    "2.04": ("Verbindlichkeit faellig gestellt", True),
    "2.05": ("Restrukturierungskosten beschlossen", True),
    "2.06": ("Ausserplanmaessige Abschreibung", True),
    "3.01": ("Hinweis auf Delisting", True),
    "3.02": ("Aktien ausserhalb der Boerse ausgegeben", False),
    "4.01": ("Wechsel des Abschlusspruefers", True),
    "4.02": ("Fruehere Abschluesse nicht verlaesslich", True),
    "5.02": ("Wechsel im Vorstand oder Aufsichtsrat", False),
    "5.03": ("Satzungsaenderung", False),
    "5.07": ("Ergebnisse der Hauptversammlung", False),
    "7.01": ("Freiwillige Mitteilung", False),
    "8.01": ("Sonstiges Ereignis", False),
    "9.01": ("Finanzberichte und Anlagen", False),
}


def sec_inhalt_lesen(link, punkte, kennung, hoechstlaenge=1400):
    """
    Liest den Text zu den wesentlichen Punkten einer 8-K-Meldung.

    Die Punktnummer sagt, WAS passiert ist, aber nicht WORUM es geht. Erst der
    Wortlaut zeigt, ob eine "neue Finanzverbindlichkeit" eine gewoehnliche
    Anleihe ist oder eine Buergschaft fuer einen Kunden - also
    Zirkelfinanzierung, die den eigenen Umsatz stuetzt.
    """
    if not link:
        return ""
    try:
        rohdaten = abrufen(link, kennung, versuche=2)
    except IOError:
        return ""

    text = rohdaten.decode("utf-8", "ignore")
    text = re.sub(r"<[^>]+>", " ", text)
    for alt, neu in [("&#160;", " "), ("&nbsp;", " "), ("&#8220;", '"'),
                     ("&#8221;", '"'), ("&#8217;", "'"), ("&#8212;", "-"),
                     ("&amp;", "&"), ("&#8211;", "-")]:
        text = text.replace(alt, neu)
    text = re.sub(r"\s+", " ", text)

    stuecke = []
    for punkt in punkte:
        beschreibung = SEC_PUNKTE.get(punkt, ("Punkt " + punkt, False))
        if not beschreibung[1]:
            continue                      # nur die wesentlichen ausschreiben
        treffer = re.search(r"Item\s+%s(.{60,%d})" % (re.escape(punkt), hoechstlaenge),
                            text)
        if treffer:
            roh = treffer.group(1).strip(" .\u00a0")
            # Bis zum naechsten Punkt abschneiden, sonst laeuft es weiter
            ende = re.search(r"Item\s+\d\.\d\d", roh)
            if ende and ende.start() > 120:
                roh = roh[:ende.start()]
            stuecke.append("%s: %s" % (beschreibung[0], roh.strip()))
    return " | ".join(stuecke)[:2600]


def sec_meldungen(cik, name, kennung, maximal=6):
    """
    Ad-hoc-Pflichtmeldungen einer Firma, aufgeschluesselt nach Punktnummern.

    Der Atom-Feed liefert nur die immer gleiche Zeile "8-K - Current report".
    Die Einreichungs-Schnittstelle nennt dagegen die Punkte, und die verraten,
    worum es geht: 2.03 ist eine neue Finanzverbindlichkeit, 2.06 eine
    ausserplanmaessige Abschreibung, 2.02 sind Zahlen. Ohne das steht die
    Meldung blind im Bericht.
    """
    url = "https://data.sec.gov/submissions/CIK%010d.json" % int(cik)
    try:
        daten = json.loads(abrufen(url, kennung, versuche=2).decode("utf-8"))
    except Exception:                                            # noqa: BLE001
        return []

    j = daten.get("filings", {}).get("recent", {})
    formulare = j.get("form", [])
    eintraege = []
    for i, form in enumerate(formulare):
        if form != "8-K":
            continue
        punkte = [p.strip() for p in (j.get("items", [""] * len(formulare))[i] or "").split(",") if p.strip()]
        beschreibungen, wichtig = [], False
        for punkt in punkte:
            text, zaehlt = SEC_PUNKTE.get(punkt, ("Punkt " + punkt, False))
            beschreibungen.append(text)
            wichtig = wichtig or zaehlt
        akz = (j.get("accessionNumber", [""] * len(formulare))[i] or "").replace("-", "")
        dok = j.get("primaryDocument", [""] * len(formulare))[i] or ""
        eintraege.append({
            "quelle": "SEC / " + name,
            "firma": name,
            "titel": "%s: %s" % (name, ", ".join(beschreibungen) or "8-K"),
            "datum": j.get("filingDate", [""] * len(formulare))[i],
            "punkte": punkte,
            "wichtig": wichtig,
            "link": ("https://www.sec.gov/Archives/edgar/data/%s/%s/%s"
                     % (int(cik), akz, dok)) if akz and dok else "",
            "auszug": "",
        })
        if len(eintraege) >= maximal:
            break

    # Nur die wesentlichen und nur die juengsten ausschreiben - jede Abfrage
    # kostet Zeit, und aeltere Meldungen sind ohnehin verarbeitet.
    grenze = (date.today() - timedelta(days=45)).isoformat()
    gelesen = 0
    for eintrag in eintraege:
        if gelesen >= 3:
            break
        if eintrag["wichtig"] and eintrag["datum"] >= grenze:
            eintrag["auszug"] = sec_inhalt_lesen(eintrag["link"],
                                                 eintrag["punkte"], kennung)
            if eintrag["auszug"]:
                gelesen += 1
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


MONATE = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
          "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}


def datum_lesen(text):
    """Erkennt die gaengigen Datumsformate aus RSS- und Atom-Feeds."""
    if not text:
        return None
    t = text.strip()
    m = re.search(r"(\d{1,2})\s+([A-Z][a-z]{2})\s+(\d{4})", t)      # 19 Aug 2026
    if m and m.group(2) in MONATE:
        try:
            return date(int(m.group(3)), MONATE[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)                     # 2026-08-19
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def alter_bestimmen(eintrag, hoechstalter_tage):
    """
    Setzt 'alter_tage' und 'veraltet'. Meldungen ohne lesbares Datum gelten
    als aktuell - lieber eine alte durchlassen als eine neue verwerfen.
    """
    d = datum_lesen(eintrag.get("datum", ""))
    eintrag["datum_erkannt"] = d.isoformat() if d else None
    if d is None:
        eintrag["alter_tage"] = None
        eintrag["veraltet"] = False
    else:
        tage = (date.today() - d).days
        eintrag["alter_tage"] = tage
        eintrag["veraltet"] = tage > hoechstalter_tage
    return eintrag


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
                  regierung, blogs, sec, tokenpreise=None):
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

Positionen (Puffer = bis zur Knock-Out-Barriere, bis Stop = bis zur
Verkaufsmarke, die deutlich frueher greift):
%s

Abgeleitete Indikatoren:
%s

Schlagzeilen mit Stichworttreffern:
%s

Regierungsvorhaben:
%s

Preis je Million Token (Ausgabe, US-Dollar) - der direkte Effizienzmesswert:
%s

Veroeffentlichungen der KI-Labore:
%s

SEC-Pflichtmeldungen (8-K), nach Punktnummern aufgeschluesselt.
Wesentlich sind vor allem: 1.01 Vereinbarung, 2.02 Zahlen, 2.03 neue
Finanzverbindlichkeit, 2.06 ausserplanmaessige Abschreibung. Eine neue
Finanzverbindlichkeit bei einem Chiphersteller kann Zirkelfinanzierung sein -
schau dort genauer hin und recherchiere bei Bedarf, worum es geht.
%s

ZWEI CHINA-MASSE, DIE VERSCHIEDENES MESSEN
Verwechsle sie nicht. Die These lautet: China gewinnt durch EFFIZIENZ - bessere
Modelle mit weniger Rechenleistung, wie beim DeepSeek-Moment. Sie lautet NICHT:
China baut eigene Fabriken.

- "China-KI-Relativstaerke" (Alibaba/Qwen, Tencent/Hunyuan, SenseTime, iFlytek,
  Kingsoft Cloud, Baidu/Ernie) misst die Modellseite. DAS ist der Kern der These.
- "China-Chipfertigung" (SMIC, Cambricon, Hua Hong) misst die Hardwareseite.
  Schwaeche dort widerlegt die These NICHT - sie ist sogar mit ihr vereinbar:
  bessere Modelle auf schwaecheren Chips ist genau die Behauptung.

Wenn beide auseinanderlaufen, benenne das als Befund statt es zu verrechnen.

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

EILMELDUNG
Zusaetzlich entscheidest du, ob dieser Bericht eine sofortige Warnmail
rechtfertigt. Sie unterbricht den Nutzer ausserhalb des Tagesrhythmus - setze
sie nur, wenn er die Lage HEUTE kennen muss, nicht erst heute Abend.

Ausloeser sind ausschliesslich:

1. POSITION IN GEFAHR: Barriere-Puffer unter 25 Prozent, oder ein Schein
   naehert sich der Verlustschwelle von 30 Prozent, oder eine Tagesbewegung
   von mehr als 3 Standardabweichungen gegen die Position.
2. THESE GEBROCHEN: Ein Hyperscaler hebt die Capex-Prognose an, Nvidia gibt
   eine starke Rechenzentrums-Guidance, oder ein Ausruester meldet steigenden
   Auftragseingang. Also die Art Nachricht, nach der man die Position
   ueberdenkt statt sie auszusitzen.
3. THESE SCHLAGARTIG BESTAETIGT: Ein Effizienzdurchbruch bei Modellen im
   Rang eines DeepSeek-Moments, eine angekuendigte Capex-Kuerzung, ein
   grossflaechiger Baustopp, oder erstmals sichtbarer Finanzierungsstress
   (Hochzins-Risikoaufschlag weitet sich um mehr als 50 Basispunkte im Monat). Auch Gutes kann eilig sein,
   wenn es eine Gewinnmitnahme nahelegt.
4. TERMIN MIT FOLGEN: Nvidia-Zahlen sind erschienen und weichen erkennbar
   von der Erwartung ab.
5. ETWAS, DAS IN KEINE DIESER SCHUBLADEN PASST, aber die Halte-Entscheidung
   heute veraendert. Dafuer hast du Ermessen - begruende es dann kurz.

Kein Ausloeser sind: gewoehnliche Tagesschwankung, wiederholte Altmeldungen,
Barometerbewegungen unter 15 Punkten, allgemeine Blasen-Kommentare ohne neuen
Sachverhalt. Im Zweifel keine Eilmeldung - eine falsche kostet mehr
Aufmerksamkeit als eine verspaetete.

Formuliere die Eilmeldung selbst, knapp und in ganzen Saetzen. Du bestimmst
Betreff, Schlagzeile und Aufbau; die Felder sind ein Geruest, kein Korsett.
Nenne konkrete Zahlen statt Adjektive.

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
 "begruendung": "1-2 Saetze, warum dieser Handlungsbedarf",
 "eilmeldung": {"noetig": false,
                "stufe": "hoch|kritisch",
                "ausloeser": "welche der fuenf Nummern, oder eigene Begruendung",
                "betreff": "Betreffzeile der Mail, unter 70 Zeichen",
                "schlagzeile": "ein Satz, der die Lage auf den Punkt bringt",
                "was_geschehen_ist": "2-3 Saetze zum Sachverhalt",
                "warum_es_zaehlt": "2-3 Saetze zur Bedeutung fuer die Position",
                "was_du_tun_koenntest": "konkrete Handlungsmoeglichkeiten, ohne Empfehlung",
                "zahlen": ["Kennzahl: Wert", "Kennzahl: Wert"]}}
""" % (
        konfig.get("zeitlimit_bis", "offen"),
        date.today().strftime("%d.%m.%Y"),
        barometer[0], barometer[1],
        zeilen(positionen, 5, lambda p: "  %s (%s): Basiswert %.2f, Tag %+.2f%%, "
               "Puffer %s, bis Stop %s" % (
                   p["name"], p.get("wkn", ""), p["kurs"], p["tag_prozent"],
                   ("%.1f%%" % p["barriere_abstand"]) if p.get("barriere_abstand")
                   is not None else "?",
                   ("%.1f%%" % p["abstand_verlustschwelle"])
                   if p.get("abstand_verlustschwelle") is not None else "?")),
        zeilen(indikatoren, 12, lambda i: "  %s: %.2f %s" % (
            i["name"], i["wert"], i["einheit"])),
        zeilen(relevant, 25, lambda n: "  [%s] %s (%s)" % (
            "GEGEN" if n["kategorie"] == "these_gefaehrdet" else "FUER",
            n["titel"][:150], n.get("quelle", ""))),
        zeilen(regierung, 8, lambda r: "  %s - %s (%s)" % (
            r["datum"], r["titel"][:150], r.get("behoerde", "")[:60])),
        ("\n".join("  %-10s %-22s %s %5.2f Ausgabe%s"
                    % (m["anbieter"], m["modell"], m.get("land", ""), m["ausgabe"],
                       "  " + m["bemerkung"] if m.get("bemerkung") else "")
                    for m in sorted((tokenpreise or {}).get("modelle", []),
                                    key=lambda x: x["ausgabe"])[:10])
         or "  (keine Preise hinterlegt)"),
        zeilen(blogs, 10, lambda b: "  [%s] %s" % (b["quelle"], b["titel"][:150])),
        zeilen(sec, 10, lambda s: "  %s %s%s%s" % (
            s.get("datum", ""), s["titel"][:130],
            "  <-- wesentlich" if s.get("wichtig") else "",
            ("\n      WORTLAUT: " + s["auszug"][:1100]) if s.get("auszug") else "")),
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
        if not s.get("wichtig"):
            continue          # Hauptversammlung, Anlagenverzeichnis und
                              # freiwillige Mitteilungen sind kein Ereignis
        alarme.append(("alarm" if any(p in ("2.02", "2.03", "2.06", "1.03", "4.02")
                                      for p in s.get("punkte", []))
                       else "hinweis",
                       "SEC-Pflichtmeldung &ndash; %s" % s["titel"][:140]))

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

def ist_mac():
    return sys.platform == "darwin"


def systemmeldung(titel, text, ton=None):
    """Mitteilung auf dem Mac. Auf dem Pi gibt es keine Oberflaeche - dort
    landet die Warnung im Protokoll und per Mail."""
    if not ist_mac():
        log_schreiben("MELDUNG %s: %s" % (titel, text[:180]))
        return
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


def positionswert_verlauf(position, kurs, devisen=None):
    """
    Rechnet den Eurowert der Position ueber die Zeit - so, wie ihn das Depot
    ausweist, also zum Geldkurs.

    Drei Dinge gehen ein:

    1. Ein Faktor-Papier bildet die TAEGLICHE Bewegung des Basiswerts mit dem
       Faktor ab. Der Wert ergibt sich aus dem fortlaufenden Produkt
       (1 + Faktor * Tagesrendite), nicht aus der Gesamtveraenderung.
    2. Beide Scheine sind nicht waehrungsgesichert. Steigt der Euro, faellt
       ihr Eurowert, auch wenn der Basiswert stillsteht.
    3. Gekauft wird zum Brief-, bewertet zum Geldkurs. Die Kurve zeigt den
       Geldkurs, die Einsatzlinie den bezahlten Briefkurs - der Abstand
       dazwischen ist die Handelsspanne.

    Steht "kurs_aktuell" in der Konfiguration, ersetzt dieser Wert den
    letzten Punkt. Dann stimmt der Graph exakt mit dem Depot ueberein.
    """
    kurse = kurs.get("verlauf") or []
    daten = kurs.get("verlauf_datum") or []
    stueck = position.get("stueck")
    einstand = position.get("einstiegskurs_schein")
    faktor = position.get("faktor", -2)
    if len(kurse) < 5 or len(daten) != len(kurse) or not stueck or not einstand:
        return None

    try:
        einstieg = datetime.strptime(position.get("einstieg_datum", ""), "%Y-%m-%d").date()
    except ValueError:
        return None

    # Index des Einstiegstags (oder der letzte Tag davor)
    anker_index = len(kurse) - 1
    for i, d in enumerate(daten):
        if d >= einstieg:
            anker_index = i
            break

    # Scheinkurs entlang der Reihe, verankert am Einstand
    schein = [1.0] * len(kurse)
    for i in range(anker_index + 1, len(kurse)):
        r = (kurse[i] / kurse[i - 1]) - 1.0
        schein[i] = schein[i - 1] * (1.0 + faktor * r)
    for i in range(anker_index - 1, -1, -1):
        r = (kurse[i + 1] / kurse[i]) - 1.0
        teiler = 1.0 + faktor * r
        schein[i] = schein[i + 1] / teiler if abs(teiler) > 1e-9 else schein[i + 1]

    # Wechselkurswirkung: Eurowert skaliert mit dem Kehrwert von EUR/USD
    fx = {}
    if devisen and devisen.get("verlauf") and devisen.get("verlauf_datum"):
        fx = dict(zip(devisen["verlauf_datum"], devisen["verlauf"]))
    fx_anker = fx.get(daten[anker_index])

    spanne = position.get("spread_prozent", 0.0) / 100.0

    punkte = []
    for i, d in enumerate(daten):
        wert = schein[i] * einstand * stueck
        if fx_anker and fx.get(d):
            wert *= fx_anker / fx[d]
        # Der Einstiegstag steht auf dem tatsaechlich bezahlten Briefkurs.
        # Erst danach wird zum Geldkurs bewertet, so wie das Depot es tut -
        # der Absatz gleich hinter dem Einstieg ist die Handelsspanne.
        if i > anker_index:
            wert *= (1.0 - spanne)
        punkte.append({"datum": d, "wert": max(0.0, wert), "vor_einstieg": i < anker_index})

    # Falls ein tatsaechlicher Scheinkurs vorliegt, hat er Vorrang fuer den
    # aktuellen Stand. Am Kauftag faellt der Einstieg auf denselben Tag wie
    # der Ist-Kurs - dann wird ein zusaetzlicher Punkt angehaengt, damit der
    # Einstieg auf dem bezahlten Kurs stehen bleibt und die Spanne sichtbar
    # wird, statt den Ankerpunkt zu ueberschreiben.
    ist_kurs = position.get("kurs_aktuell")
    if ist_kurs:
        if anker_index == len(punkte) - 1:
            punkte.append({"datum": punkte[-1]["datum"],
                           "wert": ist_kurs * stueck,
                           "vor_einstieg": False, "gemessen": True})
        else:
            punkte[-1]["wert"] = ist_kurs * stueck
            punkte[-1]["gemessen"] = True

    # Der Vorlauf dient nur der Einordnung. Er wird gekuerzt, damit die Zeit
    # seit dem Einstieg den Graphen bestimmt und nicht die Vorgeschichte.
    # Mindestens 8 Tage Vorlauf, hoechstens so viele wie Haltetage.
    haltetage = len(punkte) - 1 - anker_index
    vorlauf = max(8, min(anker_index, max(8, haltetage)))
    ab = max(0, anker_index - vorlauf)
    punkte = punkte[ab:]
    anker_index -= ab

    return {
        "name": position["name"], "wkn": position.get("wkn", ""),
        "punkte": punkte, "einsatz": einstand * stueck,
        "anker": anker_index,
        "einstieg": einstieg.isoformat(),
        "gemessen": bool(position.get("kurs_aktuell")),
    }


FARBEN = ["var(--akzent)", "var(--warn)"]


def wertverlauf_grafik(reihen, hoehe=190, breite=920):
    """Zwei Linien mit dem Eurowert der Positionen, plus Einsatzlinie."""
    reihen = [r for r in reihen if r and len(r["punkte"]) > 2]
    if not reihen:
        return ""

    n = max(len(r["punkte"]) for r in reihen)
    alle = [p["wert"] for r in reihen for p in r["punkte"]]
    alle += [r["einsatz"] for r in reihen]
    tief, hoch = min(alle), max(alle)
    spanne = (hoch - tief) or 1.0
    tief -= spanne * 0.1
    hoch += spanne * 0.1
    spanne = hoch - tief

    links, rechts, oben, unten = 58, 14, 12, 26
    zeichenbreite = breite - links - rechts
    zeichenhoehe = hoehe - oben - unten

    def x(i, laenge):
        return links + (i / max(1, laenge - 1)) * zeichenbreite

    def y(w):
        return oben + (1 - (w - tief) / spanne) * zeichenhoehe

    t = ['<svg class="wertchart" viewBox="0 0 %d %d" width="100%%" '
         'preserveAspectRatio="none" role="img">' % (breite, hoehe)]

    # Waagerechte Hilfslinien mit Eurobeschriftung
    for anteil in (0, 0.25, 0.5, 0.75, 1):
        w = tief + spanne * anteil
        yy = y(w)
        t.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--rand)" '
                 'stroke-width="1"/>' % (links, yy, breite - rechts, yy))
        t.append('<text x="%.1f" y="%.1f" font-size="10" fill="var(--gedaempft)" '
                 'text-anchor="end">%d &#8364;</text>' % (links - 6, yy + 3, round(w)))

    # Senkrechte Marke am Einstiegstag - alles links davon ist rechnerisch
    erste = reihen[0]
    xe = x(erste["anker"], len(erste["punkte"]))
    t.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="var(--gedaempft)" '
             'stroke-width="1" stroke-dasharray="2 2" opacity=".7"/>'
             % (xe, oben, xe, hoehe - unten))
    t.append('<text x="%.1f" y="%d" font-size="10" font-weight="600" '
             'fill="var(--gedaempft)" text-anchor="%s">Einstieg</text>'
             % (xe + (5 if xe < breite * 0.7 else -5), oben + 9,
                "start" if xe < breite * 0.7 else "end"))

    for nr, r in enumerate(reihen):
        farbe = FARBEN[nr % len(FARBEN)]
        punkte = r["punkte"]
        anker = r["anker"]

        # Einsatzlinie: ab hier ist Gewinn oder Verlust ablesbar
        ye = y(r["einsatz"])
        t.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
                 'stroke-width="1" stroke-dasharray="2 3" opacity=".45"/>'
                 % (x(anker, len(punkte)), ye, breite - rechts, ye, farbe))

        vor = " ".join("%.1f,%.1f" % (x(i, len(punkte)), y(p["wert"]))
                       for i, p in enumerate(punkte) if i <= anker)
        nach = " ".join("%.1f,%.1f" % (x(i, len(punkte)), y(p["wert"]))
                        for i, p in enumerate(punkte) if i >= anker)
        if vor.count(",") > 1:
            t.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="1.4" '
                     'stroke-dasharray="3 3" opacity=".4"/>' % (vor, farbe))
        if nach.count(",") > 1:
            t.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2.2" '
                     'stroke-linejoin="round"/>' % (nach, farbe))
        # Einstiegspunkt und aktueller Punkt
        t.append('<circle cx="%.1f" cy="%.1f" r="3" fill="var(--grund)" stroke="%s" '
                 'stroke-width="1.6"/>' % (x(anker, len(punkte)), y(punkte[anker]["wert"]), farbe))
        # Gemessener Ist-Kurs bekommt einen Ring, gerechneter nicht
        xj, yj = x(len(punkte) - 1, len(punkte)), y(punkte[-1]["wert"])
        t.append('<circle cx="%.1f" cy="%.1f" r="3.4" fill="%s"/>' % (xj, yj, farbe))
        if r.get("gemessen"):
            t.append('<circle cx="%.1f" cy="%.1f" r="6" fill="none" stroke="%s" '
                     'stroke-width="1.2" opacity=".55"/>' % (xj, yj, farbe))

    def tag(wert):
        """Datum beschriften - als Objekt oder als Text aus der Sicherung."""
        if hasattr(wert, "strftime"):
            return wert.strftime("%d.%m.")
        teile = str(wert).split("-")
        return "%s.%s." % (teile[2], teile[1]) if len(teile) == 3 else str(wert)

    erster = reihen[0]["punkte"]
    t.append('<text x="%.1f" y="%d" font-size="10" fill="var(--gedaempft)">%s</text>'
             % (links, hoehe - 8, tag(erster[0]["datum"])))
    t.append('<text x="%.1f" y="%d" font-size="10" fill="var(--gedaempft)" '
             'text-anchor="end">%s</text>'
             % (breite - rechts, hoehe - 8, tag(erster[-1]["datum"])))
    t.append("</svg>")

    # Legende
    beine = []
    for nr, r in enumerate(reihen):
        jetzt = r["punkte"][-1]["wert"]
        gv = jetzt - r["einsatz"]
        beine.append(
            '<span class="bein"><i style="background:%s"></i>%s '
            '<b>%s&nbsp;&#8364;</b> <span class="%s">%+.0f&nbsp;&#8364; (%+.1f%%)</span></span>'
            % (FARBEN[nr % len(FARBEN)], r["name"],
               ("%.0f" % jetzt).replace(",", "."),
               "gut" if gv >= 0 else "schlecht", gv, gv / r["einsatz"] * 100))
    gesamt_jetzt = sum(r["punkte"][-1]["wert"] for r in reihen)
    gesamt_ein = sum(r["einsatz"] for r in reihen)
    gv = gesamt_jetzt - gesamt_ein
    beine.append('<span class="bein gesamt">Gesamt <b>%.0f&nbsp;&#8364;</b> '
                 '<span class="%s">%+.0f&nbsp;&#8364; (%+.1f%%)</span></span>'
                 % (gesamt_jetzt, "gut" if gv >= 0 else "schlecht", gv,
                    gv / gesamt_ein * 100))

    return ('<div class="wertkarte">%s<div class="legende">%s</div>'
            '<div class="klein">Der Einstiegspunkt liegt auf dem <b>tatsaechlich '
            'bezahlten Kurs</b>, die waagerechte Linie je Farbe ebenfalls. Ab dem '
            'Tag danach wird zum <b>Geldkurs</b> bewertet, so wie das Depot es tut '
            '&ndash; der Absatz gleich hinter dem Einstieg ist die Handelsspanne. '
            'Gestrichelt vor dem Einstieg: rechnerischer Verlauf, nicht dein '
            'tatsaechlicher. %s Zwischenwerte sind aus der Tagesbewegung des '
            'Basiswerts mal Faktor und dem Wechselkurs EUR/USD gerechnet (beide '
            'Scheine sind nicht waehrungsgesichert).</div></div>'
            % ("".join(t), " ".join(beine),
               ("Der aktuelle Punkt stammt aus <b>abgerufenen Ist-Kursen</b> "
                "(Quotierung des Emittenten, wie im ING-Direkthandel)."
                if any(r.get("gemessen") for r in reihen) else
                "Kein Ist-Kurs hinterlegt &ndash; der aktuelle Punkt ist ebenfalls "
                "gerechnet und kann vom Depot abweichen.")))


KERNINDIKATOREN = ["Kreditrisiko-Aufschlag", "VIX-Terminstruktur",
                   "Konzentrations-Spread"]


STEUERUNG = """
<div class="steuerung" id="steuerung" hidden>
  <div class="kern-titel" style="margin-top:16px">Steuerung</div>
  <button type="button" data-aktion="neu">Bericht erneuern</button>
  <button type="button" id="mehroeffnen" class="leise">Weitere Aktionen &hellip;</button>
  <div class="rueckmeldung" id="rueckmeldung" hidden></div>
</div>

<dialog id="mehrfenster" class="mehrfenster">
  <div class="mf-kopf">
    <b>Weitere Aktionen</b>
    <button type="button" id="mehrzu" aria-label="Schliessen">&times;</button>
  </div>

  <div class="mf-block">
    <div class="mf-titel">Alarme</div>
    <div class="mf-reihe">
      <button type="button" data-aktion2="ruhe" id="mf-ruhe">Stumm bis morgen</button>
      <button type="button" data-aktion2="probealarm">Probealarm</button>
    </div>
    <div class="mf-hinweis" id="mf-ruhestand">Die Ueberwachung laeuft
     waehrend der Stummschaltung weiter, nur Lampe und Telegram schweigen.</div>
  </div>

  <div class="mf-block">
    <div class="mf-titel">Reset-Barrieren nachtragen</div>
    <div class="mf-hinweis" id="mf-barrierestand"></div>
    <div class="mf-reihe">
      <input type="text" id="mf-barriere" placeholder="324.00 421.08" autocomplete="off">
      <button type="button" id="mf-barriere-los">Setzen</button>
    </div>
  </div>

  <div class="mf-block">
    <div class="mf-titel">Positionen</div>
    <div class="mf-reihe" id="mf-positionen"></div>
    <div class="mf-hinweis">Als geschlossen markierte Positionen werden nicht
     mehr bewertet und loesen keine Alarme aus. Nochmal tippen macht es rueckgaengig.</div>
  </div>

  <div class="mf-block">
    <div class="mf-titel">Vermerk fuer den Bericht</div>
    <div class="mf-reihe">
      <input type="text" id="mf-vermerk" placeholder="erscheint oben im Bericht"
             maxlength="200" autocomplete="off">
      <button type="button" id="mf-vermerk-los">Merken</button>
    </div>
    <div class="mf-hinweis">Leeres Feld und Merken loescht den Vermerk.</div>
  </div>

  <div class="mf-block">
    <div class="mf-titel">Senden</div>
    <div class="mf-reihe">
      <button type="button" data-aktion2="telegram-bericht">Bericht per Telegram</button>
    </div>
  </div>

  <div class="rueckmeldung" id="mf-meldung" hidden></div>
</dialog>

<script>
(function () {
  var fenster = document.getElementById("mehrfenster");
  var meldung = document.getElementById("mf-meldung");
  var ruheknopf = document.getElementById("mf-ruhe");
  var ruhestand = document.getElementById("mf-ruhestand");
  var stand = document.getElementById("mf-barrierestand");
  var liste = document.getElementById("mf-positionen");
  var feld = document.getElementById("mf-barriere");

  function sagen(text, gut) {
    meldung.textContent = text;
    meldung.className = "rueckmeldung " + (gut === false ? "schlecht" : "gut");
    meldung.hidden = false;
    setTimeout(function () { meldung.hidden = true; }, 9000);
  }

  function holen(ziel) {
    return fetch(ziel, { cache: "no-store" }).then(function (a) { return a.json(); });
  }

  function positionenLaden() {
    holen("/aktion/positionen").then(function (z) {
      liste.innerHTML = "";
      var teile = [];
      (z.positionen || []).forEach(function (p) {
        var k = document.createElement("button");
        k.type = "button";
        k.textContent = p.wkn + (p.geschlossen ? " \u2013 geschlossen" : "");
        k.className = p.geschlossen ? "zu" : "";
        k.onclick = function () {
          holen("/aktion/verkauft?wkn=" + encodeURIComponent(p.wkn))
            .then(function (r) { sagen(r.text, r.ok); positionenLaden(); });
        };
        liste.appendChild(k);
        teile.push(p.wkn + " " + (p.barriere || 0).toFixed(2)
                   + " (Stand " + (p.stand || "?") + ")");
        if (!feld.value) {
          feld.placeholder = (z.positionen || [])
            .map(function (x) { return (x.barriere || 0).toFixed(2); }).join(" ");
        }
      });
      stand.textContent = "Aktuell: " + teile.join(", ");
    });
  }

  var vermerkfeld = document.getElementById("mf-vermerk");

  function ruheLaden() {
    holen("/aktion/zustand").then(function (z) {
      if (z.notiz !== undefined) { vermerkfeld.value = z.notiz || ""; }
      ruheknopf.textContent = z.ruhe_bis ? "Stumm bis " + z.ruhe_bis + " \u2013 aufheben"
                                         : "Stumm bis morgen";
      ruheknopf.dataset.aktion2 = z.ruhe_bis ? "ruhe-aus" : "ruhe";
      ruheknopf.classList.toggle("zu", !!z.ruhe_bis);
      ruhestand.textContent = z.ruhe_bis
        ? "Alarme schweigen bis " + z.ruhe_bis + " Uhr. Die Ueberwachung laeuft weiter."
        : "Die Ueberwachung laeuft waehrend der Stummschaltung weiter, "
          + "nur Lampe und Telegram schweigen.";
    });
  }

  document.getElementById("mehroeffnen").onclick = function () {
    positionenLaden();
    ruheLaden();
    if (fenster.showModal) { fenster.showModal(); } else { fenster.setAttribute("open", ""); }
  };
  document.getElementById("mehrzu").onclick = function () {
    if (fenster.close) { fenster.close(); } else { fenster.removeAttribute("open"); }
  };
  fenster.addEventListener("click", function (e) {
    if (e.target === fenster) { fenster.close(); }
  });

  fenster.addEventListener("click", function (e) {
    var a = e.target.closest("button[data-aktion2]");
    if (!a) { return; }
    a.disabled = true;
    holen("/aktion/" + a.dataset.aktion2)
      .then(function (z) { sagen(z.text, z.ok); ruheLaden(); })
      .finally(function () { a.disabled = false; });
  });

  document.getElementById("mf-vermerk-los").onclick = function () {
    holen("/aktion/notiz?text=" + encodeURIComponent(vermerkfeld.value.trim()))
      .then(function (z) { sagen(z.text, z.ok); });
  };
  vermerkfeld.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { document.getElementById("mf-vermerk-los").click(); }
  });

  document.getElementById("mf-barriere-los").onclick = function () {
    var wert = feld.value.trim() || feld.placeholder;
    holen("/aktion/barriere?werte=" + encodeURIComponent(wert))
      .then(function (z) { sagen(z.text, z.ok); if (z.ok) { positionenLaden(); } });
  };
  feld.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { document.getElementById("mf-barriere-los").click(); }
  });
})();
</script>
<script>
(function () {
  var block = document.getElementById("steuerung");
  var meldung = document.getElementById("rueckmeldung");


  function sagen(text, gut) {
    meldung.textContent = text;
    meldung.className = "rueckmeldung " + (gut === false ? "schlecht" : "gut");
    meldung.hidden = false;
    setTimeout(function () { meldung.hidden = true; }, 9000);
  }

  function zustand() {
    fetch("/aktion/zustand", { cache: "no-store" })
      .then(function (a) { return a.json(); })
      .then(function (z) {
        block.hidden = false;
      })
      .catch(function () { block.hidden = true; });
  }

  block.addEventListener("click", function (e) {
    var knopf = e.target.closest("button[data-aktion]");
    if (!knopf) { return; }
    knopf.disabled = true;
    var ziel = "/aktion/" + knopf.dataset.aktion;
    fetch(ziel, { cache: "no-store" })
      .then(function (a) { return a.json(); })
      .then(function (z) { sagen(z.text || "Erledigt.", z.ok !== false); zustand(); })
      .catch(function () { sagen("Hat nicht geklappt.", false); })
      .finally(function () { knopf.disabled = false; });
  });

  zustand();
  setInterval(zustand, 30000);
})();
</script>
"""


def kernbox(indikatoren, gruppen_ansicht, mit_steuerung=True):
    """
    Schmale Spalte mit den Kennzahlen, die den Zustand des Systems beschreiben -
    nicht die Richtung einzelner Werte. Der Kreditrisiko-Aufschlag steht oben:
    Blasen platzen ueber die Finanzierung, nicht ueber die Stimmung.
    """
    nach_name = {i["name"]: i for i in indikatoren}
    t = ['<aside class="kernbox">']

    haupt = nach_name.get("Hochzins-Risikoaufschlag")
    if haupt:
        klasse = ("gut" if haupt["these"] == "gut"
                  else "schlecht" if haupt["these"] == "schlecht" else "neutral")
        # Skala von -3 bis +3 Prozentpunkten: links rot (Risikofreude, gegen
        # die These), Mitte grau, rechts gruen (Stress, fuer die These).
        # Skala von 200 bis 800 Basispunkten: links eng (Geld billig, gegen
        # die These), rechts weit (Stress, fuer die These).
        anteil = max(0.0, min(1.0, (haupt["wert"] - 200.0) / 600.0))
        veraenderung = haupt.get("veraenderung_monat", 0.0)
        t.append('<div class="kern-haupt">'
                 '<div class="kern-titel">Hochzins-Risikoaufschlag</div>'
                 '<div class="kern-wert %s">%.0f <span class="einheit">Bp</span></div>'
                 '<div class="klein" style="margin:-2px 0 4px">%+.0f Bp im Monat</div>'
                 '<div class="kernskala"><i style="left:calc(%.1f%% - 1px)"></i></div>'
                 '<div class="kernskala-marken"><span>200 billig</span>'
                 '<span>500 Schnitt</span><span>800 Stress</span></div>'
                 '<div class="kern-hinweis">Was schlechte Schuldner ueber sichere '
                 'zahlen. <b>Steigt er, wird Fremdkapital teuer</b> &ndash; das '
                 'stuetzt die These. Eine Blase platzt ueber die Finanzierung.'
                 '</div></div>'
                 % (klasse, haupt["wert"], veraenderung, anteil * 100))

    weitere = [nach_name[n] for n in KERNINDIKATOREN[1:] if n in nach_name]
    if weitere:
        t.append('<div class="kern-liste">')
        for i in weitere:
            klasse = ("gut" if i["these"] == "gut"
                      else "schlecht" if i["these"] == "schlecht" else "neutral")
            nk = i.get("nachkomma", 2)
            t.append('<div class="kern-zeile"><span>%s</span>'
                     '<b class="%s">%s</b></div>'
                     % (i["name"], klasse, ("%." + str(nk) + "f") % i["wert"]))
        t.append("</div>")

    # Gruppen nach Monatsveraenderung
    # Bei fast allen Gruppen ist ein Anstieg schlecht fuer die Short-These.
    # Umgekehrt bei den chinesischen KI-Firmen: dort ist Staerke die
    # Bestaetigung. Die Farbe muss dieser Richtung folgen.
    UEBERSPRINGEN = ("Markt und Stress", "China Chipfertigung")
    UMGEKEHRT = ("China KI-Modelle und Software",)

    zeilen = []
    for name, info in gruppen_ansicht:
        if name in UEBERSPRINGEN:
            continue
        werte = [w.get("monat_prozent") for w in info["werte"]
                 if w.get("monat_prozent") is not None]
        if werte:
            zeilen.append((name, sum(werte) / len(werte), name in UMGEKEHRT))
    if zeilen:
        zeilen.sort(key=lambda z: -z[1])
        t.append('<div class="kern-titel" style="margin-top:16px">Gruppen, 1 Monat</div>'
                 '<table class="kern-tab">')
        for name, wert, umgekehrt in zeilen:
            t.append('<tr><td>%s</td><td class="z %s">%+.1f%%</td></tr>'
                     % (name, klasse_fuer(wert, umgekehrt), wert))
        t.append('</table><div class="kern-hinweis">Mittel der Gruppe gegenueber '
                 'dem Vormonat. Rot heisst gegen die These. Bei den chinesischen '
                 'KI-Firmen ist es umgekehrt: Staerke dort <b>stuetzt</b> die '
                 'These. Steht oben, wer das Geld ausgibt, und unten, wer es '
                 'einnimmt, verteilt der Markt die Marge um &ndash; das ist etwas '
                 'anderes als ein platzender Ausbau.</div>')

    if mit_steuerung:
        t.append(STEUERUNG)      # in der Mail waeren die Knoepfe wirkungslos
    t.append("</aside>")
    return "".join(t)


AUFFRISCHEN = """
<script>
(function () {
  // Die Seite wird alle zehn Minuten neu geschrieben. Statt manuell neu zu
  // laden, horcht sie auf den Bauzeitpunkt und holt sich die neue Fassung
  // selbst - aber nur, wenn sie gerade niemand benutzt.
  var eigener = null;
  var ORT = "ki-invest-scrollstand";

  var gemerkt = sessionStorage.getItem(ORT);
  if (gemerkt !== null) {
    sessionStorage.removeItem(ORT);
    window.addEventListener("load", function () {
      window.scrollTo(0, parseInt(gemerkt, 10) || 0);
    });
  }

  function stoert() {
    var fenster = document.getElementById("mehrfenster");
    if (fenster && fenster.open) { return true; }          // Fenster ist auf
    var a = document.activeElement;
    if (a && (a.tagName === "INPUT" || a.tagName === "SELECT")) { return true; }
    var leiste = document.getElementById("alarmleiste");
    if (leiste && !leiste.hidden) { return true; }          // Alarm sichtbar
    return false;
  }

  function pruefen() {
    fetch("/aktion/stand", { cache: "no-store" })
      .then(function (a) { return a.json(); })
      .then(function (z) {
        if (!z || !z.stand) { return; }
        if (eigener === null) { eigener = z.stand; return; }
        if (z.stand !== eigener && !stoert()) {
          sessionStorage.setItem(ORT, String(window.scrollY));
          location.reload();
        }
      })
      .catch(function () { /* ohne Server bleibt die Seite stehen */ });
  }

  pruefen();
  setInterval(pruefen, 20000);
})();
</script>
"""


ALARMSCHALTER = """
<div class="alarmleiste" id="alarmleiste" hidden>
  <span class="puls"></span>
  <span class="alarmtext"><b>Eilmeldung ausgeloest</b> &ndash; die Lampe blinkt,
   bis du sie abstellst.</span>
  <button type="button" id="alarmaus">Alarm abstellen</button>
</div>
<script>
(function () {
  var leiste = document.getElementById("alarmleiste");
  var knopf = document.getElementById("alarmaus");
  function pruefen() {
    fetch("/blink/status", { cache: "no-store" })
      .then(function (a) { return a.json(); })
      .then(function (z) { leiste.hidden = !z.blinkt; })
      .catch(function () { leiste.hidden = true; });
  }
  var erledigt = false;
  knopf.onclick = function () {
    knopf.disabled = true;
    knopf.textContent = "wird abgestellt \u2026";
    fetch("/blink/stopp", { cache: "no-store" })
      .then(function (a) { return a.json(); })
      .then(function (z) {
        erledigt = true;
        leiste.className = "alarmleiste erledigt";
        leiste.innerHTML = '<span class="haken">\u2713</span>' +
          '<span class="alarmtext"><b>Alarm abgestellt.</b> ' +
          'Die Lampe geht in ihren vorherigen Zustand zurueck.</span>';
        setTimeout(function () { leiste.hidden = true; erledigt = false; }, 12000);
      })
      .catch(function () {
        knopf.disabled = false;
        knopf.textContent = "Alarm abstellen";
      });
  };
  pruefen();
  setInterval(function () { if (!erledigt) { pruefen(); } }, 10000);
})();
</script>
"""


NAVIGATION = """
<nav class="blaettern" id="blaettern" hidden>
  <button type="button" id="zurueck" title="Aelterer Bericht (Pfeil links)"
          aria-label="Aelterer Bericht">&#8592;</button>
  <select id="auswahl" title="Bericht waehlen"></select>
  <button type="button" id="vor" title="Neuerer Bericht (Pfeil rechts)"
          aria-label="Neuerer Bericht">&#8594;</button>
  <span id="stelle" class="stelle"></span>
</nav>
<script>
(function () {
  var wurzel = document.currentScript.parentElement;
  var basis = wurzel.dataset.basis || "";
  var selbst = wurzel.dataset.datei || "";
  var nav = document.getElementById("blaettern");
  var zurueck = document.getElementById("zurueck");
  var vor = document.getElementById("vor");
  var auswahl = document.getElementById("auswahl");
  var stelle = document.getElementById("stelle");

  fetch(basis + "index.json", { cache: "no-store" })
    .then(function (a) { return a.json(); })
    .then(function (liste) {
      if (!liste || !liste.length) return;
      liste.sort(function (a, b) { return a.datei < b.datei ? 1 : -1; });  // neueste zuerst

      var hier = selbst
        ? liste.findIndex(function (e) { return e.datei === selbst; })
        : -1;

      // Die Startseite zwischen zwei Archiveintraegen hat selbst keinen
      // Dateinamen. Sie wird deshalb als eigener, aktueller Stand vorne
      // eingereiht - sonst zaehlte die Navigation an ihr vorbei.
      if (hier < 0) {
        var jetzt = (wurzel.textContent || "").match(/(\d{2}\.\d{2}\.\d{4}), (\d{2}:\d{2})/);
        liste.unshift({
          datei: "",
          beschriftung: jetzt ? jetzt[1] + ", " + jetzt[2] + " (aktuell)" : "aktuell",
          barometer: null
        });
        hier = 0;
      }
      if (liste.length < 2) return;

      liste.forEach(function (e, i) {
        var o = document.createElement("option");
        o.value = e.datei;
        o.textContent = e.beschriftung + (e.barometer != null ? "  \u00b7  " + e.barometer : "");
        if (i === hier) o.selected = true;
        auswahl.appendChild(o);
      });

      function hin(i) {
        if (i < 0 || i >= liste.length) return;
        var ziel = liste[i].datei;
        location.href = ziel ? basis + ziel : (basis ? "./" : "index.html");
      }
      zurueck.disabled = hier >= liste.length - 1;   // links = aelter
      vor.disabled = hier <= 0;                      // rechts = neuer
      zurueck.onclick = function () { hin(hier + 1); };
      vor.onclick = function () { hin(hier - 1); };
      auswahl.onchange = function () {
        var ziel = auswahl.value;
        location.href = ziel ? basis + ziel : (basis ? "./" : "index.html");
      };
      stelle.textContent = (hier + 1) + " von " + liste.length;
      document.addEventListener("keydown", function (e) {
        if (e.target.tagName === "SELECT") return;
        if (e.key === "ArrowLeft") { hin(hier + 1); }
        if (e.key === "ArrowRight") { hin(hier - 1); }
      });
      nav.hidden = false;
    })
    .catch(function () { /* ohne Archiv bleibt die Navigation verborgen */ });
})();
</script>
"""


def barometer_verlauf_balken(verlauf, breite=232, hoehe=54):
    """
    Verlauf des Barometers als Abweichung von der Mitte.

    Balken, die von unten wachsen, machen 60 und 68 ununterscheidbar und
    verstecken die eigentliche Aussage. Deshalb haengen sie hier an der
    Linie 50: nach oben heisst fuer die These, nach unten dagegen. Der
    Umschwung wird damit sichtbar statt nur die Faerbung.
    """
    if not verlauf or len(verlauf) < 2:
        return ""

    # Je Tag nur der letzte Stand, sonst verzerren mehrere Laeufe das Bild
    je_tag = {}
    for e in verlauf:
        je_tag[e.get("datum", "")] = e.get("wert", 50)
    punkte = list(je_tag.items())[-30:]
    if len(punkte) < 2:
        return ""

    mitte = hoehe / 2.0
    luecke = 2.0
    breite_balken = max(3.0, (breite - luecke * (len(punkte) - 1)) / len(punkte))

    t = ['<svg class="baroverlauf" viewBox="0 0 %d %d" width="%d" height="%d">'
         % (breite, hoehe, breite, hoehe)]
    t.append('<line x1="0" y1="%.1f" x2="%d" y2="%.1f" stroke="var(--rand)" '
             'stroke-width="1"/>' % (mitte, breite, mitte))

    for i, (tag, wert) in enumerate(punkte):
        x = i * (breite_balken + luecke)
        abweichung = (wert - 50) / 50.0                      # -1 bis +1
        laenge = max(1.5, abs(abweichung) * (mitte - 3))
        y = mitte - laenge if abweichung >= 0 else mitte
        farbe = "var(--gut)" if abweichung >= 0 else "var(--schlecht)"
        deckung = ".45" if i < len(punkte) - 1 else "1"
        t.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="1.5" '
                 'fill="%s" opacity="%s"><title>%s: %d</title></rect>'
                 % (x, y, breite_balken, laenge, farbe, deckung, tag, wert))

    t.append('<text x="0" y="%d" font-size="9" fill="var(--gedaempft)">%s</text>'
             % (hoehe - 1, punkte[0][0]))
    t.append('<text x="%d" y="%d" font-size="9" fill="var(--gedaempft)" '
             'text-anchor="end">heute</text>' % (breite, hoehe - 1))
    t.append("</svg>")
    return "".join(t)


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
.mailseite{max-width:760px;margin:0 auto}
.mailseite .kernbox{margin:0 0 14px}
.seite{max-width:1440px;margin:0 auto;display:grid;
 grid-template-columns:minmax(0,1fr) 304px;gap:22px;align-items:start}
.inhalt{min-width:0}
.rand{position:sticky;top:20px;max-height:calc(100vh - 40px);overflow-y:auto;
 scrollbar-width:thin}
@media(max-width:1080px){
 .seite{grid-template-columns:1fr}
 .rand{position:static;max-height:none}
}
h1{font-size:24px;margin:2px 0 2px;letter-spacing:-.01em}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.08em;
 color:var(--gedaempft);margin:34px 0 12px;font-weight:600}
h3{font-size:14px;margin:20px 0 8px;font-weight:600}
.kopf{color:var(--gedaempft);font-size:13px;display:flex;align-items:center;
 gap:12px;flex-wrap:wrap}
.blaettern{display:flex;align-items:center;gap:6px;margin-left:auto}
.blaettern button{font:inherit;font-size:14px;line-height:1;cursor:pointer;
 background:var(--flaeche);color:var(--text);border:1px solid var(--rand);
 border-radius:7px;padding:4px 10px}
.blaettern button:hover:not(:disabled){border-color:var(--akzent);
 color:var(--akzent)}
.blaettern button:disabled{opacity:.35;cursor:default}
.blaettern select{font:inherit;font-size:12.5px;background:var(--flaeche);
 color:var(--text);border:1px solid var(--rand);border-radius:7px;padding:4px 8px;
 max-width:260px}
.blaettern .stelle{font-size:11.5px;color:var(--gedaempft);white-space:nowrap}
/* Das Attribut "hidden" wirkt ueber die eingebaute Regel [hidden]{display:none}.
   Eine Klassenregel mit display waere staerker und wuerde sie aushebeln -
   deshalb hier ausdruecklich nachziehen. */
.alarmleiste[hidden], .blaettern[hidden]{display:none !important}
.alarmleiste{display:flex;align-items:center;gap:12px;background:#b91c1c;
 color:#fff;border-radius:11px;padding:13px 17px;margin:14px 0 4px;
 font-size:14px;box-shadow:0 2px 10px rgba(185,28,28,.3)}
.alarmleiste .alarmtext{flex:1}
.alarmleiste button{font:inherit;font-weight:650;cursor:pointer;background:#fff;
 color:#b91c1c;border:none;border-radius:8px;padding:8px 16px;white-space:nowrap}
.alarmleiste button:hover:not(:disabled){background:#ffe9e9}
.alarmleiste button:disabled{opacity:.6;cursor:default}
.puls{width:11px;height:11px;border-radius:50%;background:#fff;flex:none;
 animation:pulsieren 1.1s ease-in-out infinite}
.alarmleiste.erledigt{background:#15803d;box-shadow:0 2px 10px rgba(21,128,61,.28)}
.alarmleiste.erledigt .haken{font-size:17px;font-weight:700;flex:none}
@keyframes pulsieren{0%,100%{opacity:1}50%{opacity:.25}}
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
.fazit p.gemessen{font-size:14.5px;color:var(--text);line-height:1.58}
.fazit p.gemessen b{color:var(--text);font-weight:640}
.kernbox{background:var(--flaeche);border:1px solid var(--rand);border-radius:12px;
 padding:15px 16px;box-shadow:var(--schatten)}
.kern-titel{font-size:11px;text-transform:uppercase;letter-spacing:.07em;
 color:var(--gedaempft);font-weight:700;margin-bottom:5px}
.kern-haupt{padding-bottom:13px;border-bottom:1px solid var(--rand)}
.kern-wert{font-size:31px;font-weight:650;line-height:1.05;letter-spacing:-.02em;
 font-variant-numeric:tabular-nums;margin-bottom:5px}
.kern-wert .einheit{font-size:15px;font-weight:600;opacity:.7}
.kern-hinweis{font-size:11.5px;color:var(--gedaempft);line-height:1.45}
.kernskala{height:8px;border-radius:4px;margin:9px 0 4px;position:relative;
 background:linear-gradient(90deg,var(--schlecht) 0%,var(--flaeche2) 42%,
 var(--flaeche2) 58%,var(--gut) 100%)}
.kernskala i{position:absolute;top:-3px;width:3px;height:14px;border-radius:2px;
 background:var(--text)}
.kernskala-marken{display:flex;justify-content:space-between;font-size:9.5px;
 color:var(--gedaempft);margin-bottom:8px;letter-spacing:.02em}
.kern-liste{padding:11px 0;border-bottom:1px solid var(--rand)}
.kern-zeile{display:flex;justify-content:space-between;align-items:baseline;
 font-size:12.5px;padding:3px 0;gap:10px}
.kern-zeile b{font-variant-numeric:tabular-nums;font-weight:650}
.kern-tab{width:100%;border-collapse:collapse;font-size:12.5px;background:none;
 box-shadow:none;margin-bottom:9px}
.kern-tab td{padding:4px 0;border-bottom:1px solid var(--rand)}
.kern-tab tr:last-child td{border-bottom:none}
.kern-tab td.z{text-align:right;font-variant-numeric:tabular-nums;font-weight:650;
 white-space:nowrap}
.steuerung[hidden]{display:none !important}
.steuerung{border-top:1px solid var(--rand);margin-top:14px}
.steuerung button{display:block;width:100%;font:inherit;font-size:13px;
 font-weight:600;cursor:pointer;background:var(--akzent);color:#fff;border:none;
 border-radius:8px;padding:9px 12px;margin-bottom:6px;text-align:left}
.steuerung button:hover:not(:disabled){filter:brightness(1.08)}
.steuerung button:disabled{opacity:.5;cursor:default}
.steuerung button.leise{background:var(--flaeche2);color:var(--text);
 border:1px solid var(--rand);font-weight:500}
.steuerung button.aktiv{background:var(--warn)}
.vermerkfeld{display:flex;gap:5px;margin-top:9px}
.vermerkfeld input{flex:1;min-width:0;font:inherit;font-size:12.5px;
 background:var(--grund);color:var(--text);border:1px solid var(--rand);
 border-radius:8px;padding:8px 10px}
.vermerkfeld button{width:auto;margin:0;white-space:nowrap;padding:8px 12px}
.rueckmeldung{font-size:12px;line-height:1.45;border-radius:7px;padding:8px 11px;
 margin-top:9px}
.rueckmeldung[hidden]{display:none !important}
.rueckmeldung.gut{background:rgba(21,128,61,.12);color:var(--gut)}
.rueckmeldung.schlecht{background:rgba(185,28,28,.12);color:var(--schlecht)}
.mehrfenster{border:1px solid var(--rand);border-radius:14px;padding:0;
 max-width:520px;width:calc(100vw - 32px);background:var(--flaeche);
 color:var(--text);box-shadow:0 12px 40px rgba(0,0,0,.3)}
.mehrfenster::backdrop{background:rgba(0,0,0,.45)}
.mf-kopf{display:flex;justify-content:space-between;align-items:center;
 padding:15px 18px;border-bottom:1px solid var(--rand);font-size:15px}
.mf-kopf button{background:none;border:none;color:var(--gedaempft);font-size:22px;
 line-height:1;cursor:pointer;padding:0 4px}
.mf-kopf button:hover{color:var(--text)}
.mf-block{padding:14px 18px;border-bottom:1px solid var(--rand)}
.mf-block:last-of-type{border-bottom:none}
.mf-titel{font-size:11px;text-transform:uppercase;letter-spacing:.07em;
 color:var(--gedaempft);font-weight:700;margin-bottom:8px}
.mf-hinweis{font-size:11.5px;color:var(--gedaempft);line-height:1.45;margin:6px 0}
.mf-reihe{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.mf-reihe button{font:inherit;font-size:13px;font-weight:600;cursor:pointer;
 background:var(--flaeche2);color:var(--text);border:1px solid var(--rand);
 border-radius:8px;padding:8px 13px}
.mf-reihe button:hover:not(:disabled){border-color:var(--akzent);color:var(--akzent)}
.mf-reihe button:disabled{opacity:.5;cursor:default}
.mf-reihe button.zu{background:var(--warn);color:#fff;border-color:transparent}
.mf-reihe input{flex:1;min-width:140px;font:inherit;font-size:13px;
 background:var(--grund);color:var(--text);border:1px solid var(--rand);
 border-radius:8px;padding:8px 11px}
.mf-ausgabe{margin-top:10px;padding:11px 13px;background:var(--grund);
 border:1px solid var(--rand);border-radius:9px;font-size:12.5px;line-height:1.6;
 max-height:260px;overflow-y:auto;white-space:pre-line}
.mf-ausgabe[hidden]{display:none !important}
.mehrfenster .rueckmeldung{margin:0 18px 16px}

.wertkarte{background:var(--flaeche);border:1px solid var(--rand);border-radius:12px;
 padding:14px 16px 12px;margin:16px 0 4px;box-shadow:var(--schatten)}
.wertchart{display:block;width:100%;height:auto;overflow:visible}
.legende{display:flex;flex-wrap:wrap;gap:16px;margin:10px 0 6px;font-size:13px;
 align-items:center}
.legende .bein{display:flex;align-items:center;gap:6px}
.legende .bein i{width:11px;height:3px;border-radius:2px;display:inline-block}
.legende .gesamt{margin-left:auto;padding-left:16px;border-left:1px solid var(--rand)}
.korrektur{background:var(--flaeche2);border:1px dashed var(--akzent);border-radius:10px;
 padding:12px 15px;margin-bottom:11px;font-size:13px;line-height:1.5}
.korrektur b{color:var(--akzent)}
.alt{font-size:10px;text-transform:uppercase;letter-spacing:.05em;
 background:var(--flaeche2);color:var(--gedaempft);border-radius:3px;
 padding:1px 5px;margin-right:6px;font-weight:600}
.secauszug{margin-top:9px;padding:10px 13px;background:var(--flaeche2);
 border-radius:8px;font-size:12.5px;line-height:1.55;color:var(--text);
 max-height:200px;overflow-y:auto}
.notiz{background:var(--flaeche2);border-left:4px solid var(--akzent);
 border-radius:9px;padding:12px 16px;margin:14px 0 4px;font-size:14px;
 line-height:1.55}
.ruhehinweis{background:var(--flaeche2);border:1px dashed var(--gedaempft);
 border-radius:9px;padding:10px 15px;margin:14px 0 4px;font-size:13px;
 color:var(--gedaempft)}
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
.baroverlauf{display:block;overflow:visible}
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
                  barometer_verlauf=None, fuer_mail=False,
                  archiv_datei=None, archiv_basis=""):
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
             '<body>%s' % (STIL, '<div class="mailseite">' if fuer_mail
                              else '<div class="seite"><div class="inhalt">'))

    t.append('<div class="kopf" data-basis="%s" data-datei="%s">%s%s%s</div>'
             '<h1>KI-Invest Monitor</h1>'
             % (html_schuetzen(archiv_basis), html_schuetzen(archiv_datei or ""),
                jetzt.strftime("%A, %d.%m.%Y, %H:%M Uhr"), limit_text,
                "" if fuer_mail else NAVIGATION))
    if not fuer_mail:
        t.append(ALARMSCHALTER)
        t.append(AUFFRISCHEN)

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

    # ---- Hinweis auf eine laufende Stummschaltung
    if ruhe_aktiv(konfig):
        try:
            bis = datetime.fromisoformat(konfig["ruhe_bis"])
            t.append('<div class="ruhehinweis">Alarme sind bis <b>%s Uhr</b> '
                     'stummgeschaltet. Die Ueberwachung laeuft weiter.</div>'
                     % bis.strftime("%d.%m., %H:%M"))
        except (TypeError, ValueError):
            pass

    # ---- Vermerk, falls einer gesetzt ist
    notiz = konfig.get("notiz")
    if isinstance(notiz, dict) and notiz.get("text"):
        t.append('<div class="notiz"><b>Vermerk</b> &middot; '
                 '<span class="klein">seit %s</span><br>%s</div>'
                 % (html_schuetzen(notiz.get("seit", "")),
                    html_schuetzen(notiz["text"])))

    # ---- Wertverlauf der Positionen
    grafik = wertverlauf_grafik([p.get("wertverlauf") for p in positionen])
    if grafik:
        t.append(grafik)

    # In der Mail steht der Kernindikator-Kasten direkt unter dem Graphen:
    # E-Mail-Programme koennen das Rasterlayout nicht, dort wuerde die rechte
    # Spalte sonst ans Ende der Nachricht rutschen.
    if fuer_mail:
        t.append(kernbox(indikatoren, gruppen_ansicht, mit_steuerung=False))

    # ---- Zusammenfassung in Worten
    claude_saetze = []
    if claude_urteil and not claude_urteil.get("fehler"):
        claude_saetze = claude_urteil.get("zusammenfassung") or []

    if claude_saetze or zusammenfassung:
        t.append('<div class="fazit">')
        if claude_saetze:
            for satz in claude_saetze:
                t.append("<p>%s</p>" % html_schuetzen(satz))
            t.append('<div class="quelle">Einordnung von Claude%s &middot; '
                     'die gemessenen Werte darunter</div>'
                     % (" von " + html_schuetzen(claude_urteil["_stand"])
                        if claude_urteil.get("_stand") else ""))
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
            stand = claude_urteil.get("_stand")
            t.append('<div class="claude">')
            if stand:
                t.append('<div class="klein" style="margin:0 0 9px">'
                         'Einordnung von %s. Die Messwerte darueber sind aktuell.'
                         '</div>' % html_schuetzen(stand))
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
    if (claude_urteil and not claude_urteil.get("fehler")
            and claude_urteil.get("uebersehen")):
        t.append('<div class="korrektur"><b>Vorab, von Claude geprueft:</b> %s</div>'
                 % html_schuetzen(claude_urteil["uebersehen"]))
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
             "<th class='z'>bis Stop</th>"
             "<th class='z'>Puffer</th><th class='z'>Drag/Woche</th></tr>")
    for p in positionen:
        puffer = p.get("barriere_abstand")
        pk = "neutral"
        if puffer is not None:
            pk = "schlecht" if puffer < 20 else ("warn" if puffer < 30 else "gut")
        t.append("<tr><td>%s</td><td class='klein'>%s</td><td>%s</td>"
                 "<td class='z'>%.2f</td><td class='z %s'>%s</td>"
                 "<td class='z %s'>%s</td><td class='z %s'>%s</td>"
                 "<td class='z %s'>%s</td><td class='z %s'>%s</td>"
                 "<td class='z neutral'>%s</td></tr>" % (
                     p["name"], p.get("wkn", ""), sparkline(p.get("verlauf")),
                     p["kurs"],
                     klasse_fuer(p["tag_prozent"]), zahl(p["tag_prozent"], 2, "%"),
                     klasse_fuer(p["schein_tag_prozent"], True),
                     zahl(p["schein_tag_prozent"], 2, "%"),
                     klasse_fuer(p.get("schein_seit_einstieg"), True),
                     zahl(p.get("schein_seit_einstieg"), 1, "%"),
                     ("schlecht" if (p.get("abstand_verlustschwelle") or -99) > -12
                      else "warn" if (p.get("abstand_verlustschwelle") or -99) > -22
                      else "neutral"),
                     zahl(p.get("abstand_verlustschwelle"), 1, "%"),
                     pk, ("%.1f%%" % puffer) if puffer is not None else "&ndash;",
                     zahl(p.get("drag_woche_prozent"), 1, "%")))
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
    veraltet_anzahl = konfig.get("_verworfen", 0)
    if veraltet_anzahl:
        t.append('<div class="klein" style="margin-bottom:8px">%d aeltere Meldungen '
                 'wurden aussortiert, weil sie den Filter fuer das '
                 'Veroeffentlichungsdatum nicht bestanden haben.</div>' % veraltet_anzahl)
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

    # ---- Token-Preise
    token = (konfig.get("_tokenpreise") or {})
    if token.get("modelle"):
        v = token.get("veraenderung")
        t.append("<h2>Preis je Million Token</h2>")
        t.append('<div class="klein" style="margin-bottom:8px">Der direkte '
                 'Messwert fuer die Effizienzseite der These. Fallen die Preise '
                 'schnell, wird Rechenleistung entwertet.%s</div>'
                 % (" Aenderung seit %s: <b>%+.1f%%</b>." % (token["vergleich"], v)
                    if v is not None else " Noch kein Vergleichsstand."))
        t.append("<div class='tabelle'><table><tr><th>Anbieter</th><th>Modell</th>"
                 "<th>Land</th><th class='z'>Eingabe</th><th class='z'>Ausgabe</th>"
                 "<th>Bemerkung</th></tr>")
        for m in sorted(token["modelle"], key=lambda x: x["ausgabe"]):
            t.append("<tr><td>%s</td><td>%s%s</td><td class='klein'>%s</td>"
                     "<td class='z'>%.2f</td><td class='z'><b>%.2f</b></td>"
                     "<td class='klein'>%s</td></tr>"
                     % (html_schuetzen(m["anbieter"]), html_schuetzen(m["modell"]),
                        " &#9733;" if m.get("spitzenklasse") else "",
                        html_schuetzen(m.get("land", "")),
                        m["eingabe"], m["ausgabe"],
                        html_schuetzen(m.get("bemerkung", ""))))
        t.append("</table></div>")
        t.append('<div class="klein" style="margin-top:8px">Preise in US-Dollar je '
                 'Million Token. Ein Stern kennzeichnet die Spitzenklasse, aus der '
                 'der Durchschnitt gebildet wird. Stand der Liste: %s. Pflege ueber '
                 '<code>tokenpreise</code> in der Konfiguration.</div>'
                 % html_schuetzen(token.get("stand", "?")))

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
    for s in sec[:14]:
        t.append('<div class="karte %s"><a href="%s">%s</a><div class="klein">'
                 '%s &middot; Punkte %s</div>%s</div>'
                 % ("hinweis" if s.get("wichtig") else "",
                    html_schuetzen(s.get("link", "")), html_schuetzen(s["titel"]),
                    html_schuetzen(s.get("datum", "")),
                    html_schuetzen(", ".join(s.get("punkte", [])) or "-"),
                    ('<div class="secauszug">%s</div>'
                     % html_schuetzen(s["auszug"][:900])) if s.get("auszug") else ""))

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
    if fuer_mail:
        t.append("</div></body></html>")            # Ende .mailseite
    else:
        t.append("</div>")                          # Ende .inhalt
        t.append('<aside class="rand">%s</aside>'
                 % kernbox(indikatoren, gruppen_ansicht))
        t.append("</div></body></html>")            # Ende .seite
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
        if pos.get("geschlossen"):
            continue                      # als verkauft markiert
        daten = hole(pos["ticker"])
        if daten.get("fehler"):
            fehler.append("Position %s ohne Kurs" % pos.get("name", "?"))
            continue
        # Echten Scheinkurs holen; er hat Vorrang vor jeder Ableitung.
        # Schlaegt der Abruf fehl, greift der in der Konfiguration hinterlegte Wert.
        gestellt = scheinkurs_holen(pos["isin"], kennung) if pos.get("isin") else None
        if gestellt:
            if gestellt.get("geld"):
                pos = dict(pos, kurs_aktuell=gestellt["geld"])
            if gestellt.get("spread_prozent") is not None:
                pos["spread_prozent"] = gestellt["spread_prozent"]
            pos["kurs_quelle"] = "abgerufen"
        else:
            fehler.append("Scheinkurs %s nicht abrufbar" % pos.get("wkn", "?"))
            pos = dict(pos, kurs_quelle="Konfiguration")

        ausgewertet = position_auswerten(pos, daten)
        ausgewertet["wertverlauf"] = positionswert_verlauf(pos, daten, hole("EURUSD=X"))
        ausgewertet["kurs_quelle"] = pos.get("kurs_quelle")
        ausgewertet["scheinkurs"] = pos.get("kurs_aktuell")
        positionen.append(ausgewertet)

    gute_kurse = {k: v for k, v in kurse.items() if not v.get("fehler")}

    # Risikoaufschlag von der Notenbank, statt ihn aus Aktienkursen zu schaetzen
    zusatz = {}
    token = tokenpreise_auswerten(konfig)
    if token:
        zusatz["tokenpreise"] = token

    reihe = fred_reihe(kennung)
    if len(reihe) > 25:
        jetzt = reihe[-1][1]
        zusatz["hochzins_aufschlag"] = {
            "jetzt": jetzt,
            "woche": jetzt - reihe[-6][1],
            "monat": jetzt - reihe[-22][1],
            "stand": reihe[-1][0],
        }
    else:
        fehler.append("Risikoaufschlag (FRED) nicht abrufbar")

    indikatoren = indikatoren_bauen(gute_kurse, gruppen, zusatz)

    gruppen_ansicht = []
    for name, info in gruppen.items():
        gruppen_ansicht.append((name, {
            "rolle": info.get("rolle", ""),
            "werte": [kurse[t] for t in info.get("ticker", []) if t in kurse],
        }))

    # Nachrichten
    fuer_these = konfig.get("news_stichworte_these_bestaetigt", [])
    gegen_these = konfig.get("news_stichworte_these_gefaehrdet", [])
    nachrichten, gesehen, verworfen = [], set(), []

    hoechstalter = konfig.get("nachrichten_hoechstalter_tage", 14)

    def aufnehmen(eintraege, thema=""):
        for e in eintraege:
            schluessel = e["titel"][:110].lower()
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            e["thema"] = thema
            alter_bestimmen(e, hoechstalter)
            if e["veraltet"]:
                verworfen.append(e)
                continue
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
            alter_bestimmen(b, hoechstalter * 3)   # Fachbeitraege altern langsamer
            if b["veraltet"]:
                verworfen.append(b)
                continue
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
    if not mit_claude:
        claude_urteil = claude_letzte()      # letzte Einordnung weiterverwenden
    if mit_claude:
        claude_urteil = claude_fragen(konfig, positionen, indikatoren, barometer,
                                      nachrichten, regierung, blogs, sec,
                                      zusatz.get("tokenpreise"))

    if mit_claude:
        if claude_urteil and not claude_urteil.get("fehler"):
            claude_sichern(claude_urteil)
        else:
            # Scheitert der Aufruf, bleibt die letzte brauchbare Einordnung
            # stehen. Eine Fehlermeldung anstelle einer Einschaetzung waere
            # schlechter als eine etwas aeltere Einschaetzung.
            vorherige = claude_letzte()
            if vorherige:
                grund = (claude_urteil or {}).get("fehler", "unbekannt")
                log_schreiben("Claude fehlgeschlagen (%s), behalte Einordnung "
                              "von %s" % (str(grund)[:70],
                                          vorherige.get("_stand", "?")))
                vorherige = dict(vorherige)
                vorherige["_letzter_versuch"] = datetime.now().strftime("%H:%M")
                claude_urteil = vorherige

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
        "verworfen": len(verworfen), "tokenpreise": zusatz.get("tokenpreise"),
    }


def verzeichnis_schreiben(archiv, neue_datei, d, hoechstzahl=90):
    """
    Fuehrt das Verzeichnis der archivierten Berichte. Die Navigation liest es,
    damit auch aeltere Seiten die jeweils passenden Nachbarn kennen, ohne dass
    sie neu geschrieben werden muessten.
    """
    pfad = os.path.join(archiv, "index.json")
    liste = json_laden(pfad, [])
    liste = [e for e in liste if e.get("datei") != neue_datei]

    jetzt = datetime.now()
    reihen = [p.get("wertverlauf") for p in d.get("positionen", []) if p.get("wertverlauf")]
    gesamt = sum(r["punkte"][-1]["wert"] for r in reihen) if reihen else None

    liste.append({
        "datei": neue_datei,
        "beschriftung": jetzt.strftime("%d.%m.%Y, %H:%M"),
        "barometer": d["barometer"][0],
        "wert_eur": round(gesamt, 2) if gesamt is not None else None,
    })
    liste.sort(key=lambda e: e["datei"], reverse=True)

    # Alte Berichte auch von der Platte nehmen
    for veraltet in liste[hoechstzahl:]:
        try:
            os.remove(os.path.join(archiv, veraltet["datei"]))
        except OSError:
            pass
    liste = liste[:hoechstzahl]

    json_speichern(pfad, liste)
    return liste


def hue_signal(konfig, kritisch=True):
    """
    Laesst die Lampen bei einer Eilmeldung blinken - rot bei kritisch,
    orange sonst. Der vorherige Zustand wird gesichert und danach wieder
    hergestellt, damit die Beleuchtung nicht verstellt bleibt.

    Nutzt die Hue-API Version 1 ueber HTTPS. Das Zertifikat der Bridge ist
    selbst signiert, deshalb wird es hier bewusst nicht geprueft - es geht
    um ein Geraet im eigenen Netz, nicht um eine Internetverbindung.
    """
    einst = konfig.get("hue", {})
    if not einst.get("aktiv"):
        return False

    bridge = einst.get("bridge")
    lampen = einst.get("lampen") or []
    if not bridge or not lampen:
        return False

    schluessel = einst.get("schluessel")
    if not schluessel and einst.get("schluessel_datei"):
        try:
            with open(einst["schluessel_datei"]) as f:
                schluessel = f.read().strip()
        except IOError:
            return False
    if not schluessel:
        return False

    ohne_pruefung = ssl.create_default_context()
    ohne_pruefung.check_hostname = False
    ohne_pruefung.verify_mode = ssl.CERT_NONE
    stamm = "https://%s/api/%s/lights/" % (bridge, schluessel)

    def anfrage(pfad, daten=None, methode="GET"):
        koerper = json.dumps(daten).encode() if daten is not None else None
        req = urllib.request.Request(stamm + pfad, data=koerper, method=methode,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=8,
                                        context=ohne_pruefung) as antwort:
                return json.loads(antwort.read().decode())
        except Exception:                                        # noqa: BLE001
            return None

    # Zustand sichern
    vorher = {}
    for nr in lampen:
        info = anfrage(str(nr))
        if isinstance(info, dict) and "state" in info:
            z = info["state"]
            merken = {"on": z.get("on", False), "bri": z.get("bri", 200)}
            for feld in ("hue", "sat", "ct"):
                if feld in z:
                    merken[feld] = z[feld]
            vorher[nr] = (merken, "hue" in z)

    # Signal setzen
    farbton = einst.get("hue_kritisch", 0) if kritisch else einst.get("hue_hoch", 6000)
    for nr, (_, kann_farbe) in vorher.items():
        neuer = {"on": True, "bri": 254, "alert": "lselect"}
        if kann_farbe:
            neuer.update({"hue": farbton, "sat": 254})
        else:
            neuer["ct"] = 153 if kritisch else 400      # kalt bzw. warm
        anfrage("%d/state" % nr, neuer, "PUT")

    dauer = einst.get("dauer_sekunden", 16 if kritisch else 9)
    time.sleep(dauer)

    # Zustand zuruecksetzen
    for nr, (merken, _) in vorher.items():
        zurueck = dict(merken)
        zurueck["alert"] = "none"
        anfrage("%d/state" % nr, zurueck, "PUT")

    log_schreiben("Hue: %d Lampen signalisiert (%s)"
                  % (len(vorher), "kritisch" if kritisch else "hoch"))
    return True


def telegram_daten(konfig):
    """Token und Chat-Kennung aus Dateien lesen - beide gehoeren nicht in die
    Konfiguration, damit sie nicht versehentlich im Repo landen."""
    einst = konfig.get("telegram", {})
    if not einst.get("aktiv"):
        return None, None

    def lesen(wert, datei):
        if wert:
            return wert
        if datei and os.path.exists(datei):
            with open(datei) as f:
                return f.read().strip()
        return None

    return (lesen(einst.get("token"), einst.get("token_datei")),
            lesen(einst.get("chat"), einst.get("chat_datei")))


def telegram_senden(konfig, text, still=False):
    """Textnachricht an Telegram. Fett und kursiv ueber HTML-Auszeichnung."""
    token, chat = telegram_daten(konfig)
    if not token or not chat:
        return False
    daten = urllib.parse.urlencode({
        "chat_id": chat, "text": text[:4000], "parse_mode": "HTML",
        "disable_web_page_preview": "true",
        "disable_notification": "true" if still else "false",
    }).encode()
    try:
        with urllib.request.urlopen(
                "https://api.telegram.org/bot%s/sendMessage" % token,
                data=daten, timeout=20) as antwort:
            json.loads(antwort.read())
        log_schreiben("Telegram: Nachricht verschickt")
        return True
    except Exception as fehler:                                  # noqa: BLE001
        log_schreiben("Telegram fehlgeschlagen: %s" % fehler)
        return False


def telegram_datei(konfig, inhalt, dateiname, beschriftung="", still=True):
    """Haengt eine Datei als Dokument an - der Bericht wird so im Chat
    dauerhaft ablegbar, nicht nur ein Link auf fremde Server."""
    token, chat = telegram_daten(konfig)
    if not token or not chat:
        return False
    if isinstance(inhalt, str):
        inhalt = inhalt.encode("utf-8")

    grenze = "----------KIInvest%s" % datetime.now().strftime("%H%M%S%f")
    teile = []

    def feld(name, wert):
        teile.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                      % (grenze, name, wert)).encode("utf-8"))

    feld("chat_id", chat)
    if beschriftung:
        feld("caption", beschriftung[:1000])
        feld("parse_mode", "HTML")
    feld("disable_notification", "true" if still else "false")
    teile.append(("--%s\r\nContent-Disposition: form-data; name=\"document\"; "
                  "filename=\"%s\"\r\nContent-Type: text/html\r\n\r\n"
                  % (grenze, dateiname)).encode("utf-8"))
    teile.append(inhalt)
    teile.append(("\r\n--%s--\r\n" % grenze).encode("utf-8"))
    koerper = b"".join(teile)

    req = urllib.request.Request(
        "https://api.telegram.org/bot%s/sendDocument" % token, data=koerper,
        headers={"Content-Type": "multipart/form-data; boundary=%s" % grenze})
    try:
        with urllib.request.urlopen(req, timeout=60) as antwort:
            json.loads(antwort.read())
        log_schreiben("Telegram: %s angehaengt (%d KB)"
                      % (dateiname, len(inhalt) // 1024))
        return True
    except Exception as fehler:                                  # noqa: BLE001
        log_schreiben("Telegram-Anhang %s fehlgeschlagen: %s" % (dateiname, fehler))
        return False


def ntfy_datei_senden(konfig, inhalt, dateiname, titel, text,
                      kritisch=True, verweis=None, leise=False):
    """
    Wie ntfy_senden, haengt aber eine Datei an. Der Inhalt wird zu ntfy
    hochgeladen, damit er auch ausserhalb des Heimnetzes lesbar ist - ein
    Verweis auf die NAS-Adresse waere unterwegs wertlos.
    """
    einst = konfig.get("ntfy", {})
    if not einst.get("aktiv") or not einst.get("kanal"):
        return False

    if isinstance(inhalt, str):
        inhalt = inhalt.encode("utf-8")

    # Kopfzeilen duerfen keine echten Zeilenumbrueche enthalten. ntfy setzt
    # die Zeichenfolge Backslash-n selbst wieder in Umbrueche um.
    einzeilig = text.replace("\r", "").replace("\n", "\\n")

    kopf = {
        "Title": titel.replace("\n", " ").encode("utf-8"),
        "Message": einzeilig.encode("utf-8"),
        "Filename": dateiname,
        "Priority": "min" if leise else ("urgent" if kritisch else "high"),
        "Tags": "page_facing_up" if leise else
                ("rotating_light" if kritisch else "warning"),
    }
    if verweis:
        kopf["Click"] = verweis

    url = "%s/%s" % (einst.get("server", "https://ntfy.sh").rstrip("/"),
                     einst["kanal"])
    req = urllib.request.Request(url, data=inhalt, headers=kopf, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=45) as antwort:
            antwort.read()
        log_schreiben("ntfy: %s angehaengt (%d KB)"
                      % (dateiname, len(inhalt) // 1024))
        return True
    except Exception as fehler:                                  # noqa: BLE001
        log_schreiben("ntfy-Anhang %s fehlgeschlagen: %s" % (dateiname, fehler))
        return False


def ntfy_senden(konfig, titel, text, kritisch=True, verweis=None):
    """
    Schickt eine Push-Nachricht ueber ntfy aufs Telefon.

    Der Kanalname ist das einzige Geheimnis - wer ihn kennt, kann mitlesen
    und senden. Deshalb ist er zufaellig gewaehlt und steht nur in der
    Konfiguration auf dem Pi.
    """
    einst = konfig.get("ntfy", {})
    if not einst.get("aktiv"):
        return False
    kanal = einst.get("kanal")
    if not kanal:
        return False

    kopf = {
        "Title": titel.encode("utf-8"),
        "Priority": "urgent" if kritisch else "high",
        "Tags": "rotating_light" if kritisch else "warning",
        "Markdown": "no",
    }
    if verweis:
        kopf["Click"] = verweis

    url = "%s/%s" % (einst.get("server", "https://ntfy.sh").rstrip("/"), kanal)
    req = urllib.request.Request(url, data=text.encode("utf-8"),
                                 headers=kopf, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as antwort:
            antwort.read()
        log_schreiben("ntfy verschickt (%s)" % ("dringend" if kritisch else "hoch"))
        return True
    except Exception as fehler:                                  # noqa: BLE001
        log_schreiben("ntfy fehlgeschlagen: %s" % fehler)
        return False


def dauerblinken_starten(alarmtext=""):
    """Startet das Dauersignal als eigenstaendigen Vorgang, damit es den
    Monitorlauf nicht blockiert. Laeuft dann, bis es abgestellt wird."""
    skript = os.path.join(BASIS, "hue_blink.py")
    if not os.path.exists(skript):
        return False
    # Text fuer die Wiedervorlagen hinterlegen, damit die Erinnerungen
    # denselben Sachverhalt nennen wie die Erstmeldung.
    try:
        with open(os.path.join(BASIS, "alarm.txt"), "w") as f:
            f.write(alarmtext or "")
    except IOError:
        pass
    if os.path.exists(os.path.join(BASIS, "blink.laeuft")):
        log_schreiben("Dauerblinken laeuft bereits")
        return True
    try:
        subprocess.Popen([sys.executable, skript], cwd=BASIS,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        log_schreiben("Dauerblinken gestartet")
        return True
    except OSError as fehler:
        log_schreiben("Dauerblinken nicht startbar: %s" % fehler)
        return False


def ruhe_aktiv(konfig):
    """Waehrend der Stummschaltung wird nichts ausgeloest. Die Ueberwachung
    laeuft weiter, nur Lampe, Telegram und Eilmail schweigen."""
    bis = konfig.get("ruhe_bis")
    if not bis:
        return False
    try:
        return datetime.now() < datetime.fromisoformat(bis)
    except (TypeError, ValueError):
        return False


def feste_schwellen_pruefen(konfig, positionen, indikatoren, termine):
    """
    Prueft harte Schwellen, ohne Claude zu fragen.

    Die Einordnung laeuft nur zur vollen Stunde. Die Zwischenlaeufe haben
    frische Kurse, konnten aber bisher nichts ausloesen - hier ist das Netz
    darunter. Gibt eine Liste von Treffern zurueck.
    """
    einst = konfig.get("alarmschwellen") or {}
    if not einst.get("aktiv"):
        return []

    fuer = einst.get("fuer_these", {})
    gegen = einst.get("gegen_these", {})
    struktur = einst.get("strukturell", {})
    treffer = []

    def merken(richtung, stufe, text, zahl):
        treffer.append({"richtung": richtung, "stufe": stufe,
                        "text": text, "zahl": zahl})

    nach_name = {i["name"]: i for i in indikatoren}

    for p in positionen:
        name = "%s (%s)" % (p["name"], p.get("wkn", ""))
        schein = p.get("schein_tag_prozent")
        tag = p.get("tag_prozent")

        if schein is not None and schein >= fuer.get("schein_gewinn_tag_prozent", 25):
            merken("fuer", "hoch",
                   "%s gewinnt heute %.1f Prozent" % (name, schein),
                   "%s: %+.1f%% im Schein" % (p.get("wkn", ""), schein))
        if schein is not None and schein <= -abs(gegen.get("schein_verlust_tag_prozent", 20)):
            merken("gegen", "kritisch",
                   "%s verliert heute %.1f Prozent" % (name, abs(schein)),
                   "%s: %.1f%% im Schein" % (p.get("wkn", ""), schein))

        if tag is not None and tag <= -abs(fuer.get("basiswert_sturz_tag_prozent", 8)):
            merken("fuer", "hoch",
                   "%s faellt um %.1f Prozent" % (p["ticker"], abs(tag)),
                   "%s: %+.2f%%" % (p["ticker"], tag))
        if tag is not None and tag >= fuer.get("basiswert_sturz_tag_prozent", 8):
            merken("gegen", "kritisch",
                   "%s steigt um %.1f Prozent" % (p["ticker"], tag),
                   "%s: %+.2f%%" % (p["ticker"], tag))

        abstand = p.get("abstand_verlustschwelle")
        if abstand is not None and abstand > -abs(gegen.get("abstand_stop_unter_prozent", 12)):
            merken("gegen", "kritisch",
                   "%s ist nur noch %.1f Prozent von der Stop-Marke entfernt"
                   % (name, abs(abstand)),
                   "%s: %.1f%% bis Stop" % (p.get("wkn", ""), abstand))

        puffer = p.get("barriere_abstand")
        if puffer is not None and puffer < gegen.get("barriere_puffer_unter_prozent", 25):
            merken("gegen", "kritisch",
                   "%s hat nur noch %.1f Prozent Barriere-Puffer" % (name, puffer),
                   "%s: Puffer %.1f%%" % (p.get("wkn", ""), puffer))

        z = p.get("z_wert")
        if (z is not None and abs(z) >= gegen.get("z_wert_ueber", 3.0)
                and (tag or 0) > 0):
            merken("gegen", "hoch",
                   "%s bewegt sich das %.1f-fache der ueblichen Tagesschwankung "
                   "gegen die Position" % (p["ticker"], abs(z)),
                   "%s: Z = %.1f" % (p["ticker"], z))

    aufschlag = nach_name.get("Hochzins-Risikoaufschlag")
    if aufschlag:
        monat = aufschlag.get("veraenderung_monat", 0.0)
        if monat >= fuer.get("risikoaufschlag_monat_bp", 50):
            merken("fuer", "kritisch",
                   "Der Hochzins-Risikoaufschlag hat sich im Monat um %.0f "
                   "Basispunkte ausgeweitet" % monat,
                   "Risikoaufschlag: %.0f Bp (%+.0f im Monat)"
                   % (aufschlag["wert"], monat))

    vix = nach_name.get("VIX-Terminstruktur")
    if vix and vix["wert"] > fuer.get("vix_struktur_ueber", 1.0):
        merken("fuer", "hoch",
               "Die Volatilitaets-Terminstruktur steht bei %.2f und damit in "
               "Backwardation - akuter Marktstress" % vix["wert"],
               "VIX / VIX3M: %.2f" % vix["wert"])

    neo = nach_name.get("Neocloud-Relativstaerke")
    if neo and neo["wert"] <= fuer.get("neocloud_relativstaerke_unter", -15):
        merken("fuer", "hoch",
               "Die Neoclouds liegen %.1f Punkte hinter dem Nasdaq - die "
               "schuldenfinanzierte Seite bricht zuerst" % abs(neo["wert"]),
               "Neocloud-Relativstaerke: %.1f Punkte" % neo["wert"])

    heute = date.today()
    for termin in termine:
        try:
            tag_ = datetime.strptime(termin["datum"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        rest = (tag_ - heute).days
        if 0 <= rest <= struktur.get("termin_in_tagen", 1):
            merken("neutral", "hoch",
                   "Termin %s: %s" % ("heute" if rest == 0 else "morgen",
                                      termin["was"]),
                   termin["was"])

    if konfig.get("zeitlimit_bis"):
        try:
            limit = datetime.strptime(konfig["zeitlimit_bis"], "%Y-%m-%d").date()
            rest = (limit - heute).days
            if 0 <= rest <= struktur.get("zeitlimit_in_tagen", 3):
                merken("neutral", "hoch",
                       "Das Zeitlimit ist in %d Tagen erreicht" % rest,
                       "Zeitlimit: %s" % limit.strftime("%d.%m."))
        except ValueError:
            pass

    return treffer


def schwellen_alarm(konfig, d, zustand):
    """Baut aus den Schwellentreffern eine Eilmeldung und verschickt sie."""
    treffer = feste_schwellen_pruefen(konfig, d.get("positionen", []),
                                      d.get("indikatoren", []),
                                      konfig.get("termine", []))
    if not treffer:
        return False

    kritisch = any(t["stufe"] == "kritisch" for t in treffer)
    dafuer = [t for t in treffer if t["richtung"] == "fuer"]
    dagegen = [t for t in treffer if t["richtung"] == "gegen"]
    haupt = (dagegen or dafuer or treffer)[0]

    if dagegen:
        warum = ("Die Position ist unter Druck. Das ist keine Deutung, sondern "
                 "eine gerissene Schwelle - pruefe, ob deine Ausstiegsregel greift.")
        schritte = ("Position pruefen, Stop-Marke nachziehen, oder bewusst "
                    "aussitzen. Der Bericht zeigt die Zahlen dazu.")
    elif dafuer:
        warum = ("Das Umfeld arbeitet gerade stark fuer die These. Eine "
                 "Gewinnmitnahme oder das Nachziehen der Stop-Marke waere zu "
                 "erwaegen.")
        schritte = ("Teilgewinn mitnehmen, Stop nachziehen, oder laufen lassen "
                    "bis zum Zeitlimit.")
    else:
        warum = "Ein hinterlegter Termin steht an."
        schritte = "Vorher entscheiden, ob die Position ueber den Termin laeuft."

    d = dict(d)
    d["claude"] = {"eilmeldung": {
        "noetig": True,
        "stufe": "kritisch" if kritisch else "hoch",
        "ausloeser": "Feste Schwelle, ohne Einordnung ausgeloest",
        "betreff": haupt["text"][:70],
        "schlagzeile": haupt["text"],
        "was_geschehen_ist": " ".join(t["text"] + "." for t in treffer[:4]),
        "warum_es_zaehlt": warum,
        "was_du_tun_koenntest": schritte,
        "zahlen": [t["zahl"] for t in treffer[:6]],
    }}
    return eilmeldung_verschicken(konfig, d, zustand)


def eilmeldung_verschicken(konfig, d, zustand):
    """
    Sofortmail bei Ereignissen, die nicht bis zum Abendbericht warten koennen.
    Inhalt und Betreff stammen von Claude, die Form von hier. Jede Meldung
    geht nur einmal raus - der Ausloeser wird im Zustand vermerkt.
    """
    urteil = d.get("claude") or {}
    eil = urteil.get("eilmeldung") or {}
    if not isinstance(eil, dict) or not eil.get("noetig"):
        return False

    if ruhe_aktiv(konfig):
        log_schreiben("Eilmeldung unterdrueckt - Ruhezeit bis %s"
                      % konfig.get("ruhe_bis"))
        return False

    einst = konfig.get("mail", {})
    empfaenger = einst.get("an")
    if not empfaenger:
        return False

    # Nicht zweimal dasselbe. Der Betreff dient als Erkennungsmerkmal.
    kennung = "%s|%s" % (date.today().isoformat(), (eil.get("betreff") or "")[:80])
    gesendet = zustand.get("eilmeldungen", [])
    if kennung and kennung in gesendet:
        log_schreiben("Eilmeldung schon verschickt: %s" % kennung[:60])
        return False

    import smtplib
    from email.message import EmailMessage
    from email.utils import formatdate

    kritisch = (eil.get("stufe") == "kritisch")
    signal = "\u26a0\ufe0f" if kritisch else "\u2757"
    farbe = "#b91c1c" if kritisch else "#b45309"
    wert, lage = d["barometer"]

    betreff = eil.get("betreff") or "Eilmeldung zur KI-Invest-Position"
    nachricht = EmailMessage()
    nachricht["From"] = einst.get("von", "ki-invest@localhost")
    nachricht["To"] = empfaenger
    nachricht["Subject"] = "%s EILMELDUNG: %s" % (signal, betreff)
    nachricht["Date"] = formatdate(localtime=True)
    nachricht["X-Priority"] = "1"
    nachricht["X-MSMail-Priority"] = "High"
    nachricht["Importance"] = "high"
    nachricht["Priority"] = "urgent"

    zahlen = [z for z in (eil.get("zahlen") or []) if isinstance(z, str)]
    positionen = d.get("positionen", [])

    klartext = ["EILMELDUNG - %s" % (eil.get("schlagzeile") or betreff), "",
                eil.get("was_geschehen_ist") or "", "",
                "WARUM ES ZAEHLT", eil.get("warum_es_zaehlt") or "", "",
                "MOEGLICHE SCHRITTE", eil.get("was_du_tun_koennte")
                or eil.get("was_du_tun_koenntest") or "", ""]
    if zahlen:
        klartext += ["ZAHLEN"] + ["  " + z for z in zahlen] + [""]
    klartext.append("Barometer %d von 100 (%s)" % (wert, lage))
    for p in positionen:
        klartext.append("  %s: Basiswert %.2f (%+.2f%%), Puffer %s"
                        % (p["name"], p["kurs"], p["tag_prozent"],
                           ("%.1f%%" % p["barriere_abstand"])
                           if p.get("barriere_abstand") is not None else "?"))
    if einst.get("web_adresse"):
        klartext += ["", "Vollstaendiger Bericht: " + einst["web_adresse"]]
    nachricht.set_content("\n".join(z for z in klartext if z is not None))

    def kachel(p):
        puffer = p.get("barriere_abstand")
        return ('<td style="padding:9px 12px;border:1px solid #e2e5ea;'
                'border-radius:8px;font:13px -apple-system,Segoe UI,sans-serif">'
                '<b>%s</b><br><span style="color:#68707b">Basiswert %.2f &middot; '
                '<span style="color:%s">%+.2f%%</span><br>Puffer %s</span></td>'
                % (p["name"], p["kurs"],
                   "#15803d" if p["tag_prozent"] < 0 else "#b91c1c",
                   p["tag_prozent"],
                   ("%.1f%%" % puffer) if puffer is not None else "&ndash;"))

    html = """<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f2f3f5">
<table role="presentation" width="100%%" cellpadding="0" cellspacing="0"
 style="background:#f2f3f5;padding:22px 12px"><tr><td align="center">
<table role="presentation" width="640" cellpadding="0" cellspacing="0"
 style="max-width:640px;background:#fff;border-radius:14px;overflow:hidden;
 box-shadow:0 2px 10px rgba(0,0,0,.09)">

<tr><td style="background:%(farbe)s;padding:20px 26px">
  <div style="font:700 11px/1 -apple-system,Segoe UI,sans-serif;
   letter-spacing:.22em;color:rgba(255,255,255,.82);text-transform:uppercase">
   %(signal)s &nbsp;Eilmeldung &middot; %(stufe)s</div>
  <div style="font:700 23px/1.28 -apple-system,Segoe UI,sans-serif;color:#fff;
   margin-top:9px">%(schlagzeile)s</div>
</td></tr>

<tr><td style="padding:24px 26px 6px;font:15px/1.6 -apple-system,Segoe UI,sans-serif;color:#16191d">
  <p style="margin:0 0 18px">%(geschehen)s</p>
  <div style="font:700 11px/1 -apple-system,Segoe UI,sans-serif;letter-spacing:.1em;
   color:#68707b;text-transform:uppercase;margin-bottom:7px">Warum es zaehlt</div>
  <p style="margin:0 0 18px">%(warum)s</p>
  <div style="font:700 11px/1 -apple-system,Segoe UI,sans-serif;letter-spacing:.1em;
   color:#68707b;text-transform:uppercase;margin-bottom:7px">Moegliche Schritte</div>
  <p style="margin:0 0 18px">%(schritte)s</p>
  %(zahlenblock)s
</td></tr>

<tr><td style="padding:4px 26px 20px">
  <table role="presentation" width="100%%" cellpadding="0" cellspacing="6"><tr>%(kacheln)s</tr></table>
  <div style="font:13px -apple-system,Segoe UI,sans-serif;color:#68707b;
   margin-top:12px">Barometer <b style="color:#16191d">%(baro)d von 100</b> &middot; %(lage)s</div>
</td></tr>

<tr><td style="padding:0 26px 26px">
  <a href="%(web)s" style="display:inline-block;background:#1d4ed8;color:#fff;
   text-decoration:none;font:600 14px -apple-system,Segoe UI,sans-serif;
   padding:12px 22px;border-radius:9px">Vollstaendigen Bericht oeffnen</a>
</td></tr>

<tr><td style="background:#f7f8fa;padding:15px 26px;font:11.5px/1.55 -apple-system,
 Segoe UI,sans-serif;color:#68707b;border-top:1px solid #e2e5ea">
  Automatisch erzeugt, weil dieser Sachverhalt die Halte-Entscheidung heute
  beruehren koennte &ndash; Ausloeser: %(ausloeser)s. Kursdaten koennen verzoegert
  sein. Die Bewertung bleibt bei dir.
</td></tr>

</table></td></tr></table></body></html>""" % {
        "farbe": farbe, "signal": signal,
        "stufe": "kritisch" if kritisch else "hohe Dringlichkeit",
        "schlagzeile": html_schuetzen(eil.get("schlagzeile") or betreff),
        "geschehen": html_schuetzen(eil.get("was_geschehen_ist") or ""),
        "warum": html_schuetzen(eil.get("warum_es_zaehlt") or ""),
        "schritte": html_schuetzen(eil.get("was_du_tun_koenntest")
                                   or eil.get("was_du_tun_koennte") or ""),
        "zahlenblock": ('<table role="presentation" width="100%%" cellpadding="0" '
                        'cellspacing="0" style="background:#f7f8fa;border-radius:9px;'
                        'padding:12px 14px;margin-bottom:6px"><tr><td '
                        'style="font:13px/1.75 -apple-system,Segoe UI,sans-serif;'
                        'color:#16191d">%s</td></tr></table>'
                        % "<br>".join(html_schuetzen(z) for z in zahlen)) if zahlen else "",
        "kacheln": "".join(kachel(p) for p in positionen),
        "baro": wert, "lage": html_schuetzen(lage),
        "web": html_schuetzen(einst.get("web_adresse", "#")),
        "ausloeser": html_schuetzen(str(eil.get("ausloeser", "Ermessen"))[:120]),
    }
    nachricht.add_alternative(html, subtype="html")

    try:
        server = smtplib.SMTP(einst.get("server", "127.0.0.1"),
                              einst.get("port", 25), timeout=30)
        server.send_message(nachricht)
        server.quit()
    except Exception as fehler:                                  # noqa: BLE001
        log_schreiben("Eilmeldung fehlgeschlagen: %s" % fehler)
        return False

    marke = date.today().strftime("%Y-%m-%d")
    kurztext = ((eil.get("schlagzeile") or "") + "\n\n"
                + (eil.get("was_geschehen_ist") or ""))

    # --- Telegram: erst die Meldung laut, dann der Bericht still hinterher
    try:
        signalwort = "KRITISCH" if kritisch else "EILMELDUNG"
        zeilen = ["%s <b>%s</b>" % (signal, signalwort), "",
                  "<b>%s</b>" % html_schuetzen(eil.get("schlagzeile") or betreff), ""]
        if eil.get("was_geschehen_ist"):
            zeilen += [html_schuetzen(eil["was_geschehen_ist"]), ""]
        if eil.get("warum_es_zaehlt"):
            zeilen += ["<b>Warum es zaehlt</b>",
                       html_schuetzen(eil["warum_es_zaehlt"]), ""]
        if eil.get("was_du_tun_koenntest"):
            zeilen += ["<b>Moegliche Schritte</b>",
                       html_schuetzen(eil["was_du_tun_koenntest"]), ""]
        if zahlen:
            zeilen += ["<b>Zahlen</b>"] + ["  " + html_schuetzen(z) for z in zahlen] + [""]
        zeilen.append("Barometer <b>%d von 100</b> &#183; %s"
                      % (wert, html_schuetzen(lage)))
        for p in positionen:
            puffer = p.get("barriere_abstand")
            zeilen.append("  %s: %.2f (%+.2f%%), Puffer %s"
                          % (html_schuetzen(p["name"]), p["kurs"], p["tag_prozent"],
                             ("%.1f%%" % puffer) if puffer is not None else "?"))
        if einst.get("web_adresse"):
            zeilen += ["", '<a href="%s">Vollstaendiger Bericht</a>'
                       % html_schuetzen(einst["web_adresse"])]

        telegram_senden(konfig, "\n".join(zeilen), still=False)

        bericht = d.get("mail_html")
        if not bericht:
            try:
                with open(BERICHT_PFAD) as f:
                    bericht = f.read()
            except IOError:
                bericht = None
        if bericht:
            telegram_datei(konfig, bericht, "bericht-%s.html" % marke,
                           "Vollstaendiger Bericht zum Nachlesen", still=True)
    except Exception as fehler:                                  # noqa: BLE001
        log_schreiben("Telegram-Aufruf fehlgeschlagen: %s" % fehler)

    # --- ntfy nur noch, wenn ausdruecklich eingeschaltet
    try:
        if konfig.get("ntfy", {}).get("aktiv"):
            if not ntfy_datei_senden(konfig, html, "eilmeldung-%s.html" % marke,
                                     ("Kritisch: " if kritisch else "") + betreff,
                                     kurztext, kritisch, einst.get("web_adresse")):
                ntfy_senden(konfig, ("Kritisch: " if kritisch else "") + betreff,
                            kurztext, kritisch, einst.get("web_adresse"))
    except Exception as fehler:                                  # noqa: BLE001
        log_schreiben("ntfy-Aufruf fehlgeschlagen: %s" % fehler)

    try:
        if konfig.get("hue", {}).get("dauerblinken"):
            dauerblinken_starten(eil.get("schlagzeile") or betreff)
        else:
            hue_signal(konfig, kritisch)
    except Exception as fehler:                                  # noqa: BLE001
        log_schreiben("Hue-Signal fehlgeschlagen: %s" % fehler)

    gesendet.append(kennung)
    zustand["eilmeldungen"] = gesendet[-40:]
    log_schreiben("EILMELDUNG verschickt (%s): %s"
                  % (eil.get("stufe", "hoch"), betreff[:70]))
    systemmeldung("KI-Invest EILMELDUNG", betreff, "Basso")
    return True


def bericht_mailen(konfig, d):
    """
    Schickt den Bericht als HTML-Mail. Nutzt den lokalen Mailserver, damit
    keine Zugangsdaten im Skript stehen muessen.
    """
    einst = konfig.get("mail", {})
    if not einst.get("aktiv"):
        return
    empfaenger = einst.get("an")
    if not empfaenger:
        log_schreiben("Mail: kein Empfaenger hinterlegt")
        return

    import smtplib
    from email.message import EmailMessage
    from email.utils import formatdate

    wert, lage = d["barometer"]
    positionen = d.get("positionen", [])
    gesamt = summe_ein = None
    reihen = [p.get("wertverlauf") for p in positionen if p.get("wertverlauf")]
    if reihen:
        gesamt = sum(r["punkte"][-1]["wert"] for r in reihen)
        summe_ein = sum(r["einsatz"] for r in reihen)

    betreff = "KI-Invest %s: Barometer %d" % (date.today().strftime("%d.%m."), wert)
    if gesamt is not None:
        betreff += " | %.0f EUR (%+.0f)" % (gesamt, gesamt - summe_ein)
    echte = [t for stufe, t in d.get("alarme", []) if stufe == "alarm"]
    if echte:
        betreff += " | %d Auffaelligkeiten" % len(echte)

    nachricht = EmailMessage()
    nachricht["From"] = einst.get("von", "ki-invest@localhost")
    nachricht["To"] = empfaenger
    nachricht["Subject"] = betreff
    nachricht["Date"] = formatdate(localtime=True)

    klartext = ["Barometer %d von 100 (%s)" % (wert, lage), ""]
    for satz in (d.get("zusammenfassung") or [])[:4]:
        klartext.append("- " + re.sub(r"<[^>]+>", "", satz))
    if einst.get("web_adresse"):
        klartext += ["", "Im Browser: " + einst["web_adresse"]]
    nachricht.set_content("\n".join(klartext))

    html = d.get("mail_html")
    if not html:
        try:
            with open(BERICHT_PFAD) as f:
                html = f.read()
        except IOError:
            html = None
    if html:
        nachricht.add_alternative(html, subtype="html")

    try:
        server = smtplib.SMTP(einst.get("server", "127.0.0.1"),
                              einst.get("port", 25), timeout=30)
        server.send_message(nachricht)
        server.quit()
        log_schreiben("Mail an %s verschickt" % empfaenger)
    except Exception as fehler:                                  # noqa: BLE001
        log_schreiben("Mailversand fehlgeschlagen: %s" % fehler)


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


def claude_sichern(urteil):
    """Legt die letzte brauchbare Einordnung ab, damit die haeufigen
    Datenlaeufe sie weiterverwenden koennen, ohne Claude zu fragen."""
    if not urteil or urteil.get("fehler"):
        return
    ablage = dict(urteil)
    ablage["_stand"] = datetime.now().strftime("%d.%m.%Y, %H:%M")
    ablage["_zeitstempel"] = datetime.now().isoformat(timespec="seconds")
    json_speichern(CLAUDE_PFAD, ablage)


def claude_letzte():
    """Die zuletzt gesicherte Einordnung, oder nichts."""
    urteil = json_laden(CLAUDE_PFAD, None)
    if isinstance(urteil, dict) and not urteil.get("fehler"):
        return urteil
    return None


def bericht_schreiben(konfig, d, oeffnen, barometer_verlauf=None,
                      fuer_mail=False, nur_web=False):
    konfig["_verworfen"] = d.get("verworfen", 0)
    konfig["_tokenpreise"] = d.get("tokenpreise")
    archiv_name = datetime.now().strftime("%Y-%m-%d-%H%M.html")
    # Zwischenlaeufe schreiben keinen Archiveintrag. Wuerde die Startseite
    # trotzdem einen Dateinamen nennen, faende sich die Navigation nicht in
    # ihrer eigenen Liste wieder und zaehlte falsch.
    eigene_datei = "" if nur_web else archiv_name

    def bauen(mailfassung, basis="", datei=None):
        return bericht_bauen(konfig, d["positionen"], d["kurse"], d["gruppen"],
                             d["indikatoren"], d["barometer"], d["nachrichten"],
                             d["regierung"], d["blogs"], d["sec"], d["alarme"],
                             d.get("claude"), d["fehler"], d.get("zusammenfassung"),
                             barometer_verlauf, mailfassung,
                             archiv_name if datei is None else datei, basis)

    html = bauen(False)
    if konfig.get("mail", {}).get("aktiv"):
        d["mail_html"] = bauen(True)
    with open(BERICHT_PFAD, "w") as f:
        f.write(html)
    if oeffnen and ist_mac():
        subprocess.run(["open", BERICHT_PFAD], check=False)

    # Ablage fuer den Webserver samt Archiv. Die Startseite liegt eine Ebene
    # ueber dem Archiv, deshalb bekommt sie den Basispfad "archiv/" mit.
    ziel = konfig.get("bericht_kopie")
    if ziel:
        try:
            web = os.path.dirname(ziel)
            archiv = os.path.join(web, "archiv")
            os.makedirs(archiv, exist_ok=True)

            with open(ziel, "w") as f:
                f.write(bauen(False, "archiv/", eigene_datei))

            # Zwischenlaeufe aktualisieren nur die Startseite. Ein Archiveintrag
            # entsteht stuendlich beziehungsweise beim Tagesbericht.
            if not nur_web:
                with open(os.path.join(archiv, archiv_name), "w") as f:
                    f.write(bauen(False, ""))
                verzeichnis_schreiben(archiv, archiv_name, d,
                                      konfig.get("archiv_hoechstzahl", 90))
        except OSError as fehler:
            log_schreiben("Kopie nach %s fehlgeschlagen: %s" % (ziel, fehler))


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
             else "web" if "--web" in sys.argv
             else "test" if "--test" in sys.argv else "watch")

    # Im Web-Modus fragt nur der stuendliche Lauf bei Claude nach. Die
    # Zwischenlaeufe nehmen die zuletzt gesicherte Einordnung.
    if modus == "web":
        mit_claude = "--mit-claude" in sys.argv
    else:
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
        schwellen_alarm(konfig, d, zustand)
        # Nur wenn wirklich etwas Neues von Alarmstufe vorliegt, wird Claude
        # zur Einschaetzung gefragt - sonst liefe bei jedem Lauf eine Anfrage.
        echte = [t for stufe, t in frisch if stufe == "alarm"]
        if echte and konfig.get("eilmeldung_aktiv", True):
            log_schreiben("watch: %d neue Alarme, frage Claude nach Eilbedarf"
                          % len(echte))
            d["claude"] = claude_fragen(
                konfig, d["positionen"], d["indikatoren"], d["barometer"],
                d["nachrichten"], d["regierung"], d["blogs"], d["sec"])
            if d["claude"] and not d["claude"].get("fehler"):
                eilmeldung_verschicken(konfig, d, zustand)
        log_schreiben("watch: Barometer %d, %d Auffaelligkeiten (%d neu), "
                      "%d Abrufprobleme" % (d["barometer"][0], len(d["alarme"]),
                                            len(frisch), len(d["fehler"])))
    else:
        verlauf = zustand.get("barometer_verlauf", [])
        heute = date.today().strftime("%d.%m.")
        if modus == "web" and verlauf and verlauf[-1].get("datum") == heute:
            verlauf[-1]["wert"] = d["barometer"][0]     # Tageswert fortschreiben
        else:
            verlauf.append({"datum": heute, "wert": d["barometer"][0]})
        zustand["barometer_verlauf"] = verlauf[-40:]
        neuheiten_markieren(d["nachrichten"], zustand)

        # Zwischenlaeufe aktualisieren nur die Startseite, kein Archiveintrag
        bericht_schreiben(konfig, d, oeffnen=(modus == "report"),
                          barometer_verlauf=zustand["barometer_verlauf"],
                          nur_web=(modus == "web" and not mit_claude))

        if modus == "web":
            frisch = neue_alarme(d["alarme"], zustand)
            echte = [t for stufe, t in frisch if stufe == "alarm"]
            # Feste Schwellen greifen in JEDEM Lauf, auch ohne Einordnung -
            # sonst koennte zwischen zwei vollen Stunden nichts alarmieren.
            geschwellt = schwellen_alarm(konfig, d, zustand)
            if (not geschwellt and echte and mit_claude and d.get("claude")
                    and not d["claude"].get("fehler")):
                eilmeldung_verschicken(konfig, d, zustand)
            log_schreiben("web%s: Barometer %d, %d Auffaelligkeiten (%d neu), "
                          "%d Nachrichten, %d Abrufprobleme"
                          % (" mit Claude" if mit_claude else "",
                             d["barometer"][0], len(d["alarme"]), len(frisch),
                             len(d["nachrichten"]), len(d["fehler"])))
        # Datenstand sichern, damit --nur-claude ohne erneuten Abruf arbeiten kann
        d["gesammelt_am"] = datetime.now().strftime("%d.%m.%Y %H:%M")
        try:
            json_speichern(DATEN_PFAD, d)
        except (TypeError, ValueError) as f:
            log_schreiben("Hinweis: Daten nicht sicherbar (%s)" % f)
        if modus == "report":
            if not schwellen_alarm(konfig, d, zustand):
                eilmeldung_verschicken(konfig, d, zustand)
            bericht_mailen(konfig, d)
            zustand["gemeldet"] = {"datum": date.today().isoformat(), "texte": []}
        if modus == "web":
            zustand["letzter_lauf"] = datetime.now().isoformat(timespec="seconds")
            zustand["letztes_barometer"] = d["barometer"][0]
            json_speichern(STATE_PFAD, zustand)
            return 0
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
