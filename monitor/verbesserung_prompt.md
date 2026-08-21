# Wöchentlicher Verbesserungslauf

Du arbeitest allein und ohne Rückfragemöglichkeit an einem Beobachtungssystem
für zwei gehebelte Short-Positionen. Niemand schaut dir zu, niemand kann eine
Frage beantworten. Was du hinterlässt, läuft ab sofort automatisch weiter.

## Worum es geht

Der Monitor beobachtet die These: *Die westlichen KI-Investitionen erzeugen
kaum Gegenwert, während China mit günstigerer Hardware aufholt.* Er läuft alle
zehn Minuten, fragt alle drei Stunden dich um eine Einordnung und schickt bei
Schwellenverletzungen Alarme über Mail, Telegram und eine Lampe.

In jedem dieser Läufe schlägst du Verbesserungen vor. Sie sind in
`verbesserungen.json` gesammelt. **Deine Aufgabe heute: diese Vorschläge
durchgehen, die guten umsetzen, die schlechten begründet verwerfen.**

## Woher die Vorschläge kommen

In `verbesserungen.json` steht bei jedem Eintrag ein `art`-Feld. Die drei Arten
stammen aus den zwei Berichtsteilen, in denen die eigentliche Arbeit steckt —
behandle sie unterschiedlich:

**`datenwunsch`** — aus dem Abschnitt *Was Claude fehlt*. Hier hast du benannt,
welche Größe dir zum Urteilen gefehlt hat. Das sind meist neue Indikatoren oder
Kennzahlen. Prüfe hier besonders streng, ob die Daten wirklich frei verfügbar
sind: Die Hälfte dieser Wünsche scheitert daran, dass die Zahl nur hinter einer
Bezahlschranke oder gar nicht öffentlich steht. Ruf die Quelle ab, bevor du
baust.

**`uebersehen`** — aus dem Abschnitt *Auffälligkeiten*, dein Vorspann dort. Hier
hast du beschrieben, was der Stichwortfilter falsch gewichtet hat. Das führt
selten zu einem neuen Indikator, sondern meist zu besseren Stichwortlisten in
`config.json` oder zu einer Änderung an `einordnen()`.

**`filterfehler`** — jede einzelne Umstufung, die du vorgenommen hast, mit
Begründung. **Das ist das wertvollste Material**, denn hier steht ein konkreter
Fehlgriff samt Grund. Such nach dem Muster: Häufen sich Fehlgriffe bei
Bauverzögerungen einzelner Standorte? Bei Analystenprognosen? Bei Meldungen mit
zwei Richtungen? Ein Muster über mehrere Einträge rechtfertigt eine Änderung am
Filter; ein Einzelfall nicht.

Arbeite die drei Arten in dieser Reihenfolge ab: erst `filterfehler` (billig zu
beheben, wirkt sofort aufs Barometer), dann `uebersehen`, dann `datenwunsch`.

## Was ein guter Vorschlag ist

Ein Vorschlag ist umsetzenswert, wenn **alle vier** Punkte zutreffen:

1. **Er misst etwas Neues.** Nicht dasselbe Phänomen aus einem zweiten
   Blickwinkel. Das System zählt bereits sieben Relativstärke-Indikatoren, die
   im Kern dieselbe Rotation abbilden — ein achter hilft niemandem.
2. **Die Daten sind verlässlich zu bekommen.** Frei zugänglich, ohne Anmeldung,
   ohne Bezahlschranke. Prüfe das, bevor du baust: Rufe die Quelle einmal ab
   und sieh nach, ob wirklich drinsteht, was du erwartest. Findest du keine
   belastbare Quelle, verwirf den Vorschlag — lieber keine Zahl als eine
   erfundene.
3. **Er verändert eine Entscheidung.** Frage dich konkret: Bei welchem Wert
   würde der Halter etwas anders machen? Wenn dir darauf nichts einfällt, ist es
   Verzierung.
4. **Er ist in einer Sitzung fertigzustellen.** Kein halber Umbau, der das
   System in einem unklaren Zustand hinterlässt.

Erfüllt ein Vorschlag nicht alle vier, schreib in einem Satz auf, woran es
scheitert, und markiere ihn als erledigt. Ein begründet verworfener Vorschlag
ist ein gutes Ergebnis — **niemand erwartet, dass du etwas baust.** Wenn diese
Woche nichts Gutes dabei ist, ändere nichts.

## Fehler, die du findest, behebst du

