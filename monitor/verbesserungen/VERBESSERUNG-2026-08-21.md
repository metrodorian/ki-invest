> **Protokoll, nicht Dokumentation.** Dies ist der Bericht des
> Verbesserungslaufs vom 21.08.2026, so wie er ihn geschrieben hat. Der Text
> bleibt unverändert stehen, auch wo er sich später als falsch erwiesen hat —
> ein nachträglich geglättetes Protokoll wäre wertlos. Ältere Läufe liegen unter
> `verbesserungen/`.
>
> **Nachträglich richtiggestellt (22.08.2026):** Der Abschnitt „Aufgefallen"
> vermutet, ein `git rm` ohne `--cached` habe `tokennutzung.json` gelöscht. Das
> stimmt nicht — der Befehl wurde mit `--cached` ausgeführt, die Datei war beim
> Hereinkopieren schlicht noch nicht geschrieben. Die Beobachtung selbst war
> richtig: Es gab noch keinen Vergleichswert, weil erst ein Eintrag existierte.
> Der Prompt weist seither darauf hin, dass die mitgegebenen Daten eine
> Momentaufnahme vom Laufbeginn sind.

# Verbesserungslauf 21.08.2026

Sieben Vorschläge, drei davon führten zu Code. Zwei neue Indikatoren, ein
behobener Fehler, eine behobene Abschneidung im Claude-Prompt.

## Umgesetzt

### Vertiv: erhaltene Anzahlungen als Quartalsreihe

Vertiv hat den Auftragseingang mit dem Q2-2026-Bericht aufgehört zu
veröffentlichen — die Kennzahl, auf der die Vertiv-Position eigentlich ruht.
Was das Unternehmen nicht mehr in eine Pressemitteilung schreibt, muss es
trotzdem in die Bilanz stellen: Vertragsverbindlichkeiten sind Geld, das Kunden
gezahlt haben, ohne die Ware zu haben. Das ist Auftragseingang, nur eben in der
Sprache der Buchhaltung, und es läuft dem Umsatz genauso weit voraus.

Die Reihe kommt aus `data.sec.gov/api/xbrl/companyconcept`, Feld
`us-gaap:ContractWithCustomerLiabilityCurrent`, CIK 1674101. Frei, ohne
Anmeldung, dieselbe Kennung wie bei den 8-K-Meldungen. Die im Vorschlag
genannten Zahlen ließen sich bestätigen — 1,8147 Mrd. zum 31.12.2025 und
3,6337 Mrd. zum 30.06.2026, auf den Cent so wie dort behauptet.

Im Bericht steht künftig der Indikator **„Vertiv erhaltene Anzahlungen"** mit
dem Stand in Milliarden und der Veränderung zum Vorquartal. Heute: 3,63 Mrd.,
**+48 % gegenüber dem Vorquartal**, eingestuft als *gegen die These*. Das ist
ein unangenehmer, aber wichtiger Befund: Die Reihe lautet 1,10 / 1,26 / 1,13 /
1,81 / 2,46 / 3,63 Mrd. — sie hat sich in zwei Quartalen verdoppelt. Kunden
zahlen weiter im Voraus. Die Vertiv-Position kämpft gerade gegen bezahlte
Nachfrage, nicht gegen eine Erwartung.

Entscheidungsrelevant ist die Richtung: Fällt der Posten zum ersten Mal
gegenüber dem Vorquartal, ist das die früheste harte Bestätigung, die es für
diese Position überhaupt geben kann — zwei bis drei Quartale, bevor der Umsatz
es zeigt. Steigt er weiter, trägt die These die Position nicht und der Stop
zählt mehr als das Argument.

Vorbehalt steht in der Erklärung: Es ist nur der kurzfristige Teil (der
langfristige lag zuletzt bei 0,12 Mrd., also rund ein Dreißigstel), und
Zukäufe bringen fremde Bestände mit, die wie eigenes Wachstum aussehen.

*Dateien:* `ki_monitor.py` (`sec_konzept_reihe`, `bilanzreihen_holen`,
`indikatoren_bauen`), `config.json` (Herkunft und Reihe unter
`kennzahlen.vertiv_auftraege.ersatzindikator`), `README.md`.

