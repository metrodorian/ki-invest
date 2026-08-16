# Short-Strategien nach Kategorie

Alle Positionen als **taktische, kurzfristige** Wetten gedacht (Tage/Wochen), nicht Buy-and-Hold — gehebelte Produkte resetten täglich.

## Gewählte Kombination

| Position | Basiswert | WKN | Rolle in der These |
|---|---|---|---|
| 1 | Nvidia -2x | **MG4U8W** | Chip-Seite: profitiert heute vom Capex, leidet am stärksten bei Effizienzschock |
| 2 | Vertiv -2x | **MR275A** | Bau-/Ausrüstungsseite: ~75% Umsatz aus Rechenzentren, stirbt bei Baustopp |

Beide sterben, wenn keine Rechenzentren mehr gebaut werden — aber es ist nicht zweimal dieselbe Aktie. Details zu den Produkten in [PLATTFORM.md](PLATTFORM.md).

---

## Kategorie 1: Chip-Zulieferer (Nvidia, AMD, TSMC) — GEWÄHLT

- **These**: Nvidia = "Waffenhändler", verdient unabhängig davon wer gewinnt — aber am stärksten exponiert, wenn Hyperscaler-Capex zurückgefahren wird.
- **Empirischer Beleg (DeepSeek, 27.01.2025)**: Nvidia -16,9%, während Hyperscaler nur 3-4% verloren. **Faktor 4-5 stärkere Reaktion auf denselben Auslöser.**
- **Verstärkendes Argument**: Nvidia betreibt **Vendor Financing** (siehe [RECHERCHE.md](RECHERCHE.md)) — die Umsatzqualität ist schlechter als die Zahlen suggerieren.
- **Trigger**: Neue Exportkontrollen, Capex-Kommentare in Earnings Calls, Fortschritte chinesischer Chiphersteller.
- **Risiko**: Hohe Erwartung eingepreist, extreme Liquidität → kurzfristige Rallyes auf positive News.

## Kategorie 2: Rechenzentrums-Ausrüster (Vertiv, Comfort Systems, Sterling) — GEWÄHLT

- **These**: Wenn der Bau stoppt, bricht der Auftragseingang **sofort** weg. Präziser als Neoclouds, die langlaufende Verträge haben, die noch eine Weile Umsatz liefern.
- **Vertiv**: ~75% Umsatz aus Rechenzentren, Auftragsbestand über 15 Mrd. USD, KGV 47,47. Höchste Konzentration unter den etablierten Zulieferern.
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

## Offene Punkte

- [ ] Positionsgrößen und Einstiegszeitpunkt festlegen
- [ ] Ausstiegsregel definieren (Stop-Loss? Zielkurs? Zeitlimit?)
- [ ] Barriere-Abstand regelmäßig prüfen — die Reset-Barriere wandert täglich mit
