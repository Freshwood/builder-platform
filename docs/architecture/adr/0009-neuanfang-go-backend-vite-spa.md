# ADR-0009: Neuanfang mit Go-Backend, Vite-SPA und BDD-Szenarien

- Status: nicht umgesetzt (Go-Backend und Vite-SPA am 2026-10-29 entfernt, Python und Next.js bleiben; Ersatz-ADR steht aus)
- Datum: 2026-10-16
- Löst ab: den Technologie-Stack aus ADR-0001 (FastAPI, Python-Pakete, import-linter),
  ADR-0003 (Pydantic AI) und den Next.js-Client. Die fachlichen Entscheidungen aus ADR-0001 bis
  ADR-0008 gelten weiter und sind in [ARCHITEKTUR.md](../ARCHITEKTUR.md) zusammengefasst.

## Kontext

Die Entwicklung war zu langsam:

- `task dev` lief als sequentielle Kette: `pnpm install` → `uv sync` → `docker compose up --wait`
  (Postgres-Healthcheck) → alembic in einem eigenen Python-Prozess → uvicorn mit `--reload`.
- Der API-Start importierte pydantic-ai und das openai-SDK („dauert Sekunden“), baute große
  pydantic-Schemas und wärmte WeasyPrint mit fontconfig auf.
- `next dev` kompilierte jede Route erst beim ersten Aufruf. Dafür gab es ein eigenes
  Aufwärmskript (`warmup.mjs`), das je Route bis zu Minuten wartete.
- Das Frontend nutzte von Next.js nur Routing, Seitentitel, `next/dynamic` und den `/api`-Proxy.
  Es gab keine Route-Handler, keine Server-Actions und kein serverseitiges Datenladen.

## Bewertete Optionen

### Backend

| Option | Bewertung |
|---|---|
| Python behalten, Start optimieren (lazy imports, SQLite in dev, kein Docker) | Kleinster Aufwand, behebt aber nur einen Teil. Importzeit und Laufzeit der Geometrie-Engine bleiben. |
| **Go** | Ein statisches Binary, Start im Millisekundenbereich, schnelle Kompilierung, echte Parallelität für Engine-Builds. Kein Agent-Framework wie Pydantic AI nötig, weil die Tool-Schleife klein ist. Nachteile: Engine, Ausdrucks-Parser, Stream-Protokoll und PDF müssen neu geschrieben werden. |
| Rust | Schnellste Laufzeit, aber deutlich langsamere Kompilierung und höherer Aufwand für das Team. |
| Node/TypeScript | Eine Sprache für alles, aber kein Geschwindigkeitsgewinn gegenüber Python bei der Geometrie und schwächere Typisierung für Decimal-Geld. |

### Frontend

| Option | Bewertung |
|---|---|
| **Vite + React SPA** | Dev-Start in Sekunden, HMR ohne Routen-Kompilierung. Die bestehenden React-Komponenten, `useChat`, TanStack Query und three.js bleiben nutzbar. In Produktion liefert das Go-Binary die statischen Dateien aus. |
| SvelteKit (SPA) | Sehr schnell, aber alle Komponenten müssten neu geschrieben werden, und das AI SDK ist für Svelte schwächer. |
| SolidJS + Vite | Höchste Laufzeitleistung, aber kleineres Ökosystem und ebenfalls ein Neubau. |
| Next.js behalten (Turbopack) | Behebt die Kompilierung pro Route nicht grundsätzlich und bringt Server-Funktionen mit, die nicht gebraucht werden. |

### Funktionale Tests

| Option | Bewertung |
|---|---|
| **Gherkin + playwright-bdd** | Ein Runner für API- und Browser-Szenarien. Deutsche Feature-Dateien. Unabhängig von der Backend-Sprache, daher konnten dieselben Szenarien erst gegen den alten und dann gegen den neuen Stack laufen. |
| godog (Go) + playwright-bdd | Zwei Runner, zwei Sätze Step-Definitionen. |
| pytest-bdd | Fällt mit Python weg. |

## Entscheidung

