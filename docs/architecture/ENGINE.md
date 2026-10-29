# Engine und Entwurfsformat

Ausgelagert aus [ARCHITEKTUR.md](ARCHITEKTUR.md) §6 (Inhalt unverändert, Katalogpfad korrigiert). Beschreibt, was das LLM im `AssemblyDesign` beschreibt, was die Engine prüft und was sie ableitet. Lesen, wenn an Engine, Schema oder Prüfregeln gearbeitet wird.

## 1. Was das LLM beschreibt

- **Parameter** mit Name, Einheit, Grenzen und optional Auswahlwerten.
- **Bauteile** mit Katalogmaterial. Maße und Positionen sind **Ausdrücke über die Parameter** in mm
  (x = Breite, y = Tiefe, z = oben). Zwei Platzierungen:
  - *Quader*: `size`, `at`, optional `rotate` um eine Achse;
  - *Stab* zwischen zwei Punkten: `start`, `end`, Querschnitt aus dem Material oder `section`,
    Ausrichtung `facing`, Endschnitte `cuts` (`square`, `level`, `plumb`, `corner`). Die Engine
    bestimmt Zuschnittlänge und Neigung.
- **Formen** (`shape`): `cloud`, `ellipse`, `rounded`, `triangle`, `arch`, `polygon`.
  **Ausschnitte** (`cutouts`): Rechteck, Ellipse, Polygon.
- **Wiederholungen** (`repeat`), **Bedingungen** (`when`), **Varianten**.
- **Beschläge** (`hardware`) und **Holzverbindungen** (`joints`): `tenon` (Zapfen), `half_lap`
  (Blatt), `notch` (Kerve).
- **Bauschritte** (`steps`): Reihenfolge und Montagehinweise. Die konkreten Unterschritte schreibt
  die Engine.
- Einsatzort (innen/außen), Montage (`support`: Boden oder Wand), Oberfläche und Kategorie
  (`category`, z. B. `building`).
- Material-, Holzart-, Stärke- und Bauweisewünsche des Nutzers sind verbindlich. Interne Begriffe
  (Katalog, IDs) werden dem Nutzer gegenüber nicht verwendet.

## 2. Was die Engine prüft

Jeder Entwurf wird geprüft. Bei einem Fehler lehnt die Engine ihn mit einer konkreten,
für das LLM verständlichen Meldung ab (`DesignRejectedError`).

- Material existiert im Katalog; Querschnitt bzw. Plattenstärke passt; Länge ≤ Handelslänge;
  Plattenzuschnitt ≤ Plattenformat; Schüttgut innerhalb seines Stärkenbereichs.
- **Maßholz** (`FD-LUMBER`): Jede Holzart mit `lumber_price_m3` ist in jedem Querschnitt bestellbar
  (Stärke 8–200 mm, Breite bis 400 mm), als `lumber_<holzart>_<t>x<b>` oder `lumber_<holzart>`.
  Preis = Volumen × Preis je m³. Teure Holzarten werden nie ersetzt.
- Keine Durchdringung von Bauteilen, außer bei deklarierten Holzverbindungen.
- Alle Teile hängen zusammen. Bei Wandmontage (`support="wall"`) dürfen getrennte Baugruppen
  existieren, wenn jede an der Wand anliegt.
- Boden- bzw. Wandkontakt; nichts unter Geländeniveau, außer Betonteilen bei Gebäuden.
- Ausschnitte liegen innerhalb der Kontur und überschneiden sich nicht. Endschnitte flacher als
  10° zur Stabachse werden abgelehnt. Kontur und Schrägschnitt lassen sich an einem Stab nicht
  kombinieren.
- **Beschläge sind Pflicht, wenn die Anleitung sie nennt** (`FD-HW`): Nennt ein Bauschritt
  Scharniere, Verschlüsse oder Griffe ohne passenden Beschlag, wird der Entwurf mit den passenden
  Katalog-IDs abgelehnt. Außenprojekte warnen bei nicht außentauglichen Beschlägen.
- Größen- und Mengengrenzen, siehe Kapitel 8.

## 3. Was die Engine ableitet

- **Stückliste** inkl. Maßholz-Hinweis, Schüttgut nach m³ bzw. m² mit 5 % Verschnitt.
- **Zuschnitt:** 1D-Handelslängen-Optimierung (First-Fit-Decreasing, 4 mm Sägeschnitt) und
  Plattenaufteilung.
- **Schrauben** aus erkannten Kontaktflächen (geschraubt wird durch das dünnere Teil), Holznägel
  und Holzbauschrauben aus den Holzverbindungen, Oberflächenmittel aus der Fläche.
- **Kosten** (Decimal, keine Gleitkommazahlen), **Gewicht**, **Kippwarnung**, **Werkzeug**.
- **Geometrie:** Bauteile sind Prismen, also eine 2D-Kontur extrudiert über die Stärke. Sie werden
  in konvexe Stücke zerlegt (Ohrenschneiden mit Lochbrücken). Durchdringung prüft der
  Separating-Axis-Test, Kontakt ergibt sich aus koplanaren gegenüberliegenden Flächen.
  Achsparallele Quader haben einen exakten Schnellpfad.
