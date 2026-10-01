# Sicherheitsleitplanken des Agenten und Haftungsgrundsätze

## Grundsatz

**Das LLM rechnet nicht.** Alle Maße, Mengen, Zuschnitte, Kosten und Zeichnungen kommen aus der
deterministischen Engine (`packages/calc-engine`). Das LLM versteht Anforderungen, stellt Rückfragen,
schlägt Commands vor und erklärt die Ergebnisse der Engine.

## Themen, die blockiert und an Fachleute verwiesen werden

Umgesetzt in `homeworking.modules.compliance.safety`. Der Klassifikator läuft regelbasiert vor jedem
Agent-Lauf, mit fester Antwortvorlage.

| Thema | Grund | Verweis |
|---|---|---|
| Arbeiten an der festen Elektroinstallation | DIN VDE 0100, § 13 NAV | Elektrofachbetrieb (Installateurverzeichnis) |
| Gas, Feuerstätten, Kamine, Abgasanlagen | § 13 NDAV, TRGI, Abnahme durch Schornsteinfeger | Fachbetrieb, Bezirksschornsteinfeger |
| Tragende Wände, Dachstühle, Decken, Durchbrüche | Standsicherheit (§ 12 MBO) | Tragwerksplaner |
| Asbest, alte Holzschutzmittel (PCP, Lindan), Abbruch von Gebäuden vor 1993 | GefStoffV, TRGS 519 | Fachbetrieb mit Sachkunde |

## Pflicht-Hinweise in jedem Ergebnis und PDF

1. „Planungshilfe – kein Standsicherheitsnachweis und keine geprüfte Statik.“
2. „Ob dein Vorhaben genehmigungs- oder anzeigepflichtig ist, regelt die Landesbauordnung deines
   Bundeslandes und ggf. ein Bebauungsplan. Kläre dies im Zweifel mit dem örtlichen Bauamt.“
   Es gibt keine verbindliche Einzelfallaussage (RDG, BGH I ZR 113/20).
3. „Texte mit dem Kennzeichen ‚KI‘ wurden durch ein KI-System erstellt“ (AI Act Art. 50).
4. Arbeitsschutz: Schutzbrille, Gehörschutz und Handschuhe bei Maschinenarbeit. Die Hinweise der
   Werkzeughersteller beachten.

## Fachspezifische Regeln: Hochbeet (Pack `raised_bed`)

- Bei Nutzpflanzen kein kesseldruckimprägniertes oder chemisch behandeltes Holz. Empfohlen: Lärche,
  Douglasie, ggf. thermisch modifiziertes Holz.
- Innenauskleidung mit HDPE-Noppenbahn, nicht mit PVC-Folie.
- Ab etwa 1,5 m Innenlänge Querstreben oder Zuganker gegen Ausbauchen durch Erddruck.
- Ab einer Höhe von etwa 80 cm Kippsicherheit und Spreizdruck beachten. Bei Hanglage keine Montage
  ohne ebenen Untergrund.
- Konstruktiver Holzschutz (in Anlehnung an DIN 68800-2): kein direkter Erdkontakt der Bretter,
  Abstand bzw. Kies oder Rasengitter als Unterlage.

## Normen

Normtexte (Eurocodes, DIN) sind urheberrechtlich geschützt und **nicht** Teil des Repos, der Prompts
oder der PDFs. Regeln in der Engine sind eigene Faustregeln mit Normverweis. Jede Regel hat eine ID
und eine Version (`RuleRef`) und gehört vor dem Go-Live in die fachliche Validierung.

## Haftung (BGB, ProdHaftG-neu)

- AGB dürfen die Haftung für Leben, Körper und Gesundheit sowie für grobe Fahrlässigkeit nicht
  ausschließen (§ 309 Nr. 7 BGB). Stattdessen sollen die Leistungsbeschreibung und die Hinweise klar
  sein.
- Ab 09.12.2026 gilt Software als Produkt [?: Stand der deutschen Umsetzung]. Daraus folgen:
  versionierte Regeln, Replay-Fähigkeit, Prozess für Sicherheitsupdates und eine Versicherung.
