# Homeworking – Architektur (gültiger Stand)

- Stand: 2026-10-29
- Fasst die Entscheidungen [ADR-0001 bis ADR-0008](adr/archiv/) zusammen und ergänzt sie um
  [ADR-0010](adr/0010-gestufte-entwurfspipeline.md) (gestufte Entwurfspipeline).
- Dieses Dokument ist die verbindliche Beschreibung. Die archivierten ADRs erklären nur noch,
  *wie* es dazu kam. Neue Entscheidungen werden als ADR ab 0011 geschrieben und hier eingearbeitet.

> **Stack (2026-10-29):** Python (FastAPI) plus Next.js. Der Go-Neuanfang aus
> [ADR-0009](adr/0009-neuanfang-go-backend-vite-spa.md) wurde nicht umgesetzt und entfernt; ein
> Ersatz-ADR steht aus. Paketkarte und Auffälligkeiten: [STRUKTUR.md](STRUKTUR.md).

Veraltetes aus den alten ADRs ist hier bewusst weggelassen: Construction Packs, Vorlagen,
Vertrauensstufen (`trust`), die Werkzeuge `create_project`, `create_from_template`,
`design_project`/`redesign_project`.

---

## 1. Leitprinzip: Das LLM entwirft, die Engine rechnet

Homeworking macht aus einer Beschreibung eines Heimwerkerprojekts ein berechenbares Bauprojekt.

- Das Sprachmodell **beschreibt** Bauteile in einem parametrischen Entwurf (`AssemblyDesign`).
- Die **deterministische Engine** prüft den Entwurf und leitet alles andere ab: Stückliste,
  Zuschnitt, Kosten, Gewicht, Zeichnungen, Anleitung und 3D-Modell.
- **Das LLM rechnet nie.** Zahlen, die ein Sprachmodell frei erzeugt, sind nicht maßhaltig, nicht
  reproduzierbar und passen nicht zur Stückliste. Neue Kennzahlen gehören in die Engine, der Agent
  gibt sie nur weiter.
- **Jedes Projekt ist ein Unikat** (ADR-0008). Es gibt keine Packs und keine Vorlagen. Die KI
  entwirft jedes Projekt selbst genau nach der Angabe des Kunden. Jeder Entwurf trägt den Hinweis
  „KI-Entwurf“ (Transparenz nach Art. 50 KI-Verordnung).

## 2. Modularer Monolith mit I/O-freiem Kern (ADR-0001)

- **Ein Backend-Prozess:** FastAPI-App `homeworking` (`apps/api`), die API unter `/api`. Der
  Next.js-Client (`apps/web`) leitet `/api` per Proxy dorthin.
- **Fachmodule** unter `apps/api/src/homeworking/modules/*`: `projects`, `conversations`,
  `identity`, `drawings`, `documents`, `compliance`, `agent`, `pipeline`.
- **I/O-freier Kern** als Unterpakete desselben Python-Pakets `homeworking`:
  - `homeworking.construction_model` ist die Domäne (Eingaben, Commands, Diff, `AssemblyDesign`,
    Zeichnungs-IR).
  - `homeworking.calc_engine` ist die Rechen-Engine (Prüfung, Geometrie, Ableitung, Katalog).
  - Beide kennen weder HTTP noch Datenbank noch LLM.
- **Modulgrenzen** prüft `lint-imports` (Teil von `task check`):
  - `construction_model` importiert weder `calc_engine` noch `api`, `modules`, `db`, FastAPI,
    SQLAlchemy oder Pydantic AI.
  - `calc_engine` importiert nichts aus `api`, `modules`, `db`, FastAPI, SQLAlchemy oder Pydantic AI.
  - `modules/agent` und `modules/pipeline` werden nur von der HTTP-Schicht (`api/`) importiert.
  - `modules/pipeline` importiert nicht `modules/agent`; `modules/llm` (Modellfabrik, Metering,
    Provenienz-Lock) kennt weder Agent noch Pipeline.
  - `modules/*` importieren weder `api`, `bootstrap` noch `main`; die Laufzeit importiert nicht
    `homeworking_dev` (Werkzeuge: Benchmark, Live-Auswertung, Fall-Erfassung in
    `apps/api/devtools`).
- **Ports** (`modules/projects/ports.py`) werden im Composition Root (`bootstrap.py`) verdrahtet.
- Keine Microservices und kein Kubernetes in Phase I.

## 3. Projektmodell: Eingaben plus Command-Log (ADR-0002, ADR-0008)