### Nvidia: Vorratsreichweite in Tagen

Der Vorschlag wollte Einkaufsverpflichtungen *und* Vorräte als Reihe. Die
Einkaufsverpflichtungen sind nicht zu bekommen — siehe „Verworfen". Die
Vorräte schon, und mit dem Wareneinsatz daneben ergibt sich die Reichweite:
wie lange Nvidia braucht, um das Lager abzuverkaufen.

Die blanke Milliardenzahl wächst mit dem Unternehmen mit und sagt nichts. Die
Reichweite ist über Quartale vergleichbar: 80 Tage (Jul 24), 77 (Okt 24), 59
(Apr 25), 105 (Jul 25), 118 (Okt 25), 113 (Apr 26). Der Bestand ist von 6,7 auf
25,8 Mrd. gestiegen, die Reichweite hat sich in einem Jahr fast verdoppelt.

Im Bericht: **„Nvidia Vorratsreichweite"**, heute 113 Tage, −4 Tage gegenüber
dem Vergleichsquartal, also *neutral*. Die Konfiguration nannte eine
Vorratsabschreibung bisher „das deutlichste Einzelsignal überhaupt" — jetzt ist
der Vorlauf dazu messbar, statt nur benannt.

Die Erklärung sagt ausdrücklich, dass der Wert **für sich allein zweideutig**
ist: Ein Aufbau vor einem bereits verkauften Hochlauf sieht genauso aus wie
unverkäufliche Ware. Hart wird das Signal erst, wenn die Reichweite steigt *und*
die Umsatzprognose verfehlt wird. Vor dem Quartal am 26.08. ist das die Zahl,
die man daneben legt.

Die Quartale zum Januar fehlen in der Reihe, weil der Wareneinsatz dafür nur als
Jahressumme im 10-K steht. Deshalb steht im Bericht das Vergleichsdatum und
nicht das Wort „Vorquartal" — der Sprung geht dort über zwei Quartale.

*Dateien:* wie oben, dazu `kennzahlen.nvidia_quartal.vorratsreichweite` in
`config.json`.

### Fehler: „Preis je Million Token" hing im falschen Block

Beim Nachsehen zu Vorschlag vier fiel ein echter Fehler auf. Der Indikator
„Preis je Million Token" — laut README *der direkte Effizienzmesswert* — stand
eingerückt im Block des Verbrauchsanteils statt im Block der Tokenpreise. Drei
Folgen:

1. Er verschwand komplett aus dem Bericht, sobald die OpenRouter-Rangliste nicht
   lesbar war, obwohl seine eigene Datenquelle einwandfrei war.
2. Die angezeigte Preisänderung war gar keine. Die Variable `v` war eine Zeile
   vorher mit der *Punktveränderung des China-Anteils* überschrieben worden und
   wurde als Prozentänderung des Preises ausgegeben — samt Vergleichsdatum aus
   der Preisreihe. Auch die Einstufung *für/gegen die These* rechnete mit dieser
   falschen Zahl.
3. War umgekehrt die Preisreihe leer und die Rangliste vorhanden, lief der
   ganze Lauf mit `NameError` auf `j` gegen die Wand.

Der Block steht jetzt dort, wo `j` und `v` die Tokenpreise meinen. Beide
Ausfallwege sind einzeln nachgestellt und geprüft.

*Datei:* `ki_monitor.py`, `indikatoren_bauen`.

### Claude sah nur die ersten zwölf Indikatoren

Ebenfalls beim Nachsehen aufgefallen und mitbehoben: `claude_fragen` schnitt die
Indikatorenliste bei zwölf ab. Die Liste ist auf achtzehn gewachsen.
Abgeschnitten wurden dadurch ausgerechnet Preislücke, Preis je Million Token,
chinesischer Verbrauchsanteil und Speicherpreise — die gesamte Effizienzseite
der These, also der Teil, den der Kursblock gerade *nicht* abbildet. Die
Tokenpreistabelle erreicht Claude über einen eigenen Abschnitt, der
Verbrauchsanteil und die Speicherpreise erreichten es gar nicht.

