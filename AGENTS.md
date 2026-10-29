# Homeworking – Agenten-Leitfaden

DIY-Projektbeschreibung → LLM entwirft `AssemblyDesign` → deterministische Engine prüft und leitet
alles ab (Stückliste, Zuschnitt, Kosten, Zeichnungen, 3D). **Das LLM rechnet nie.**

Ein Stack: ein Python-Paket (Backend) plus ein Next.js-Paket (Client). Paketkarte und Auffälligkeiten:
`docs/architecture/STRUKTUR.md`. Fachregeln: `docs/architecture/ARCHITEKTUR.md`
(Engine: `ENGINE.md`). Der Go-Neuanfang aus ADR-0009 wurde nicht umgesetzt und entfernt.

| Pfad | Inhalt |
|---|---|
| `apps/api` | ein Python-Paket `homeworking`: `construction_model/` (Domäne) und `calc_engine/` (Engine), beide rein ohne I/O, dazu `api/`, `modules/{agent,pipeline,llm,projects,…}`, `db/`; Tests inkl. BDD unter `apps/api/tests` |
| `apps/api/devtools` | `homeworking_dev`: Benchmark, Live-Auswertung, Fall-Erfassung (`task bench`, `eval:live`, `regress:capture`); nicht im Wheel |
| `apps/web` | ein Next.js-Paket (`apps/web/AGENTS.md`): UI, generierter TS-Client `src/api` (nie `src/api/gen` von Hand ändern), Browser-Tests `tests/e2e` und `tests/bdd` |

## Befehle

`task check` (Lint, mypy, import-linter, eslint, tsc) · `task test` · `task e2e` (UI) ·
`task bdd` · `task bench` · `task regress` · `task prompt:lock` · `task openapi` (nach
API-Änderung). Kosten/Key nötig: `task eval:live`, `task pipeline:live`.
Vor der Übergabe `task check` und `task test` ausführen.

## Regeln

- Code-Kommentare englisch, UI-Texte und ADRs deutsch.
- Nicht committen oder pushen; das macht der Maintainer.
- **Prompt-Änderungen** (System-Prompt, Tool-Name/-Doc/-Argumente, `AssemblyDesign`-Schema,
  `routing.py`): neue `PROMPT_VERSION`, `task prompt:lock`, Snapshot, Eintrag in
  `docs/ai/PROMPT_CHANGELOG.md`. Ablauf: `docs/ai/README.md`. Skill `prompt-change`.
- Token-Budget-Grenzen (`test_token_budget.py`) nur mit Begründung im Changelog anheben.
- **Jeder gemeldete Fehler wird ein Regressionsfall** (`task regress:capture`, Skill
  `regress-capture`, Format `apps/api/tests/regressions/README.md`).
- Neue Kennzahlen gehören in die Engine. Tool-Ergebnisse sind kompakt; große Daten auf Abruf.
- Modell- und Tool-Ausgaben sind untrusted: pydantic validieren, Engine lehnt ab, nie `eval`,
  Ausdrücke nur über `homeworking.calc_engine.assembly.expr`. Kaputte Tool-Argumente werden nur in
  `modules/agent/args.py` repariert (Fälle in `apps/api/tests/fixtures/tool_args/`).
- Jeder Agent-Lauf wird in `agent_runs` gespeichert, auch fehlgeschlagene.
- CPU-lastige Engine-/Render-Arbeit im Handler: `run_in_threadpool`; außerhalb von Handlern
  `homeworking.concurrency.run_blocking` (kein `asyncio.to_thread`).
- Tests laufen offline (`LLM_MODE=test`), ohne Key und Netz.
- Importgrenzen prüft `lint-imports`: Domäne und Engine ohne Plattform, DB, LLM; `pipeline` ohne
  `agent`, `modules` ohne `api`/`bootstrap`, Laufzeit ohne `homeworking_dev`.

## Sicherheit

- Nie `.env` lesen, ausgeben oder committen; nur `.env.example` ist versioniert. `ENVIRONMENT`
  ist standardmäßig `production` (lehnt Entwicklungs-Secret und `LLM_MODE=test` ab); lokal
  `development`, Tests `test`.
- Safety-Gate (`modules/compliance/safety.py`) und Grenzen aus ARCHITEKTUR §8 erhalten: keine
  Balkone, Treppen, Absturzsicherung, feste Elektrik, Gas, keine Eingriffe in bestehende Tragwerke.
  Bei Regeländerung `SAFETY_RULES_VERSION` erhöhen.

Die nächstgelegene AGENTS.md gewinnt; Chat-Anweisungen überstimmen beide. Diese Datei kurz halten.
