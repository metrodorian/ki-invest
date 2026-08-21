#!/usr/bin/env python3
"""
Waehlt die Vorschlaege aus, die dem woechentlichen Verbesserungslauf vorgelegt
werden: alles, was seit dem letzten Lauf dazugekommen ist.

Alles Aeltere gilt als abgearbeitet - unabhaengig davon, ob es umgesetzt oder
begruendet verworfen wurde. Das ist verlaesslicher, als sich auf ein
"erledigt"-Kennzeichen zu stuetzen: Bricht ein Lauf nach der Arbeit ab, waeren
die Vermerke verloren und dieselben Vorschlaege liefen dauerhaft wieder auf.
Was weiterhin wichtig ist, schlaegt claude in den Tageslaeufen ohnehin erneut
vor - und dann taucht es hier wieder auf.

Aufruf:  vorschlaege_auswaehlen.py <zieldatei>
Umgebung: SEIT (ISO-Zeitpunkt, leer = alles), KI_LIVE (Betriebsordner)
Ausgabe: die Anzahl der ausgewaehlten Vorschlaege
"""
import io
import json
import os
import sys


def main():
    ziel = sys.argv[1] if len(sys.argv) > 1 else "verbesserungen.json"
    seit = (os.environ.get("SEIT") or "").strip()
    quelle = os.path.join(os.environ.get("KI_LIVE", "."), "verbesserungen.json")

    try:
        with io.open(quelle, encoding="utf-8") as f:
            alle = json.load(f)
    except (IOError, ValueError):
        alle = []
    if not isinstance(alle, list):
        alle = []

    neu = [e for e in alle if isinstance(e, dict)
           and (e.get("zuletzt") or e.get("zeit") or "") > seit]

    # Haeufig genannte zuerst: Ein Wunsch, der zwanzigmal kam, hat zwanzigmal
    # beim Urteilen gefehlt.
    neu.sort(key=lambda e: -(e.get("genannt") or 1))

    with io.open(ziel, "w", encoding="utf-8") as f:
        json.dump(neu, f, indent=2, ensure_ascii=False)
    print(len(neu))
    return 0


if __name__ == "__main__":
    sys.exit(main())
