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
   - `template` – vom Team erstellte Vorlage im Entwurfsformat (Regal, Gartenbank, Werkbank),
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
