# ADR-0004: Freie Entwürfe über ein generisches, parametrisches Bauteilmodell

- Status: akzeptiert
- Datum: 2026-10-02
- Ergänzt: [ADR-0002](0002-projektmodell-und-command-log.md)

## Kontext

Bisher kann die Plattform nur Vorhaben planen, für die ein Construction Pack programmiert wurde
(Hochbeet). Der Kernnutzen laut Roadmap ist aber, *beliebige* Bauvorhaben zu beschreiben und zu
planen. Ein Pack pro Objektart skaliert nicht – es gibt Millionen möglicher Vorhaben.

Gleichzeitig gilt weiter der Grundsatz aus ADR-0002 und den Agent-Regeln: **Das LLM rechnet
nicht.** Bilder oder Mengen, die ein Sprachmodell frei erzeugt, sind nicht maßhaltig, nicht
reproduzierbar und passen nicht zur Stückliste.

## Entscheidung

1. **Das LLM entwirft, die Engine rechnet.** Für Vorhaben ohne Pack schreibt das LLM einen
   *Entwurf* (`AssemblyDesign`): benannte Parameter mit Grenzen, Bauteile als achsparallele Quader
   (optional um eine Achse gedreht) mit Katalogmaterial, Größe und Position als Ausdrücke über die
   Parameter, Wiederholungen (`repeat`), Bedingungen (`when`), Beschläge, Bauschritte und Varianten.
2. **Der Entwurf ist Eingabe, nicht Ergebnis.** Er liegt in `ProjectInputs.design` und wird über
   Commands geändert (`create_project` mit Entwurf, `replace_design`). Parameteränderungen
   („50 cm breiter“) laufen wie bei Packs über `set_parameters`/`change_parameter_by` und sind ohne
   LLM deterministisch.
3. **Die Engine prüft jeden Entwurf** (`calc_engine.assembly`) und lehnt ihn mit konkreten,
   für das LLM verständlichen Fehlern ab:
   - Material existiert im Katalog; Querschnitt bzw. Plattenstärke passt; Länge ≤ Handelslänge,
     Plattenzuschnitt ≤ Plattenformat.
   - Keine Durchdringung von Bauteilen; alle Teile hängen zusammen; Bodenkontakt (bzw. Wand bei
     Wandmontage); nichts unter Bodenniveau.
   - Größen- und Mengengrenzen (max. 4 m Kantenlänge, 2,5 m Höhe, 400 Bauteile).
4. **Die Engine leitet alles ab:** Stückliste, Zuschnitt mit Handelslängen-Optimierung bzw.
   Plattenaufteilung, Schrauben aus erkannten Kontaktflächen, Oberflächenmittel aus der Fläche,
   Kosten, Gewicht, Kippwarnung, Werkzeug, Zeichnungen (Ansichten, Draufsicht, Isometrie mit
   Positionsnummern, automatische Bemaßung, Materiallegende) und 3D-Daten für den Browser.
5. **Vertrauensstufen** werden im Ergebnis geführt (`ConstructionResult.trust`) und angezeigt:
   - `pack` – programmiertes Pack mit fachlich validierten Regeln (Hochbeet),
   - `template` – vom Team erstellte Vorlage im Entwurfsformat (Regal, Gartenbank, Werkbank, Fensterladen),
   - `ai_draft` – vom LLM frei erzeugter Entwurf, gekennzeichnet als „KI-Entwurf, nicht fachlich
     geprüft“ (Transparenz nach Art. 50 KI-Verordnung).
   Häufig genutzte KI-Entwürfe können zu Vorlagen und später zu Packs reifen.
6. **Vorlagen zuerst.** Der Agent nutzt eine passende Vorlage (`create_from_template`) und passt
   Parameter an; er entwirft frei (`design_project`) nur, wenn keine Vorlage passt. Das spart
   Tokens und erhöht die Qualität.
7. **Grenzen bleiben:** Keine tragenden Gebäudeteile, Dächer, Carports, Balkone, Treppen,
   Absturzsicherungen, Elektro/Gas. Das Sicherheits-Gate und die Größengrenzen der Engine setzen
   das durch; Ergebnisse bleiben Planungshilfe ohne Standsicherheitsnachweis.

## Konsequenzen

- Die Plattform kann alles planen, was sich aus Brettern, Kanthölzern, Platten und Beschlägen
  zusammensetzen lässt, ohne Code pro Objektart.