Die Grenze steht jetzt bei 40. Ohne das wären auch die beiden neuen
Bilanzindikatoren nie bei der Einordnung angekommen und der ganze Umbau folgenlos
geblieben.

### Nebenwirkung: die Zusammenfassung wurde einheitenblind

Die Zusammenfassung nennt die zwei stärksten Indikatoren je Richtung und
sortiert dafür nach `abs(wert)`. Das mischt Einheiten. Mit den neuen Indikatoren
hätte dort „Vertiv erhaltene Anzahlungen (+3,6)" gestanden — 3,6 was?

Indikatoren können jetzt optional `vergleichswert` (eine vergleichbare Zahl zum
Sortieren) und `kurzwert` (ein lesbarer Text) mitgeben. Wer beides weglässt,
wird behandelt wie bisher; es ändert sich also nichts an bestehenden
Indikatoren. Im Bericht steht jetzt „Gegen die These läuft vor allem **Vertiv
erhaltene Anzahlungen** (3,63 Mrd. USD, +48 %)".

## Verworfen

**Vertiv-Auftragsbestand aus dem Bilanzanhang.** Vertiv zeichnet ihn in keinem
einzigen XBRL-Feld aus — die kompletten `companyfacts` enthalten weder `Backlog`
noch `RemainingPerformanceObligation`; die Zahl steht nur als Fließtext im
Bericht. Ohne belastbare Reihe lieber keine Zahl.

**Nvidias Einkaufsverpflichtungen als Reihe.** Nicht durchgängig ausgezeichnet:
`us-gaap:PurchaseObligation` bricht mit dem Quartal zum 27.07.2025 ab (letzter
Wert 45,8 Mrd.), `OtherCommitment` springt von 13,7 auf 6,5 Mrd. Der im Bericht
genannte Wert von über 145 Mrd. lässt sich aus keinem dieser Felder
rekonstruieren. Eine aus wechselnden Feldern zusammengesetzte Reihe wäre
erfunden. Die Vorräte sind der belastbare Ersatz, weil eine Abschreibung dort
zuerst sichtbar wird.

**Neocloud-Anleihe (CoreWeave) als Risikoaufschlag.** Keine freie Quelle
gefunden: FRED liefert zur Suche „coreweave" null Reihen und führt
Kreditaufschläge grundsätzlich nur als Index, nicht je Emittent; FINRAs
Anleihesuche lädt ihre Daten per Javascript nach und gibt im HTML nichts her.
Einzelemittenten-Aufschläge stehen sonst hinter einer Bezahlschranke. Der
CCC-Aufschlag bleibt der nächstbeste freie Ersatz und ist bereits im Bericht.

**Vertiv gegen einen Korb aus Stromausrüstern.** Das wäre der achte
Relativstärke-Indikator und misst dieselbe Rotation wie die vorhandene
Bau-Relativstärke, in deren Korb Vertiv ohnehin sitzt.

**Stichwortfilter enger ziehen.** Die beiden genannten Fehlgriffe sind echt —
eine Klage wegen eines Baustopps ist kein Nachfragesignal. Aber genau dafür gibt
es die Claude-Umstufung, die seit dem letzten Lauf auch die Nachrichtenbilanz
und damit das Barometer ändert; in diesem Lauf hat sie zwei Meldungen umgestuft.
Eine allgemeine Sperre auf Prozesswörter („sues", „lawsuit") würde echte Signale
mit unterdrücken — eine Klage von Anleihegläubigern wegen Zahlungsausfalls ist
das stärkste Signal für die These, das es gibt. Der Vorschlag ist als Befund
richtig und als Codeänderung falsch.

**CFTC-Terminmarkt für Rechenleistung.** Nach eigener Einschätzung des
Vorschlags „vor dem 17. September ohne Wirkung". Eine zusätzliche
Nachrichtensuche dafür ändert bis zum Zeitlimit keine Entscheidung.

## Aufgefallen

