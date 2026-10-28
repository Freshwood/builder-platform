# ADR-0010: Gestufte Entwurfspipeline statt eines großen Aufrufs

- Status: vorgeschlagen
- Datum: 2026-10-28
- Ergänzt: ADR-0006 (Token-Budget), ADR-0008 (Unikate). Stack: Python; Go nur dort, wo es
  nachweislich etwas bringt (siehe Konsequenzen).

## Kontext

Ein Neuentwurf läuft heute als ein `save_design`-Aufruf mit dem vollständigen `AssemblyDesign`
(bis 120 Bauteile) auf dem Designer-Modell. Gemessen (`task bench`, offline, ohne
Reasoning-Tokens):

- Statisches Präfix 7.608 Token je Anfrage (Prompt 2.867, Tools 4.740, davon `save_design` 3.509).
- Einfacher Entwurf: 2 Anfragen, 17K Token. Mit zwei Reparaturrunden: 5 Anfragen, 48K Token.
- Reale Läufe mit Reasoning und Reparaturschleife erreichen 130–150K Token. Der Lauf
  `podest_kinder_modenschau_es_so_art_2` brach bei Anfrage 8 von 12 mit `UsageLimitExceeded` ab.
- Rückfragen sind nicht vorgesehen: Regel 11 des Prompts verlangt Annahmen statt Fragen, das
  Formular wird zu einem Freitext verflacht, den das große Modell neu auswertet.
- `list_materials` ist ein Pflicht-Round-Trip vor jedem Entwurf.

## Entscheidung

Die Stufen 1–5 (Gerüst, Module und Zusammenführen bilden zusammen Schritt 2 und 3 der Anforderung) reichen jeweils ein kleines, geprüftes Dokument weiter
(Verträge in `construction_model/pipeline.py`):

| Stufe | Eingabe → Ausgabe | Modell | Tools |
|---|---|---|---|
| 1 Intake | Beschreibung + Formular → `Spec` + höchstens 3 `Question` | klein | keine |
| 2 Gerüst | `Spec` → `Skeleton` (Parameter, Module mit Ursprung und Hüllmaß) | größer | keine |
| 3 Module | `Skeleton` + ein `ModuleBrief` → `ModuleDesign` (Bauteile in Modul-Koordinaten) | klein | keine |
| 4 Zusammenführen | `Skeleton` + `ModuleDesign`s → `AssemblyDesign` | Engine | – |
| 5 Dokumentation | abgeleitete Engine-Daten → Erklärung, Bauschritte | klein | keine |

Regeln:

1. **Fragen entscheidet die Engine, nicht das Modell.** `calc_engine.pipeline.gaps` liefert die
   offenen Lücken (Maße blockierend, Einsatzort, Montage, Material, Oberfläche, Erfahrung), das
   Intake-Modell füllt die `Spec` aus dem Text und formuliert nur die Fragen. Alle Angaben des
   Formulars und freie „Details" aus den Plattform-Einstellungen landen in derselben `Spec`.
2. **Module sind lokal.** Ein Modul kennt nur seine eigenen Koordinaten (0,0,0). Das Zusammenführen
   verschiebt um den Modulursprung, stellt die Modul-ID den Bauteil-IDs voran und verknüpft die
   Modul-Bedingung (`when`) mit der des Bauteils. Das ist reine Ausdrucks-Umschreibung
   (`calc_engine.pipeline.merge`), kein Modellaufruf.
3. **Die Engine prüft das Ganze wie bisher** (`check_design`). Ein Engine-Fehler, der ein Bauteil
   nennt, wird dem Modul zugeordnet, das es besitzt (`attribute`). Eine Reparaturrunde ruft nur
   dieses Modul erneut auf, mit seinen eigenen Fehlern. Fehler ohne Bauteil gehen an das Gerüst.
4. **Die Dokumentation ist eine eigene Stufe** auf Basis der abgeleiteten Daten. Sie steht nicht
   mehr im Entwurfsaufruf (heute 4–6 Absätze Output-Tokens des teuren Modells).
5. **Kein Modell rechnet.** Wie bisher: Ausdrücke über Parameter, Zahlen kommen aus der Engine.
6. **Je Stufe ein eigener, kurzer Prompt und ein eigenes Schema.** Jede Stufe hat ein Token-Budget
   in `test_token_budget.py`; die Stufen sind unabhängig versioniert (`PROMPT_VERSION`).