- Qualität der freien Entwürfe hängt vom Modell ab (Konstruktionsidee), nicht aber die Richtigkeit
  der Mengen und Zeichnungen. Für freie Entwürfe ist ein starkes Modell nötig; Kosten pro Entwurf
  grob 15–25 ct (Schätzung, wird nach den ersten Läufen gemessen).
- Der Katalog wird zur zentralen Fachquelle (Querschnitte, Handelslängen, Formate, Preise,
  Eignung außen); seine Pflege wird wichtiger.
- Die Prüfregeln sind bewusst geometrisch-einfach (Quader, Kontaktflächen). Gehrungen,
  Ausklinkungen und Holzverbindungen werden nicht modelliert; die Schraubenmenge ist ein Richtwert.
- Painter-Sortierung der Zeichnung ist für achsparallele Quader exakt, für gedrehte Teile eine
  Näherung.

## Ergänzung 2026-10-05: Maßholz, Beschläge, Wandmontage

Anlass: Ein Fensterladen „aus Brettern“ wurde als Kantholzrahmen (45 × 70 mm) entworfen, weil
der Katalog Douglasie/Lärche nur als 28-mm-Brett bzw. Kantholz führte und 18 mm nur als Fichte
(innen). Scharniere und Verschluss standen nur im Anleitungstext, nicht in der Stückliste, und die
KI-Erläuterung beschrieb nach einem Umbau noch die alte Konstruktion.

1. **Maßholz statt fester Artikel.** Jede Holzart mit `lumber_price_m3` im Katalog ist in jedem
   Querschnitt bestellbar (Stärke 8–200 mm, Breite bis 400 mm): `lumber_<holzart>_<t>x<b>` oder
   `lumber_<holzart>` (Querschnitt aus den zwei kleineren Bauteilmaßen, damit er Parametern folgen
   kann). Der Meterpreis ist Holzvolumen × Preis je m³; die Stückliste weist auf Bestellung im
   Holzfachhandel hin (Regel `FD-LUMBER`). Teure Holzarten kosten mehr, werden aber nicht ersetzt.
2. **Beschläge sind Pflicht, wenn die Anleitung sie nennt** (`FD-HW`). Katalogbeschläge tragen einen
   `hardware_type` (`hinge`, `latch`, `handle`, …). Nennt ein Bauschritt Scharniere/Bänder,
   Verschlüsse oder Griffe ohne passenden Beschlag unter `hardware`, wird der Entwurf mit den
   passenden Katalog-IDs abgelehnt. Außenprojekte warnen bei nicht außentauglichen Beschlägen.
3. **Wandmontage mit getrennten Baugruppen.** Bei `support="wall"` dürfen mehrere Baugruppen
   unverbunden sein (z. B. zwei Ladenflügel), sofern jede an der Wand anliegt.
4. **Erläuterungen folgen dem Entwurf.** `replace_design` entfernt KI-Erläuterungen des alten
   Entwurfs (Nutzernotizen bleiben). Schreibende Agent-Werkzeuge laufen pro Agent-Lauf
   nacheinander, damit parallele Tool-Aufrufe nicht um dieselbe Sequenznummer konkurrieren.
5. **Prompt:** Material-, Holzart-, Stärke- und Bauweisewünsche des Nutzers sind verbindlich;
   interne Begriffe (Pack, Katalog, IDs) werden dem Nutzer gegenüber nicht verwendet.
6. **Vorlage `window_shutter`:** Brett-Fensterladen mit Querleisten, 1–2 Flügel, Ladenbänder,
   Schubriegel und Sturmhaken; die Brettanzahl je Flügel ergibt sich automatisch (Bretter ca.
   100 mm breit), die Bandlänge (100/200/300 mm) aus der Flügelbreite.
7. **Beschläge sichtbar machen.** Ladenbänder und Schubriegel haben feste Maße und werden als
   Bauteile an der Einbaustelle platziert (Zeichnung, 3D, Positionsnummer); sie erfüllen `FD-HW`
   ebenso wie Einträge unter `hardware`. Wandmontierte Entwürfe erhalten zusätzlich die Ansichten
   „Isometrie Wandseite“ (`iso_back`) und „Rückansicht (Wandseite)“ (`back`), weil Querleisten
   und Beschläge dort sitzen; eine Vorderansicht allein zeigt z. B. bei Fensterläden nur Bretter.
