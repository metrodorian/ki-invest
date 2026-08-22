# Short-Strategien nach Kategorie

Alle Positionen als **taktische, kurzfristige** Wetten gedacht (Tage/Wochen), nicht Buy-and-Hold — gehebelte Produkte resetten täglich.

## Gewählte Kombination

Beide Positionen laufen seit dem 20.08.2026, Zeitlimit 17.09.2026.

| | WKN | Faktor | Stück | Einsatz | Einstieg Schein | Stop | Barriere |
|---|---|---|---|---|---|---|---|
| Nvidia Short | **MG4U8W** | −2x | 2.222 | 1.003,80 € | 0,451755 | 0,294 | 324,00 USD |
| Vertiv Short | **MR275A** | −2x | 9 | 1.030,95 € | 114,55 | 56,20 | 421,08 USD |

Gesamteinsatz 2.034,75 € von 3.000 € — knapp ein Drittel bleibt als Puffer liegen.

**Warum diese zwei.** Nvidia steht für die Chip-Seite: Sie verdient heute am Capex und leidet
am stärksten bei einem Effizienzschock. Vertiv steht für die Bau- und Ausrüstungsseite: rund
drei Viertel des Umsatzes aus Rechenzentren, das Geschäft stirbt bei einem Baustopp. Beide
sterben, wenn nicht mehr gebaut wird — aber es ist nicht zweimal dieselbe Aktie.

**Die Stops sind ungleich gesetzt**, und zwar mit Absicht. Vertiv schwankt mit rund 76 Prozent
im Jahr fast doppelt so stark wie Nvidia mit 38. Der weite Stop bei −51 Prozent soll
verhindern, dass gewöhnliches Rauschen die Position beendet, bevor die These überhaupt geprüft
ist.

**Der Preis dafür ist der tägliche Reset.** Bei Seitwärtslauf kostet Vertiv rund 3,3 Prozent
pro Woche, Nvidia rund 0,8. Über die verbleibende Laufzeit sind das bei Vertiv gut zwölf
Prozent allein durch Mechanik. Die Vertiv-Position muss also bald recht bekommen, die
Nvidia-Position kann warten.

Details zu den Produkten in [PLATTFORM.md](PLATTFORM.md), die laufende Überwachung in
[monitor/README.md](monitor/README.md).

---

---

## Kategorie 1: Chip-Zulieferer (Nvidia, AMD, TSMC) — GEWÄHLT

- **These**: Nvidia = "Waffenhändler", verdient unabhängig davon wer gewinnt — aber am stärksten exponiert, wenn Hyperscaler-Capex zurückgefahren wird.
- **Empirischer Beleg (DeepSeek, 27.01.2025)**: Nvidia -16,9%, während Hyperscaler nur 3-4% verloren. **Faktor 4-5 stärkere Reaktion auf denselben Auslöser.**
- **Verstärkendes Argument**: Nvidia betreibt **Vendor Financing** (siehe [RECHERCHE.md](RECHERCHE.md)) — die Umsatzqualität ist schlechter als die Zahlen suggerieren.
- **Trigger**: Neue Exportkontrollen, Capex-Kommentare in Earnings Calls, Fortschritte chinesischer Chiphersteller.
- **Risiko**: Hohe Erwartung eingepreist, extreme Liquidität → kurzfristige Rallyes auf positive News.

## Kategorie 2: Rechenzentrums-Ausrüster (Vertiv, Comfort Systems, Sterling) — GEWÄHLT

- **These**: Wenn der Bau stoppt, bricht der Auftragseingang **sofort** weg. Präziser als Neoclouds, die langlaufende Verträge haben, die noch eine Weile Umsatz liefern.
- **Vertiv**: ~75% Umsatz aus Rechenzentren, höchste Konzentration unter den etablierten Zulieferern.
- **Wichtige Einschränkung seit dem Kauf**: Vertiv meldet seit dem ersten Quartal 2026 **weder Auftragseingang noch Book-to-Bill noch Auftragsbestand** je Quartal. Angekündigt am 11.02.2026 auf dem Q4-Call, begründet mit zu hoher Schwankung — im Quartal mit +252 Prozent Auftragseingang und 15 Mrd. Auftragsbestand, also den besten Zahlen der Firmengeschichte. Die Jahresangabe im 10-K bleibt. Das ist angekündigte Politik, kein Verstecken — es entzieht der Position aber die Kennzahl, an der sie eigentlich zu messen wäre. Der Ersatz aus der Bilanz (erhaltene Anzahlungen) trägt nur bedingt; siehe [RECHERCHE.md](RECHERCHE.md).
- **Alternativen geprüft**: Comfort Systems (45% Umsatzanteil, ~12 Mrd. Auftragsbestand), Sterling Infrastructure (92% des Auftragsbestands "mission-critical"), EMCOR (breit diversifiziert, Puffer durch Gesundheit/Behörden/Energie), Schneider Electric (Europa, über 24% Umsatzanteil).
- **Volatilität**: Vertiv-Wochenspanne 11,5% — handhabbar, im Gegensatz zu den Neoclouds.
- **Sensitivität trotzdem hoch**: 17%-Abverkauf Ende Juli 2026.