1. **Eingabe und Ableitung sind getrennt.**
   - Gespeichert werden nur die *Eingaben* (`ProjectInputs`): der Entwurf (`design`, Pflicht),
     Parameterwerte, die gewählte Variante, Name, Region, eigene Preise und Notizen.
   - Das *Ergebnis* (`ConstructionResult`: Bauteile, Stückliste, Zuschnitt, Kosten, Zeichnungen,
     Anleitung, 3D-Daten) erzeugt die Engine bei jeder Änderung neu, mit Versionsangaben
     (`Provenance.engine_version`, `design_version`).
2. **Speicherung:** `projects.model` als JSON (Postgres: JSONB) mit `schema_version` (aktuell 2).
   Ältere Schemata werden beim Lesen per Upcaster angehoben. Nutzer und Projekte liegen in
   normalisierten Tabellen.
3. **Änderungen nur über typisierte Commands** (diskriminierte Union über `type`):
   `create_project`, `set_parameters`, `change_parameter_by`, `select_variant`, `rename`,
   `set_region`, `add_note`, `replace_design`, `set_price`, `replace_inputs`, `undo`.
   - Jede Ausführung schreibt einen append-only Eintrag in `project_commands`: `seq`, `command`,
     `actor` (user/agent), `llm_trace_id`, `engine_version`, `design_version` und `diff`.
   - Das LLM kann das Modell nie direkt beschreiben, es schlägt nur Commands über Werkzeuge vor.
4. **Undo** ist selbst ein Command (Stapel-Semantik in `effective_commands`). Der Zustand entsteht
   per Replay, was nur geht, weil die Engine deterministisch ist.
5. **Bauteile** tragen eine stabile ID und einen IFC-nahen Typ (`IfcMember`, `IfcPlate`,
   `IfcCovering`, `IfcMechanicalFastener` …). Ein späterer IFC-Export ist damit nur ein Adapter.
6. Integritätsregeln liegen in der Validierung und in den Tests, nicht in DB-Constraints.

## 4. Versionen und gespeicherte KI-Läufe (ADR-0005)

1. **Jeder Log-Eintrag ist eine Version.** `GET /api/projects/{id}/versions` liefert Bezeichnung,
   Akteur, Zeitpunkt und Materialkosten. `GET /api/projects/{id}/versions/{seq}` rekonstruiert
   den Stand per Replay. Zeichnungen und PDF akzeptieren `?seq=`.
2. **Wiederherstellen hängt an, statt zu löschen.** `replace_inputs` trägt die vollständigen
   Eingaben und optional `restored_seq`. Ein Wiederherstellen lässt sich selbst rückgängig machen.
3. **Neu planen bleibt im Projekt.** Ist ein Projekt aktiv, wird ein neuer Entwurf zur nächsten
   Version desselben Projekts. Region, eigene Preise und Nutzernotizen bleiben erhalten. Ein
   separates Projekt entsteht nur mit `new_project=true`.
4. **Jeder KI-Lauf wird gespeichert** (`agent_runs`), auch fehlgeschlagene und abgebrochene:
   - Nutzernachricht und Antwort im UI-Format sowie die vollständigen Modellnachrichten,
   - alle Entwurfsversuche einschließlich abgelehnter,
   - Tokenverbrauch, Modell, Prompt-Version und Fingerprint, Routing-Rolle und -Grund, Dauer,
   - Status (`completed`/`failed`/`cancelled`) und Fehler.
5. **Der Chat gehört zum Projekt.** `GET /api/projects/{id}/chat` baut den Verlauf aus den Läufen
   auf. Fragen vor dem ersten Projekt desselben Chats werden beim Anlegen dem Projekt zugeordnet.

Konsequenzen:
- Alte Versionen werden mit der aktuellen Engine neu berechnet. Ihre Zahlen können leicht
  abweichen, die Eingaben bleiben exakt.
- `agent_runs` enthält personenbezogene Inhalte (redigiert) und wird mit Projekt bzw. Nutzerkonto
  gelöscht (Kaskade).

## 5. LLM-Zugang (ADR-0003, ADR-0006)

- **Provider-agnostisch** über eine OpenAI-kompatible Chat-Completions-API (Pydantic AI mit
  Streaming und Tool-Calls, frei konfigurierbare Base-URL). Mögliche Anbieter: OpenRouter, Mistral, Azure OpenAI EU, STACKIT, Scaleway, Ollama, vLLM.
- **Konfiguration nur über Umgebungsvariablen:** `LLM_MODE` (`test` | `openai`), `LLM_BASE_URL`,
  `LLM_API_KEY`, `LLM_MODEL`, optional `LLM_MODEL_FAST`, `LLM_REASONING`.
- **LiteLLM** wird nie als Bibliothek eingebunden (Supply-Chain-Vorfall März 2026). Wenn
  überhaupt, läuft es als separater Proxy-Container mit gepinntem Image-Digest.