**Die Verlaufsdatei `tokennutzung.json` war leer.** Deshalb steht beim
chinesischen Verbrauchsanteil heute keine Veränderung, obwohl der Abruf
einwandfrei funktioniert (73,7 % bei 52,9 Bio. Token). Vermutlich ist sie beim
Herausnehmen der Laufzeitdaten aus der Versionierung mitgelöscht worden —
`git rm` ohne `--cached` löscht auch auf der Platte. Dasselbe kann
`tokenpreise.json` und `state.json` getroffen haben. Sie bauen sich von selbst
wieder auf; nach einer Woche steht die Wochenveränderung wieder da. Nichts zu
tun, aber gut zu wissen, wenn nächste Woche wieder eine Veränderung fehlt.

**Der Vergleich beim Verbrauchsanteil ist ein Tages-, kein Wochenvergleich.**
`tokennutzung_holen` vergleicht mit dem letzten Eintrag, der einen Wert hat —
also mit gestern. Die OpenRouter-Rangliste ist aber ein rollender Wochenwert;
zwischen gestern und heute wechselt nur ein Siebtel der Grundlage. Die
Schwellen des Indikators (±1 Punkt) sind auf eine Wochenveränderung geeicht, die
gemessene Zahl ist eine Tagesveränderung. Ich habe das nicht angefasst, weil die
Datei ohnehin leer ist und ich die Auswirkung erst über mehrere Tage sehen
könnte. Wer es anfasst: den Vergleichseintrag nach Datum suchen, sieben Tage
zurück, nicht einfach den vorherigen nehmen.

**Die Zusammenfassung sortiert Basispunkte gegen Prozente.** „Dafür sprechen
Risikoaufschlag CCC und schlechter (+1030,0)" steht dort nur, weil 1030
Basispunkte die größte Zahl im Feld sind — nicht weil der Aufschlag sich stark
bewegt hätte. Der Indikator führt bereits `veraenderung_monat`, und das
Barometer rechnet auch damit statt mit dem Stand. Der eine Handgriff wäre,
`veraenderung_monat` als Rückfallwert in `sortwert` aufzunehmen. Ich habe es
gelassen, weil es das Verhalten bestehender Indikatoren ändert und niemand es
vorgeschlagen hat. Das neue Feld `vergleichswert` ist der Platz dafür.

**Der Kommentar „Was treibt das Barometer" stimmt nicht mehr.** Die
Zusammenfassung listet dort alle Indikatoren mit Einstufung gut/schlecht, aber
das Barometer gewichtet nur sieben davon namentlich. CCC-Aufschlag, Preislücke,
Verbrauchsanteil, Speicher und die beiden neuen Bilanzposten stehen im Satz und
zählen im Barometer nicht mit. Der sichtbare Satz ist trotzdem richtig — er
sagt „gegen die These läuft", nicht „das Barometer drückt". Nur der Kommentar
darüber führt in die Irre.

**Zwei .gitignore-Dateien.** `bilanzreihen.json` musste ignoriert werden, die
übrigen Laufzeitdateien stehen aber in der `.gitignore` des
Wurzelverzeichnisses — außerhalb des Projektordners, den ich anfassen darf.
Deshalb liegt jetzt eine zweite, sehr kurze `.gitignore` in `monitor/`. Das
funktioniert, ist aber ein Ort mehr zum Nachsehen. Wer aufräumt: die eine Zeile
nach oben ziehen und die Datei hier löschen.

**Die CIKs stehen zweimal.** `BILANZ_KONZEPTE` in `ki_monitor.py` nennt 1045810
und 1674101, die auch schon unter `sec_firmen` in der `config.json` stehen. Ich
habe es so gelassen, weil die Zuordnung Firma-zu-Bilanzposten eine Sache des
Codes ist und CIKs sich nicht ändern — aber es ist eine Dopplung.

**Nvidias viertes Quartal fehlt dauerhaft in der Reichweitenreihe.** Der
Wareneinsatz steht dafür nur als Jahressumme im 10-K. Man könnte ihn ausrechnen
(Jahr minus Q1 bis Q3) und die Reihe lückenlos machen. Das ist ein zusätzlicher
Rechenweg mit eigenem Ausfallweg für einen Schönheitsfehler; der Bericht nennt
stattdessen das tatsächliche Vergleichsdatum. Wenn die Lücke stört: an dieser
Stelle ansetzen.
