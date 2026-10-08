# ADR-0007: Freie Formen, Stäbe, Holzverbindungen und Gebäude

- Status: akzeptiert
- Datum: 2026-10-08
- Ergänzt: [ADR-0004](0004-freie-entwuerfe-bauteilmodell.md) (ersetzt dort §7 für Gebäude)

## Kontext

Das Bauteilmodell aus ADR-0004 kannte nur Quader, optional um eine Achse gedreht. Ein Nutzer
wollte ein Tonie-Regal „in Form einer Wolke“; der Assistent musste antworten, die Engine könne
nur rechteckige Rohteile, die Form müsse man selbst anbringen. Ebenso wenig ließen sich
Fachwerk (schräge, gezapfte Streben), Dächer oder ganze Gebäude planen: ADR-0004 §7 schloss
tragende Gebäudeteile und Dächer aus, die Größengrenze lag bei 4 × 4 × 2,5 m.

Gewünscht ist, dass die Plattform alle Formen und auch Fachwerkhäuser vollständig planen kann.
Weiterhin gilt: **Das LLM rechnet nicht.** Es benennt Formen und Verbindungen, Kontur, Winkel,
Längen, Mengen und Zeichnungen berechnet die Engine.

## Entscheidung

1. **Bauteile sind Prismen.** Jedes Bauteil ist eine 2D-Kontur in seiner Fläche quer zum
   dünnsten Maß, extrudiert über die Stärke und an den Enden beschnitten. Es gibt zwei
   Platzierungen:
   - *Quader* wie bisher (`size`, `at`, optional `rotate`),
   - *Stab* zwischen zwei Punkten (`start`, `end` = Mitte der Enden) mit Querschnitt aus dem
     Material oder `section`, Ausrichtung `facing` und Endschnitten `cuts`: `square`, `level`
     (Waagschnitt), `plumb` (Lotschnitt), `corner` (beides, z. B. Strebe in der Gefachecke).
     Die Engine bestimmt Zuschnittlänge und Neigung.
2. **Formen erzeugt die Engine.** `shape` mit `cloud`, `ellipse`, `rounded`, `triangle`, `arch`
   oder `polygon` (Punkte u, v); `cutouts` (Rechteck, Ellipse, Polygon) für Fenster, Grifflöcher,
   Fächer. Die Engine prüft, dass Ausschnitte innerhalb der Kontur liegen und sich nicht
   überschneiden. Für Holz- und Plattenteile mit Kontur entsteht je Position eine
   Schablonen-Zeichnung (`template_<pos>`); der Zuschnitt erfolgt aus dem Rohteil (Hüllrechteck).
3. **Exakte Geometrie.** Teile werden in konvexe Stücke zerlegt (Ohrenschneiden mit Lochbrücken).
   Durchdringung prüft der Separating-Axis-Test, Kontaktflächen ergeben sich aus koplanaren,
   gegenüberliegenden Flächen (Polygonschnitt). Achsparallele Quader behalten den bisherigen
   exakten Pfad, bestehende Entwürfe rechnen unverändert. Zeichnungen sortieren Teile über
   trennende Ebenen; Flächen mit Ausschnitten werden als Polygone mit Löchern gezeichnet. Teile,
   die keine einfachen Quader sind, erhalten ein Dreiecksnetz für die 3D-Ansicht.
4. **Holzverbindungen** (`joints`) werden zwischen Bauteil-IDs deklariert und gelten für alle
   sich berührenden bzw. überlappenden Instanzen:
   - `tenon` (Zapfen): Stärke 1/3 des Holzes, Länge 0,4 × Gegenholz (30–60 mm), Zuschnittlänge
     wird je Zapfenende verlängert, je Zapfen ein Holznagel (zwei ab 200 mm Breite),
   - `half_lap` (Blatt): Überlappung erlaubt, je Teil halbe Überdeckung, ein Holznagel,
   - `notch` (Kerve): Überlappung bis 1/3 der Bauteilhöhe, eine Holzbauschraube.
   Nur deklarierte Verbindungen dürfen sich durchdringen; dort entfallen automatische Schrauben.
   Die Anleitung erhält den Schritt „Holzverbindungen anreißen und ausarbeiten“.
5. **Flächen- und Volumenmaterial** (`kind="bulk"`): Ausfachung (Lehmstein, Porenbeton), Beton,
   Dämmung nach m³, Dachdeckung und Schalung nach m², jeweils mit erlaubtem Stärkenbereich und
   5 % Verschnitt. Neu im Katalog: Bauholz (KVH Fichte bis 13 m, Eichenbalken bis 10 m),
   Holzbauschrauben 8 × 200/240 mm, Holznägel, Holzfenster und Haustür als Fertigteile.
6. **Gebäude** (`category="building"`): Grenzen 25 × 25 m Grundfläche, 15 m Höhe, 1500 Bauteile.
   Nur Betonteile dürfen unter Geländeniveau (Fundamente). Statt „Planungshilfe ohne Statik“
   erscheint der Warnhinweis `BUILDING` (Regel `FD-BUILD`): Tragwerk, Gründung, Dach und
   Aussteifung brauchen eine Statik vom Tragwerksplaner, meist auch eine Baugenehmigung; die
   Engine prüft keine Standsicherheit und keinen Wärme-, Feuchte-, Brand- oder Schallschutz.
7. **Sicherheitsregeln:** Das Safety-Gate (Version 2) verweist weiter bei Eingriffen in
   *bestehende* tragende Bauteile (Wanddurchbruch, Dachstuhl ändern, Sparren kürzen) an
   Fachleute, blockiert aber nicht mehr die Planung eines neuen Hauses. Balkone, Treppen,
   Absturzsicherungen und Spielgeräte mit Absturzhöhe bleiben ausgeschlossen.
8. **Vorlagen:** `cloud_shelf` (Wolkenregal) und `timber_frame_house` (eingeschossiges
   Fachwerkhaus mit Streifenfundament, Bodenplatte, Schwellenkranz mit Blattstößen, gezapften
   Ständern, Streben und Riegeln, Rähm, Deckenbalken, gekervtem Sparrendach mit Ziegeldeckung,
   Giebelschalung, ausgemauerten Gefachen, Fenstern und Haustür). Beide sind über ihren ganzen
   Parameterbereich gültig.

## Konsequenzen

- Die Plattform kann beliebige Konturen und Holzbauwerke bis Hausgröße planen. Schablone,
  Zuschnitt, Winkel, Zapfen, Mengen und 3D kommen aus der Engine.
- Der Entwurfs-Schema-Teil der Anfrage wächst um ca. 1,1K Token, das statische Präfix um ca.
  1,7K Token (siehe `docs/ai/PROMPT_CHANGELOG.md`, Version 2026-10-08.1).
- Gebäudeentwürfe sind und bleiben Planungshilfen. Die Ergebnisse ersetzen weder Statik noch
  Bauantrag, Wärmeschutznachweis oder Fachplanung für Haustechnik.
- Grenzen der Geometrie: Kontur und Schrägschnitt lassen sich an einem Stab nicht kombinieren;
  Endschnitte flacher als 10° zur Stabachse werden abgelehnt; die Zerlegung nicht-konvexer
  Teile kann bei sehr feinen Konturen mehr Rechenzeit kosten (Wolke: ca. 150 Stücke).