- **Zeichnungen:** Ansichten, Draufsicht, Isometrie mit Positionsnummern, automatische Bemaßung,
  Materiallegende, Sortierung über trennende Ebenen. Bei Wandmontage zusätzlich `iso_back` und
  `back`. Zu jedem geformten Holz- oder Plattenteil eine Schablone `template_<pos>`. Die Engine
  erzeugt eine rendererunabhängige Zeichnungs-IR, daraus wird byte-stabiles SVG und PDF.
- **3D-Daten** für den Browser (Quader und Dreiecksnetze).
- **Anleitung** mit konkreten Unterschritten (`InstructionStep.details`):
  - Einkaufen je Stücklistenzeile;
  - Zuschnitt Stange für Stange (z. B. „Stange 1 von 2 (5,00 m): 6× 800 mm (Pos. 1) … Rest ca. 180 mm“);
  - jede Verschraubung („Pos. A von <Seite> in Pos. B schrauben: n Stellen mit je k Schrauben …“);
  - „Holzverbindungen anreißen und ausarbeiten“, Oberfläche, Kippsicherung.
  - Ein Teil wird im ersten Schritt montiert, der es nennt. Die Schraubenmengen der Unterschritte
    ergeben in Summe die Kennzahl „Schrauben“.
- **Intent-Checks** (`Expectation`): Hüllmaße, begehbare Oberseite, Ebenen, Türen u. a., plus
  Konsistenz der Ansichten. Sie sichern Regressionsfälle ab.

## 4. Holzverbindungen und Schüttgut (ADR-0007)

| Verbindung | Regel |
|---|---|
| `tenon` | Stärke 1/3 des Holzes, Länge 0,4 × Gegenholz (30–60 mm), Zuschnitt je Zapfenende verlängert, 1 Holznagel (2 ab 200 mm Breite) |
| `half_lap` | Überlappung erlaubt, je Teil halbe Überdeckung, 1 Holznagel |
| `notch` | Überlappung bis 1/3 der Bauteilhöhe, 1 Holzbauschraube |

An deklarierten Verbindungen entfallen automatische Schrauben.

Schüttgut und Flächenmaterial (`kind="bulk"`): Ausfachung, Beton und Dämmung nach m³,
Dachdeckung und Schalung nach m², jeweils mit erlaubtem Stärkenbereich.

## 5. Zeitbudget

Jede Konstruktion muss für den Kunden in fester Zeit fertig sein, gemessen von der Nachricht bis
zum gespeicherten Projekt: **mittel 60 s, schwer 90 s**. `calc_engine/pipeline/budget.py` stuft den
Steckbrief regelbasiert ein (Gebäude, Fachwerk, Carport, Pergola, Zaun oder ein Maß ab 3 m =
schwer, sonst mittel) und hält die Werte. Durchgesetzt wird das in `modules/pipeline/stages.py`:
jede Modellanfrage läuft gegen die Frist (`Deadline`), Reparaturrunden der Module enden, wenn eine
weitere nicht mehr passt, die Doku fällt bei Zeitmangel auf die Standardtexte zurück. Der Chat
rechnet seine eigene Zeit mit (`ChatPlanner`, 6 s Reserve für die Schlussantwort). Verhaltenstest:
`apps/api/tests/bdd/features/zeitbudget.feature`; Mechanik: `tests/test_time_budget.py`; echte
Dauer: `task eval:live` (Fälle `schuhe_flur`, `fachwerk_gartenhaus`). Messung und Grenzen:
[`docs/ai/ZEITBUDGET.md`](../ai/ZEITBUDGET.md).

## 5a. Bausteine

Was die Engine selbst bauen kann, baut sie selbst (`calc_engine/pipeline/blocks`). Ein Modul des
Gerüsts trägt dann `block` statt eines Modell-Aufrufs: `house` (Fundament, vier Wände aus Fachwerk
oder Ständerbau mit Tür und Fenstern, Satteldach oder Flachdach), `carcass` (Regal, Schrank),
`platform` (Podest), `table` (Tisch, Bank, Werkbank), `post_frame` (Carport, Pergola) und `fence`.
Ein Baustein schreibt Bauteile als Ausdrücke über die Parameter; Stückzahlen (Pfosten, geteilte
Hölzer, Plattenraster) legt er für das obere Ende des Reglerbereichs fest, Neigungen sind in Ausdrücken
begrenzt (Satteldach 12–45°, Pultdach 12–30°), und `prepare` begrenzt die Regler auf einen Bereich, der
nachweislich baut (`tests/calc_engine/test_blocks.py` prüft jede Ecke). Passt ein Baustein nicht zu
den Maßen, meldet er auf Deutsch, was zu ändern ist (`BlockError`); die Pipeline gibt das dem Gerüst
zurück. Die Teile gehen durch dieselben Prüfungen wie alles andere (kein Durchdringen, flächiger
Kontakt, Katalogquerschnitte und Handelslängen). `blocks/suggest.py` setzt einen Baustein ein, wenn
das Modell ein einzelnes Modul ohne ihn plant und der Brief das Objekt eindeutig nennt.

## 6. Der Katalog

`apps/api/src/homeworking/calc_engine/data/catalog.json` ist die zentrale Fachquelle für Querschnitte,
Handelslängen, Formate, Preise, Eignung außen und Beschlagtypen. Seine Pflege ist ein
fachlicher Vorgang.