1. **Backend in Go** (`backend/`). Ein Binary mit `net/http` (ServeMux mit Mustern).
   - Die API ist **contract-first**: `backend/openapi.json` (anfangs aus der Python-API exportiert,
     damit sie unverändert bleibt) ist die Quelle für den TypeScript-Client. Ein Go-Test prüft,
     dass der Router jede Operation des Vertrags bedient. Ein Generator aus Go-Typen (z. B. huma)
     hätte die vielen Union-Typen des Domänenmodells (Commands, Parameterwerte, Formen) nur über
     Schnittstellen im Modellpaket abbilden können und damit dessen Importgrenze verletzt.
   - Die I/O-freien Kernpakete heißen `internal/model` und `internal/engine`.
   - Modulgrenzen werden mit `depguard` geprüft.
2. **Datenbank:** SQLite (`modernc.org/sqlite`, ohne CGO) für Entwicklung, Tests und BDD,
   PostgreSQL (`pgx`) für Produktion und `task test:pg`. Die SQL-Migrationen (je Dialekt) sind
   eingebettet und laufen beim Start; ein eigener kleiner Migrator ersetzt alembic. Für `task dev` ist kein Docker mehr nötig.
3. **LLM:** ein schlanker eigener Client für OpenAI-kompatible Chat-Completions (Streaming,
   Tool-Calls, OpenRouter-Reasoning und Cache-Punkte) und eine eigene, kleine Tool-Schleife. Ein
   SDK hätte die anbieterspezifischen Felder nur über Umwege erlaubt. Der
   Chat-Stream implementiert das AI-SDK-UI-Message-Stream-Protokoll direkt. Das Offline-Modell
   ist eine Portierung des bisherigen und bleibt deterministisch.
4. **PDF** wird in Go erzeugt (`go-pdf/fpdf`, eingebettete Schrift); die Zeichnungen werden direkt
   aus der Zeichnungs-IR als Vektorgrafik gezeichnet. WeasyPrint und seine Systembibliotheken
   entfallen.
5. **Frontend:** Vite + React SPA (`frontend/`) mit React Router. Im Entwicklungsmodus leitet der
   Vite-Proxy `/api` an das Backend weiter (300 s Timeout, SSE ungepuffert). In Produktion bettet
   das Go-Binary die gebaute SPA ein.
6. **Funktionale BDD-Szenarien** unter `tests/` (Gherkin, Deutsch, playwright-bdd). Sie wurden
   zuerst gegen den alten Stack grün gemacht und sind das Abnahmekriterium für den neuen.
7. **`task check`** ruft `task backend:check` und `task frontend:check` auf. Beide schließen die
   BDD-Szenarien ihres Bereichs ein. Das ist das Signal für KI-Agenten, ob alle funktionalen
   Anforderungen erfüllt sind.
8. Die ADRs 0001 bis 0008 liegen unter `adr/archiv/`. Der gültige Stand steht in `ARCHITEKTUR.md`.

## Konsequenzen

- `task dev` startet ohne Installationskette, ohne Docker und ohne Aufwärmen. Ziel: Startseite und
  API antworten nach wenigen Sekunden.
- Engine, Agent und PDF sind Neuimplementierungen. Golden-Dateien der Python-Engine, die
  Regressionsfälle und die BDD-Szenarien sichern die Gleichwertigkeit ab.
- Die Werkzeug-Schemas entstehen jetzt aus Go-Typen. Das ist eine Prompt-Änderung mit neuer
  `PROMPT_VERSION` und Eintrag in `docs/ai/PROMPT_CHANGELOG.md`.
- Python, uv, alembic, import-linter, Next.js und `packages/api-client` entfallen.
- **Bekannte Einschränkung:** Das PDF ist nicht mehr als PDF/UA-1 getaggt (WeasyPrint konnte das,
  keine reine Go-Bibliothek kann es). Inhalt, Kennzeichnung „KI-generiert“ und Hinweise bleiben
  gleich. Getaggte PDFs sind ein offener Punkt der Roadmap, z. B. über einen separaten
  Render-Dienst.
- Bestehende Daten in Postgres werden nicht automatisch übernommen. Vor dem Go-Live betrifft das
  nur Test- und Gastdaten.