Zielwerte (Schätzung, noch nicht gemessen; werden nach der ersten Messung festgeschrieben):
Intake unter 1,5K Token, Gerüst unter 4K, je Modul unter 5K, Neuentwurf eines einfachen Objekts
insgesamt deutlich unter 40K statt 100–150K.

## Nicht Teil dieser Entscheidung

- Modulübergreifende Verbindungen (`joints` zwischen Modulen): zunächst nur lokale Verbindungen,
  übergreifende entstehen über `auto_screws` und die Konstruktionsprüfung.
- Strict-/Structured-Output je Stufe: wird mit der Live-Evaluation festgelegt.

## Konsequenzen

- Der laufende Python-Agent bleibt für Änderungen, Preise, Rückgängig und Fragen bestehen
  (`change_project`, `undo_last_change`); nur der Neuentwurf wird durch die Pipeline ersetzt.
- Die Go-Portierung (ADR-0009) übernimmt die Verträge unverändert, wenn die Engine portiert ist.
  Go lohnt sich dort, wo CPU-lastig gerechnet wird (Geometrie, `derive`, SVG/PDF), nicht für die
  Pipeline-Steuerung, die auf LLM-Latenz wartet.
- Neue Prompts und Tools folgen dem Ablauf in `docs/ai/README.md` (Version, Lock, Snapshot,
  Changelog); jede Stufe bekommt dort einen eigenen Abschnitt.

## Stand der Umsetzung (2026-10-28)

- Umgesetzt: Verträge, Lückenregeln, Zusammenführen, Gerüst-Prüfung (`calc_engine.pipeline`),
  Stufe 1 bis 3 als Endpunkte `POST /api/pipeline/intake`, `/skeleton` und `/modules`
  (`modules/pipeline`, eigene Prompts, Lock und Token-Budget), Fragen-Schritt im Planer.
- Stufe 3: Pro Modul ein Aufruf des kleinen Modells (höchstens 4 gleichzeitig) mit
  Katalog-Kurzliste, Steckbrief, Parametern, eigener Box und den Nachbarboxen. Die Engine
  verschiebt, führt zusammen und prüft; Fehler mit Bauteilnamen gehen nur an das besitzende Modul
  (Bauteil-IDs in Modul-Schreibweise, höchstens zwei Reparaturrunden). Fehler ohne Bauteil beenden
  die Stufe mit 422 (`skeleton`-Schlüssel). Ein Modul, dessen Ausgabe das Schema verletzt, wird
  neu angefragt. Jeder Lauf steht in `agent_runs` (`stage:modules`, Rolle `fast`).
- Stufe 5 und Neuentwurf im Chat: Das Chat-Werkzeug `plan_design(spec, title)` ersetzt
  `save_design` für neue Projekte und für die komplette Neuplanung. Das Chat-Modell füllt nur
  den Steckbrief; `Pipeline.design` führt Gerüst, Module und Dokumentation aus
  (`api/planner.py` speichert jede Stufe in `agent_runs`, mit der Chat-ID). Die Dokumentation
  (`docs.de.md`) liefert die Erklärung („Warum so?“) und die Texte der Bauschritte; die Engine
  ordnet jedem Schritt die Teile seines Moduls zu und prüft ihn. Lehnt sie die Texte ab oder
  fällt das Modell aus, bleiben Modultitel und -rolle als Schritt, die Erklärung bleibt leer: der
  Entwurf hängt nie an der Dokumentation. `save_design` bleibt für strukturelle Umbauten.
- Offen: Reparatur des Gerüsts bei Skeleton-Fehlern, strukturelle Umbauten über die Pipeline (dann
  entfällt `save_design` und mit ihm rund 3,5K Token Präfix je Chat-Anfrage), Routing der
  Neuentwurf-Züge auf das kleine Modell, Live-Evaluation. Der Offline-Chat plant Schränke, Podeste
  und Ähnliches über die Pipeline (Plattenkorpus); Hochbeet und Regal nutzen weiter ihre
  Beispielentwürfe über `save_design`.
- Gemessen (offline, Anfrageseite exakt): Intake 810, Gerüst 1.690, je Modul 3.293 Token je
  Anfrage (Präfix 2.697, für alle Module eines Entwurfs gleich) gegenüber 7.608 Token Präfix des
  bisherigen Entwurfsaufrufs bei jeder seiner 2 bis 8 Anfragen. Ob ein kleines Modell brauchbare
  Module liefert und wie viele Reparaturrunden es braucht, zeigt erst die Live-Evaluation.