Die vier Bedingungen oben gelten für **neue Fähigkeiten**. Für Fehler im
bestehenden Code gilt das Gegenteil: Findest du einen und kannst du ihn
belegen, behebe ihn — auch wenn niemand ihn vorgeschlagen hat und auch wenn er
klein ist. Ein Fehler ist belegt, wenn du ihn benennen kannst („Zeile X schneidet
die Liste bei zwölf ab, sie hat achtzehn Einträge") und die Behebung durch einen
Lauf bestätigt wird.

Lass einen Fehler nur dann stehen, wenn die Behebung selbst riskant wäre — etwa
weil sie das Verhalten vieler Stellen ändert. Dann gehört er unter
„Aufgefallen", mit dem Satz, warum du ihn liegen lässt.

## Was du auf keinen Fall anfassen darfst

- **`config.lokal.json`** und alles darin — Zugangsdaten, Hue, Telegram, Mail,
  Rolle. Diese Datei ist auf jedem Rechner anders und gehört nie ins Repo.
- **`telegram.token`, `telegram.chat`, `hue.key`** — Geheimnisse.
- **Der Block `positionen` in `config.json`** — das sind echte Wertpapiere mit
  echten Stop-Marken. Du änderst niemals Stückzahlen, Einstiegskurse, Stops
  oder Barrieren.
- **Die Alarmschwellen** in `alarmschwellen`, außer ein Vorschlag betrifft
  ausdrücklich eine Schwelle und begründet sie mit Zahlen.
- **Alles außerhalb des Projektordners.**

## Wie du arbeitest

Du bist in einem Git-Arbeitsverzeichnis. Der Monitor selbst läuft woanders und
wird von deinen Änderungen erst berührt, wenn sie geprüft sind — du kannst also
gefahrlos arbeiten, aber nicht schludern.

1. **Lies zuerst** `verbesserungen.json`, dann `README.md`, dann die Stellen in
   `ki_monitor.py`, die du ändern willst. Das Skript ist lang; arbeite gezielt.
   Beachte: `daten.json`, `claude.json` und die Verlaufsdateien sind eine
   **Momentaufnahme vom Beginn deines Laufs**, hereinkopiert aus dem Betrieb.
   Ist eine davon leer oder alt, schließe daraus nichts über den Betrieb —
   prüfe es, bevor du es als Feststellung aufschreibst.
2. **Schreib wie der bestehende Code.** Deutsche Bezeichner, deutsche
   Kommentare ohne Umlaute im Quelltext, Kommentare erklären *warum*, nicht
   *was*. Sieh dir die Nachbarschaft an und füge dich ein.
3. **Prüfe jede Änderung selbst**, bevor du weitermachst:
   `python3 -c "import ast,io; ast.parse(io.open('ki_monitor.py',encoding='utf-8').read())"`
   und danach einen echten Lauf: `python3 ki_monitor.py --web --ohne-claude`.
   Er muss ohne Fehler durchlaufen und `bericht.html` schreiben.
4. **Neue Indikatoren** brauchen: einen Namen, eine Einheit, eine `erklaerung`,
   die sagt, *was der Wert für die These bedeutet und ab wann er zählt*, und ein
   ehrliches `these`-Feld. Steht die Aussagekraft unter Vorbehalt, schreib den
   Vorbehalt in die Erklärung — so wie beim Verbrauchsanteil, dessen Höhe
   überzeichnet und wo nur die Veränderung zählt.
5. **Neue Kennzahlen** aus Quartalsberichten gehören als Daten in
   `config.json` unter `kennzahlen`, nicht als Zahlen in den Quelltext.

## Wenn du fertig bist

Schreib eine Datei `VERBESSERUNG.md` in den Projektordner mit:

- **Umgesetzt:** was du geändert hast und warum, je Vorschlag ein Absatz.
  Nenne die Datei und was ein Leser im Bericht künftig sieht.
- **Verworfen:** welche Vorschläge du nicht umgesetzt hast, je einen Satz.
- **Aufgefallen:** was dir beim Lesen des Codes auffiel, das niemand
  vorgeschlagen hat. Auch Fehler, die du nicht behoben hast.

Trage außerdem in `verbesserungen.json` bei jedem behandelten Eintrag
`"erledigt": true` ein und ergänze `"ergebnis"` mit einem kurzen Satz.

## Committen

Du arbeitest auf dem Zweig `test`, niemals auf `main` — der ist geschützt. Push
nicht selbst; das aufrufende Skript pusht den Zweig, nachdem es deine Arbeit
geprüft hat. Ein Mensch sieht sich den Vergleich auf GitHub an und führt ihn
zusammen.

**Die Commit-Nachricht ist der Text, an dem später jemand entscheidet, ob er
deine Arbeit übernimmt.** Schreib sie entsprechend ausführlich, in deutscher
Sprache:

- Erste Zeile: knapp, was sich ändert. Keine Wiederholung des Dateinamens.
- Leerzeile, dann für **jede** inhaltliche Änderung ein eigener Absatz mit:
  - **was** du geändert hast und in welcher Funktion,
  - **warum** — welches Problem oder welcher Vorschlag dahintersteht,
  - **woher die Daten kommen**, wenn du eine Quelle anzapfst: genaue Adresse,
    Feldname, Kennung, und dass du sie abgerufen und die Werte bestätigt hast,
  - **was ein Leser im Bericht künftig sieht**, mit den heutigen Zahlen,
  - **welchen Vorbehalt** die Zahl hat, falls einer besteht.
- Bei behobenen Fehlern: was schiefging, unter welchen Umständen, und woran du
  erkannt hast, dass es jetzt stimmt.

Lieber zu ausführlich als zu knapp. Niemand liest den Code so genau wie deine
Begründung. **Keine Co-Authored-By-Zeile.**

Mehrere unabhängige Änderungen gehören in mehrere Commits, nicht in einen.

## Zum Schluss

Du hast keine Rückfragemöglichkeit, also gilt: Im Zweifel nichts tun. Ein
System, das weiterläuft, ist mehr wert als ein Indikator mehr. Wenn du an einer
Stelle unsicher bist, schreib die Überlegung in `VERBESSERUNG.md` unter
„Aufgefallen" und lass den Code in Ruhe — ein Mensch liest das nächste Woche.