- **`LLM_MODE=test`** nutzt ein deterministisches Offline-Modell. Es ruft `save_design` mit
  eigenen Entwürfen auf (Hochbeet, Regal) und verhält sich sonst wie ein echtes Modell.
  Alle Tests, die BDD-Szenarien, CI und lokale Entwicklung laufen ohne API-Key.
- Für die Produktion: EU-gehosteter Anbieter mit AV-Vertrag und Zero Data Retention. Das ist reine
  Konfiguration.

### Werkzeuge des Agenten

`list_materials`, `save_design`, `get_current_design`, `change_project`, `undo_last_change`,
`get_project`, `add_explanation`.

- Werkzeugergebnisse sind kompakter Text oder JSON. Große Daten (komplette Stückliste, Entwurf,
  Katalog) werden nur auf Anfrage geholt.
- Schreibende Werkzeuge laufen innerhalb eines Agent-Laufs nacheinander, damit parallele
  Tool-Aufrufe nicht um dieselbe Sequenznummer konkurrieren.
- Kaputte Tool-Argumente (unquotierte Formeln, überzählige Klammern) werden an genau einer Stelle
  repariert (`modules/agent/args`). Jeder fehlerhafte Aufruf aus einem Fehlerbericht wird dort als
  Testfall abgelegt.
- Modellausgaben und Tool-Argumente sind unvertrauenswürdige Eingaben: strikt validieren, die
  Engine ablehnen lassen, nie `eval`. Ausdrücke laufen nur durch den Ausdrucks-Parser der Engine.

## 6. Freie Entwürfe: `AssemblyDesign` (ADR-0004, ADR-0007)

Das LLM beschreibt Parameter, Bauteile (Quader oder Stab, Maße als Ausdrücke in mm), Formen,
Ausschnitte, Wiederholungen, Bedingungen, Varianten, Beschläge, Holzverbindungen und Bauschritte.
Die Engine prüft jeden Entwurf und lehnt ihn mit einer konkreten Meldung ab (`DesignRejectedError`),
sonst leitet sie Stückliste, Zuschnitt, Schrauben, Kosten (Decimal), Gewicht, Zeichnungen
(Zeichnungs-IR → SVG/PDF), 3D-Daten, Anleitung und Intent-Checks ab. Katalog:
`apps/api/src/homeworking/calc_engine/data/catalog.json`.

Alle Regeln im Einzelnen: [ENGINE.md](ENGINE.md).


## 7. Token-Budget, Routing und Prompt-Provenienz (ADR-0006, ADR-0008)

1. **Token-Budget als Test.** Ein Offline-Benchmark (`task bench`) spielt fünf feste Szenarien
   durch die echten Werkzeuge und die Engine und misst jeden Request. Ein Test setzt Obergrenzen.
   Eine Grenze wird nur mit Begründung im Changelog angehoben und enger gezogen, wenn Requests
   kleiner werden.
2. **Kleiner, stabiler Präfix.** Ein Design-Werkzeug (`save_design`), die Ausdrucks-Syntax steht
   einmal im Schema, der System-Prompt ist eine kompakte Datei (`prompts/system.de.md`). Der Präfix
   ist byte-stabil (Test), damit Prompt-Caching greift. Für OpenRouter werden explizite
   Cache-Punkte gesetzt.
3. **Kompakte Historie.** Frühere Entwurfsargumente, Katalogabfragen und Reasoning werden durch
   Stubs ersetzt. Im laufenden Turn bleibt nur der letzte Entwurf vollständig. Jeder Entwurf bleibt
   in `agent_runs` vollständig erhalten.
4. **Serverseitige Historie.** Der Browser sendet nur die neue Nachricht. Die Historie kommt aus
   `agent_runs`, damit der Client keine Tool-Ergebnisse einschleusen kann.
5. **Modell-Routing pro Turn,** deterministisch und ohne zusätzlichen LLM-Call (`ROUTING_VERSION` 2):
   - neue Projekte, Entwürfe und strukturelle Änderungen gehen an `LLM_MODEL` (Designer);
   - Parameter-, Preis- und Variantenänderungen, Undo und Fragen in einem offenen Projekt gehen an
     `LLM_MODEL_FAST`, falls gesetzt, mit Rückfall auf den Designer bei Provider-Fehlern;
   - im Zweifel der Designer.
6. **Prompt-Provenienz.** Ein Fingerprint über Instructions, alle Werkzeugdefinitionen und die
   Routing-Version wird mit jedem Lauf gespeichert. `prompt.lock`, ein Snapshot-Test und
   `docs/ai/PROMPT_CHANGELOG.md` erzwingen für jede Prompt-Änderung eine neue `PROMPT_VERSION` und
   einen Changelog-Eintrag.

