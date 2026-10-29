# Zeitbudget der Konstruktion: Stand und Lösung

- Stand: 2026-10-29, gemessen mit dem echten Modell (`task eval:live`, `task pipeline:live`)
- Vorgabe: Jede Konstruktion ist für den Kunden fertig, gemessen von der Nachricht bis zum
  gespeicherten Projekt, in **60 s (mittel)** bzw. **90 s (schwer: Fachwerkhaus, Gartenhaus, Carport, …)**.

## Kurzfassung

Die Zeit hing am Modell, weil das Modell Hunderte Bauteile mit Koordinaten schreiben sollte. Das ist
jetzt Sache der Engine: **parametrische Bausteine** (`calc_engine/pipeline/blocks`) bauen Haus,
Regal/Schrank, Podest, Tisch/Bank, Carport/Pergola und Zaun selbst. Das Modell wählt im Gerüst nur
noch Baustein und Optionen (ein Aufruf mit 600–900 Ausgabetokens), die Engine erzeugt die Teile in
Millisekunden und prüft sie wie alles andere.

| | vorher | mit Bausteinen |
|---|---|---|
| Pipeline `task pipeline:live`, schwer (Fachwerkhaus) | Abbruch nach 80–92 s (0 von 6) | **9–25 s** |
| Pipeline, leicht (Wandregal) und mittel (Schuhregal, Podest) | 46 s und mehr, Abbruch bei 54 s | **7–8 s** |
| Eingabetokens je Entwurf | 27k–91k | 4–5k |
| Chat bis Projekt (`task eval:live`, 6 Briefe) | 4 von 12 Läufen, Mittel 90,7 s | **21 von 24 Läufen, Mittel 29 s** |

## Was verankert ist

| Was | Wo |
|---|---|
| Feste Werte (`TIME_BUDGET_S = {"medium": 60, "heavy": 90}`) und regelbasierte Einstufung | `calc_engine/pipeline/budget.py` |
| Durchsetzung: jede Modellanfrage läuft gegen die Frist, Reparaturrunden enden, wenn keine mehr passt, die Doku fällt auf Standardtexte zurück | `modules/pipeline/stages.py` (`Deadline`) |
| Der Chat rechnet seine eigene Zeit mit (6 s Reserve für die Schlussantwort) | `modules/agent/planner.py` |
| Bausteine und ihre Regeln | `calc_engine/pipeline/blocks/` (`house`, `furniture`, `frame`, `roof`, `wall`, `floor`) |
| Baustein einsetzen, wenn das Modell ihn vergisst | `blocks/suggest.py`, Einstellung `ENGINE_BLOCKS=auto|model` |
| Verhaltenstests | `tests/bdd/features/zeitbudget.feature`, `tests/test_block_pipeline.py` |
| Jeder Baustein an jeder Ecke seiner Reglerbereiche | `tests/calc_engine/test_blocks.py` |
| Mechanik mit absichtlich langsamen Modellen | `tests/test_time_budget.py` |
| Live-Prüfung: ein Lauf über dem Budget gilt als Misserfolg | `devtools/homeworking_dev/live_eval.py`, Fälle in `tests/regressions` (`schuhe_flur`, `wandregal_gewuerze`, `gartentisch_sechs`, `fachwerk_gartenhaus`, `carport_zwei_autos`, `zaun_garten`) |

Einstufung: Gebäude und große Holzbauten (Fachwerk, Haus, Gartenhaus, Hütte, Carport, Garage,
Schuppen, Pergola, Wintergarten, Zaun …) oder ein Maß ab 3 m sind **schwer**, alles andere **mittel**.

## Wie die Bausteine arbeiten

- **Ausdrücke statt Zahlen.** Ein Baustein rechnet Anzahl und Lage der Teile einmal bei den
  Standardwerten aus, schreibt aber jedes Maß als Ausdruck über die Parameter (`blocks/sym.py`).
  Regler und Varianten funktionieren wie bei einem Modul, das das Modell geschrieben hat. Die
  Dachneigung ist ein Ausdruck aus Höhe und Spannweite, begrenzt auf 12–45° (Pultdach 12–30°).
- **Stückzahlen für den Reglerbereich.** Geteilte Hölzer, Plattenraster und Spannweiten sind für das
  obere Ende des Bereichs (+25 %) ausgelegt; `prepare` begrenzt die Regler auf ±25 % um den Standard.
  Lange Sparren, Pfetten und Dachbalken werden KVH (Handelslängen bis 13 m).