## Kategorie 3: Hyperscaler (Microsoft, Amazon, Meta, Alphabet) — VERWORFEN

- **These**: Capex 2026 zusammen ~725 Mrd. USD, davon ~75% AI-Infrastruktur.
- **Warum verworfen**: Diversifizierte Konzerne — Cloud/Werbung/E-Commerce dämpfen stark. Beim DeepSeek-Moment nur 3-4% Verlust. Reaktionen zuletzt uneinheitlich.
- **Falls doch**: **Amazon** wäre der Kandidat (höchster Capex mit 220 Mrd., FCF soll negativ werden, noch nicht abgestraft). Microsoft ist mit -21% dieses Jahr bereits vorbelastet — weniger Fallhöhe.
- **Kein sauberes Basket-Produkt verfügbar** (siehe PLATTFORM.md).

## Kategorie 4: Neoclouds (CoreWeave, Nebius, IREN, Applied Digital) — VERWORFEN

- **These**: Direkteste Capex-Wette — GPU-Rechenzentren auf eigene Rechnung, schuldenfinanziert.
- **Zahlen**: CoreWeave Auftragsbestand 104 Mrd. USD bei 58,8 Mrd. Marktkap., aber Quartalsverlust 626 Mio. USD und **Zinsaufwand 640 Mio. pro Quartal**. Applied Digital: 600 MW unter Vertrag (~16 Mrd.) bei 8,37 Mrd. Marktkap.
- **Warum verworfen**: **Volatilität zu hoch.** CoreWeave-Wochenspanne 87,46-117,49 USD = **34% in einer Woche**. Bei -2x (50% theoretischer Puffer) ein reales Ausknock-Risiko, unabhängig davon ob die These stimmt.
- Kein Faktor-1-Produkt auf CoreWeave gefunden, das den Puffer auf 100% heben würde.
- Zusätzlich: Laufen aktuell heiß ("Neocloud Stocks Catch Fire", August 2026).

## Kategorie 5: Indizes (S&P 500, Nasdaq 100) — VERWORFEN

Reaktion am DeepSeek-Tag: Nvidia -16,9%, Nasdaq 100 -3,07%, **S&P 500 -1,46%** → S&P ist ~11x unempfindlicher. Mag 7 machen zwar ~31,5% des S&P aus, aber die restlichen zwei Drittel (Banken, Gesundheit, Energie, Konsum) würden von *billigerer* KI eher profitieren — man wettet teilweise gegen die eigene These. Dazu struktureller Aufwärtsdrift gegen einen gehebelten Short.

**Nasdaq 100** wäre der brauchbarere Mittelweg gewesen (doppelte Sensitivität ggü. S&P, sehr liquide Produkte).

## Kategorie 6: SpaceX (enthält xAI) — VERWORFEN

Seit 12.06.2026 börsennotiert (WKN A42D4F), IPO zu 135 USD, aktuell ~140 USD, KGV 1.425. xAI macht nur ~12-15% der Bewertung aus — der Rest ist Raumfahrt und Starlink. Noch verwässerter als der Magnificent-7-Basket. Kurstreiber der nächsten Monate (Lock-up-Auslauf ca. September-Dezember 2026) haben mit der These nichts zu tun.

## Nicht handelbar

- **OpenAI, Anthropic**: nicht börsennotiert (IPO frühestens 2027). Microsoft hält ~27% an OpenAI, aber das sind nur ~9% von Microsofts Marktkapitalisierung — stark verwässerter Proxy.
- **xAI**: seit Februar 2026 in SpaceX aufgegangen, kein eigenständiges Instrument.
- **Huawei**: nicht börsennotiert. **SMIC**: Shanghai/Hongkong, für deutsche Privatanleger kaum zugänglich.

## Erledigt

- [x] **Positionsgrößen und Einstieg** — je rund 1.000 €, gekauft am 20.08.2026
- [x] **Ausstiegsregel** — Stop-Loss im Depot hinterlegt, Zeitlimit 17.09.2026
- [x] **Barriere-Abstand laufend prüfen** — der Monitor rechnet ihn bei jedem Lauf neu und
      warnt, sobald der Puffer unter 30 Prozent fällt

## Offen

- [ ] **Entscheidung am 26.08.** nach den Nvidia-Zahlen: halten, glattstellen oder Stop
      nachziehen. Maßgeblich sind Prognose fürs Folgequartal gegen 103,1 Mrd. USD und
      Bruttomarge gegen 75,0 Prozent.
- [ ] **Reset-Barrieren nachtragen**, wenn sie zu weit von der Konfiguration abweichen — sie
      wandern täglich mit.
