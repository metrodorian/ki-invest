# Plattform- und Produktnotizen

## Broker

**ING Direkt-Depot**, Konto eröffnet 15.08.2026 (PostIdent mit Video-Identifizierung). Gewählt wegen Stiftung-Warentest-Bewertung "sehr gut", kein Gamification-Design, volle Xetra-Anbindung.

Verworfen: comdirect (7-10 Werktage Kontoeröffnung), Trade Republic (Gamification-Kritik, schwer erreichbarer Support), XTB (Alternative, falls ING nicht passt).

### Gebührenstruktur

- Grundgebühr **4,90 € + 0,25%** des Ordervolumens, gekappt bei 69,90 €
- Handelsplatzentgelt: **2,90 €** (Xetra/Frankfurt/München u.a.), **1,90 €** (Stuttgart/Euwax)
- Bei 3.000 € über Xetra: ca. **15,30 €** pro Order (~0,5%)
- Ausländische Handelsplätze: zusätzlich bis zu **14,90 €**
- **Aber:** Zertifikate von ING-Partneremittenten kosten **0 € Ordergebühr** (zzgl. Spread). Morgan Stanley und J.P. Morgan gehören dazu, **UniCredit offenbar nicht** (ING zeigt dort "kein Wert vorhanden" in der Gebührenspalte).
- Kein Zugang zu Lang & Schwarz

## Gewählte Positionen

| Position | WKN | Emittent | Faktor | Barriere | Puffer | Spread |
|---|---|---|---|---|---|---|
| Nvidia Short | **MG4U8W** | Morgan Stanley | -2x | 324,42 USD | ~44% | 2,38% |
| Vertiv Short | **MR275A** | Morgan Stanley | -2x | 413,37 USD | ~40,7% | 0,25% |

Beide Faktor-Optionsscheine, Endlos-Laufzeit, 0 € Ordergebühr bei ING. Referenzkurse: Nvidia 225,16 USD, Vertiv 293,84 USD (Stand 14.08.2026).

## Wichtigste Produktlektionen aus der Recherche

### 1. "Faktor-Optionsschein" heißt NICHT knock-out-frei

Ursprüngliche Annahme war falsch. **Alle** geprüften Faktor-Optionsscheine (Morgan Stanley, J.P. Morgan) tragen denselben Textbaustein im Produktblatt: *"Das Produkt ist mit einer Knock-Out Schwelle ausgestattet."* Knock-out ist in diesem Segment der Normalfall, nicht die Ausnahme.

### 2. Der Barriere-Abstand ergibt sich aus dem Faktor

Ein Short wird theoretisch wertlos bei einem Kursanstieg von `100% ÷ Faktor`:

| Faktor | Nötiger Anstieg für Totalverlust |
|---|---|
| -1x | +100% |
| -2x | +50% |
| -3x | +33% |
| -5x | +20% |

Emittenten setzen die tatsächliche Barriere unterschiedlich nah an dieses Maximum — **das ist das eigentliche Auswahlkriterium**, nicht der Preis des Scheins.

### 3. Emittenten-Muster

- **Morgan Stanley**: setzt Barrieren nahe am theoretischen Maximum (40-44% bei Faktor 2) → viel Puffer
- **J.P. Morgan**: setzt Barrieren deutlich enger (10-12,6% bei Faktor 2) → bei volatilen Werten gefährlich, dafür oft engere Spreads
- Konsistent bei Nvidia **und** Vertiv beobachtet

### 4. Preis ≠ Risiko

Verschiedene Tranchen desselben Emittenten teilen oft **identische Barriere und Basispreis** und unterscheiden sich nur im Bezugsverhältnis (= Stückpreis). Ein teurerer Schein bedeutet nicht mehr Sicherheit. Beispiel: MR275A (96,26 €) und MM6J30 (1,34 €) haben beide Barriere 413,37 USD.

## Geprüfte und verworfene Produkte

| Produkt | WKN | Warum verworfen |
|---|---|---|
| Vontobel Nvidia -2x | (VX2GSQ) | **Delisted seit 06.08.2025** |
| Leverage Shares -3x Magnificent 7 | A4AFMK | Nicht an deutscher Börse — nur Mailand (Spread 34%) und London (Auslandsgebühr ~14,90 €) |
| WisdomTree Short Magnificent 7 | A4ANZ4 | An Xetra handelbar, aber **kein Hebel** (1x) und Spreads 2,14-2,75% |
| DZ Bank Microsoft -2x | DY8CWG | Knock-Out-Produkt, damals als einzige Microsoft-Option gefunden |
| J.P. Morgan Nvidia -2x | JE1PLW u.a. | Nur ~12,6% Barriere-Puffer |
| J.P. Morgan Vertiv -2x | JY3BTR | Nur ~9,9% Barriere-Puffer |
| UniCredit Vertiv -2x | UN0QCB, UN74M3 | Nicht im 0-€-Programm von ING |

Faktor-Optionsscheine auf den Magnificent-7-Index (Morgan Stanley) existieren nur als **Long**-Varianten.

## Mechanik-Hinweis

Gehebelte Produkte resetten **täglich**. Bei volatiler Seitwärtsbewegung frisst der Compounding-Effekt Rendite, auch wenn die These langfristig aufgeht. Für taktische Positionen (Tage/Wochen) gebaut, nicht für Buy-and-Hold.