## 8. Sicherheit und Grenzen (ADR-0004 §7, ADR-0007)

| Bereich | Regel |
|---|---|
| Möbel und Kleinbauten | max. 4 m Kantenlänge, 2,5 m Höhe, 400 Bauteile |
| Gebäude (`category="building"`) | max. 25 × 25 m Grundfläche, 15 m Höhe, 1500 Bauteile; nur Beton unter Geländeniveau (Fundamente); Warnhinweis `BUILDING` (`FD-BUILD`): Statik vom Tragwerksplaner, meist Baugenehmigung; keine Prüfung von Standsicherheit, Wärme-, Feuchte-, Brand- oder Schallschutz |
| Ausgeschlossen | Balkone, Treppen, Absturzsicherungen, Spielgeräte mit Absturzhöhe, feste Elektroinstallation, Gas |
| An Fachleute verwiesen | Eingriffe in *bestehende* tragende Bauteile (Wanddurchbruch, Dachstuhl ändern, Sparren kürzen) |

- Das Sicherheits-Gate (`modules/compliance/safety`) prüft jede Nutzernachricht vor dem Modell.
  Ändern sich die Regeln, steigt `SAFETY_RULES_VERSION`.
- Alle Ergebnisse sind Planungshilfen ohne Standsicherheitsnachweis.
- Geheimnisse (`.env`) werden nie gelesen, ausgegeben oder eingecheckt; nur `.env.example` ist versioniert.

## 9. Technologie-Stack

| Schicht | Technik |
|---|---|
| Backend | Python 3.13, FastAPI, Uvicorn |
| API-Vertrag | aus FastAPI exportiert (`task openapi`) nach `apps/web/openapi.json`; die CI prüft Drift |
| Datenbank | PostgreSQL (Produktion, JSONB), SQLite (Tests); SQLAlchemy async, Alembic |
| LLM | Pydantic AI mit OpenAI-kompatibler API (OpenRouter-Reasoning, Cache-Punkte); Offline-Modell |
| Chat-Stream | AI-SDK-UI-Message-Stream (SSE) |
| PDF | WeasyPrint aus HTML-Vorlage, Zeichnungen aus der Zeichnungs-IR als SVG |
| Frontend | `apps/web`: Next.js 16, React 19, TanStack Query, Vercel AI SDK `useChat`, three.js, Tailwind 4 |
| API-Client | `apps/web/src/api`, generiert mit `@hey-api/openapi-ts` |
| Funktionale Tests | Gherkin (Deutsch): pytest-bdd (`apps/api/tests/bdd`), playwright-bdd (`apps/web/tests/bdd`) |
| Build und Aufgaben | Task (`Taskfile.yml`), uv, pnpm |

## 10. Teststrategie

- **`task check`** prüft Lint, Typen und Importgrenzen (ruff, mypy strict, import-linter, eslint,
  tsc) und lässt die Vitest-Unit-Tests der reinen Frontend-Logik (`apps/web/src/lib`) laufen;
  **`task test`** führt pytest aus (Engine, API, Agent, SVG-Goldens, PDF).
- **Funktionale BDD-Szenarien** (`task bdd`): Backend-Szenarien (`apps/api/tests/bdd`, pytest-bdd)
  sprechen die API im selben Prozess an und laufen in `task test` mit. Frontend-Szenarien
  (`apps/web/tests/bdd`, playwright-bdd) bedienen den Browser. Beide nutzen das Offline-Modell.
  `task e2e` führt im Frontend-Paket alle Browser-Tests aus (Playwright mit axe-Prüfung:
  `apps/web/tests/e2e` für Abläufe ohne Gegenstück in den Szenarien, dazu die BDD-Szenarien).
- **Engine-Tests:** Golden-Dateien, Korpus-Invarianten über alle Testentwürfe, Intent-Checks,
  Hypothesis-Tests für den Ausdrucks-Parser.
- **Regressionsfälle:** Jeder gemeldete fehlerhafte Entwurf oder Agent-Lauf wird ein Fall unter
  `apps/api/tests/regressions/` (`task regress:capture`). Ein Bugfix ist ohne Fall nicht fertig.
- **Agent-Tests:** Tool-Argument-Reparatur, Routing, Prompt-Lock, Token-Budget, Stream-Format.
- **Live-Evaluation** (`task eval:live`) kostet Geld, braucht einen Schlüssel und läuft nicht in CI.
- Kein Test braucht einen API-Key oder Netzwerkzugriff.
