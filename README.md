# ki-invest

Zwei gehebelte Short-Positionen und das Überwachungssystem dazu.

**Die These:** Die westlichen KI-Investitionen erzeugen kaum Gegenwert, während China mit
günstigerer Hardware und Energie aufholt.

Kein Anlageberatungs-Dokument. Eine Arbeitsgrundlage: Recherche, Positionen, offene Fragen —
und ein Monitor, der die These laufend gegen die Wirklichkeit prüft, auch dort, wo sie
danebenliegt.

## Stand: 22.08.2026

Beide Positionen laufen seit dem 20.08.2026.

| | WKN | Faktor | Einsatz | Stop | Barriere | Zeitlimit |
|---|---|---|---|---|---|---|
| Nvidia Short | **MG4U8W** | −2x | 1.003,80 € | 0,294 | 324,00 USD | 17.09.2026 |
| Vertiv Short | **MR275A** | −2x | 1.030,95 € | 56,20 | 421,08 USD | 17.09.2026 |

**Nächster Termin: Nvidia Q2 GJ2027 am 26.08.2026** nach US-Schluss. Entscheidend ist nicht
das Quartal, sondern die Prognose fürs Folgequartal gegen den Konsens von 103,1 Mrd. USD und
die Bruttomarge gegen die geführten 75,0 Prozent.

## Inhalt

| Datei | Inhalt |
|---|---|
| [THESE.md](THESE.md) | Kernthese, ihre zwei Mechanismen — und was die Daten seither dazu sagen |
| [STRATEGIEN.md](STRATEGIEN.md) | Gewählte Positionen, geprüfte und verworfene Kategorien |
| [RECHERCHE.md](RECHERCHE.md) | Belastbare Datenpunkte mit Quellen |
| [PLATTFORM.md](PLATTFORM.md) | Broker, Produktauswahl, Produktlektionen |
| [monitor/README.md](monitor/README.md) | Das Überwachungssystem: Aufbau, Betrieb, Bedienung |

## Der Monitor

Läuft auf einem Raspberry Pi, alle zehn Minuten, rund um die Uhr. Er verfolgt rund fünfzig
Kurse in acht Gruppen, leitet daraus Indikatoren ab, liest Nachrichten, SEC-Pflichtmeldungen,
Regierungsvorhaben und Bilanzreihen — und lässt die Lage zweimal täglich von Claude einordnen.

Bei harten Schwellen meldet er sofort: Mail, Telegram, blinkende Lampe. Werktags um 22:30 gibt
es einen Tagesbericht.

Einmal in der Woche geht er sich selbst verbessern: Claudes gesammelte Vorschläge werden
sonntags von einer unbeaufsichtigten Sitzung durchgearbeitet, die auf einem Testzweig
committet. Zusammengeführt wird von Hand.

Alles Weitere in [monitor/README.md](monitor/README.md).

## Wie hier gearbeitet wird

`main` ist geschützt. Änderungen laufen über den Zweig `test` und einen Pull Request; der
Betrieb holt sich den zusammengeführten Stand selbst:

```
./betrieb.sh aktualisieren --pi
```

Die Konfiguration liegt in zwei Schichten: `config.json` ist auf jedem Rechner identisch und
im Repo, `config.lokal.json` trägt Zugangsdaten, Pfade und die Rolle des Rechners und bleibt
draußen.
