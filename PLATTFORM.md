# Plattform- und Produktnotizen

## Broker-Entscheidung

- **Gewählt: ING Direkt-Depot** — Stiftung Warentest "sehr gut" (Browser-Handel), kein Gamification-Design (im Gegensatz zu Trade Republic), volle Xetra-Anbindung.
- Kontoeröffnung: PostIdent mit **Video-Identifizierung** durchgeführt (15.08.2026) → Zugangsdaten meist innerhalb 1-3 Werktage.
- Alternativen geprüft, aber verworfen/nicht gewählt: comdirect (7-10 Werktage Kontoeröffnung, für 3-Tage-Ziel zu langsam), Trade Republic (Gamification-Kritik, schwer erreichbarer Support), XTB (moderne Trading-App-Alternative, falls ING nicht passt).

## ING-Gebührenstruktur (relevant für Orderplanung)

- Grundgebühr: **4,90 € + 0,25%** des Ordervolumens, gekappt bei max. 69,90 €
- Handelsplatzentgelt: **2,90 €** (Xetra/Frankfurt/München/Berlin/Düsseldorf/Hamburg/Hannover), **1,90 €** (Stuttgart/Euwax)
- Bei 3.000 € Ordervolumen über Xetra: ca. **15,30 €** Gesamtkosten pro Order (~0,5%)
- Ausländische Handelsplätze (falls Produkt nicht an deutscher Börse notiert): zusätzlich bis zu **14,90 €**
- Kein Zugang zu Lang & Schwarz (bei Neobrokern beliebter günstiger Handelsplatz)
- ETPs/ETNs grundsätzlich handelbar, außer Xetra-Gold

## Produktanbieter: Leverage Shares (leverageshares.com)

Bietet 130+ Short-/Leveraged-/1:1-ETPs an der Xetra an, handelbar über Broker mit Zugang zu LSE, Euronext Amsterdam, Börse Frankfurt, Borsa Italiana.

### Bestätigte Produkte

| Produkt | ISIN/Ticker | Hebel | Notiz |
|---|---|---|---|
| Short Artificial Intelligence (AI) ETP | ISIN XS2779861835, Ticker GPTS/AIS3 | -3x | Basis: Solactive US AI Index, enthält auch Alibaba |
| Long Artificial Intelligence (AI) ETP | Ticker GPT3 | 3x | ISIN nicht final verifiziert |
| Nvidia-Produkte | diverse | -1x, 2x long, -3x short bestätigt | **-2x short Nvidia noch nicht bestätigt** — auf leverageshares.com prüfen |
| Alphabet-Produkte | diverse | 2x long bestätigt | — |

### Offen / vor Kauf zu prüfen

- Exakte WKN/ISIN für gewünschtes Produkt direkt auf der [Leverage Shares Xetra-ETP-Liste](https://leverageshares.com/en-eu/xetra-etps/) nachschlagen (Liste ändert sich, Snippets aus Websuche nicht vollständig)
- Handelsplatz-Verfügbarkeit für ING-Konto konkret verifizieren (Xetra vs. Frankfurt vs. Stuttgart — Kostenunterschied 1,90 € vs. 2,90 €, ausländische Plätze bis zu 14,90 € extra)
- Ob es überhaupt eine -2x-Variante des breiten AI-Index-Produkts gibt (bisher nur 3x/-3x gefunden)

## Wichtiger Mechanik-Hinweis

Gehebelte ETPs resetten **täglich**. Bei volatiler Seitwärtsbewegung frisst der Compounding-Effekt Rendite auf, selbst wenn die These langfristig aufgeht. Für taktische Positionen (Tage/Wochen) gebaut, nicht für Buy-and-Hold über Monate.