- **Flächiger Kontakt statt Überschneidung.** Sparren stehen mit Waagschnitt auf dem Dachbalken und
  stoßen mit Lotschnitt an die Firstbohle, Streben haben Lotschnitte an beiden Enden, Türen und
  Fenster haben genau die Katalogmaße der Öffnung mit Pfosten, Sturz und Brüstungsriegel.
- **Fehler sagen, was zu ändern ist.** Passt ein Baustein nicht, meldet er auf Deutsch das Mindest-
  oder Höchstmaß; das Gerüst wird einmal überarbeitet (vorhandene Revisionsrunde).
- **Die Engine korrigiert, was sie darf.** Maße, die der Kunde nicht genannt hat, rückt sie in den
  baubaren Bereich (zu niedrige Höhe, zu kleine Fläche); eine genannte Höhe, unter der kein
  Satteldach passt, ergibt ein Flachdach. Erfundene Oberflächenmittel und ein zusätzliches
  Fundament- oder Wandmodul neben dem Haus verwirft sie.

## Messungen mit dem echten Modell

Alle Läufe: deepseek-v4-flash über OpenRouter (Sortierung nach Durchsatz), Chat bis fertiges Projekt,
Berichte in `docs/ai/evals/2026-10-29-bausteine-*.md`.

Endstand (`2026-10-29-bausteine-final`, 4 Läufe je Brief, Chat bis Projekt, Dauer in s):

| Brief | Kategorie | Budget | Erfolg | typische Dauer |
|---|---|---|---|---|
| Wandregal für Gewürze (leicht) | mittel | 60 | 4 von 4 | 16–45 |
| Schuhregal im Flur | mittel | 60 | 4 von 4 | 8–21 |
| Gartentisch für sechs | mittel | 60 | 3 von 4 | 12–26 |
| Fachwerk-Gartenhaus | schwer | 90 | 3 von 4 | 17–70 |
| Carport für zwei Autos | schwer | 90 | 4 von 4 | 8–29 |
| Holzzaun 8 m | schwer | 90 | 3 von 4 | 8–33 (ein Ausreißer 155 s) |

Verlauf: 4 von 12 erfolgreich (Mittel 91 s) vor den Bausteinen, 10 von 12 (42 s) mit den ersten
Bausteinen, 17 von 18 (18 s) mit Möbel-, Haus- und Pfostenbau-Korrekturen, danach noch die Route
`new_project` ohne Denken und das Verwerfen scheiternder Zusatzmodule. Die drei Fehlläufe des
Endstands: ein Haus mit vom Kunden genannter Höhe 2,5 m (zu niedrig, Fehlermeldung korrekt), ein
Tisch, den der Chat-Agent ausdrücklich als „indoor“ ins Steckbrief schrieb, und ein Zaun, den das
Modell von Hand plante, bis das Chat-Modell sein Token-Limit sprengte. Ältere Fälle mit Sonderform
(`tonie_cloud_shelf`, `window_shutter_reported`) laufen weiter über Modell-Module und verfehlen
das Budget wie vorher; die Podest-Fälle bestehen mit der Oberflächenwahl Platte/Bretter.

## Grenzen

- Die Zeit eines Laufs besteht jetzt zum großen Teil aus den Chat-Runden des Agenten (jede 8–15 s mit
  deepseek). Läuft eine Runde aus dem Ruder (Modell erzeugt 8000+ Tokens; einmal überschritt der
  Agent sein eigenes Limit von 12000), hilft kein Baustein. Das Gerüst ist auf 3500 Ausgabetokens
  begrenzt, der zweite Versuch läuft dann meist durch.
- Ein Baustein deckt nur die Standardbauweise ab (Rechteckhaus mit Sattel- oder Flachdach, Möbel
  mit Platten, Pfostenbau, Zaun). Wer etwas anderes will (Erker, Walmdach, geschwungene Formen),
  bekommt wie bisher Module vom Modell, mit den bekannten Grenzen.
- Der Baustein `platform` bietet keine Auswahl „Bretter oder Platte“; der ältere Fall
  `podium_kids_catwalk` erwartet sie (`choice_param:surface`).
- Statik wird nicht berechnet; die Querschnitte sind Erfahrungswerte für kleine Bauten.
- Der Katalog kennt keine Dachziegel außer Lehm und keine Bleche; `cover` hat nur `boards`
  (Lärchenschalung) und `tiles`.

## Empfohlene Einstellung

Unverändert: `LLM_STAGE_REASONING=off`, `LLM_MODULE_REASONING=minimal`, `LLM_PROVIDER_SORT=throughput`.
Mit Bausteinen ist die Wahl des Modells für die Zeit nachrangig; `.env` habe ich nicht angefasst.
