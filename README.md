# Homeworking – Builder Platform

> Aus einer natürlichen Beschreibung entsteht ein veränderbares, berechenbares und ausführbares
> Bauprojekt.

Vision und Schritte stehen in der [ROADMAP](ROADMAP.md). Dieses Repository enthält **Phase I**:
die private DIY-Agent-Plattform mit Projektmodell, deterministischer Engine und dem ersten
Construction Pack **Hochbeet**.

## Architektur in einem Bild

```text
Browser (Next.js 16)
  │  Chat (AI SDK UI-Protokoll)    REST (generierter Client)
  ▼                                  ▼
FastAPI-Monolith ─────────────────────────────────────────────
  agent/       Pydantic AI; Tools = typisierte Commands (das LLM rechnet nicht)
  compliance/  Sicherheits-Gate, PII-Redaction, Hinweise (AI Act Art. 50)
  projects/    Command-Log (append-only) → Undo/Replay → Provenance
  drawings/    Drawing-IR → SVG      documents/  HTML → PDF/UA-1
  │
  ├─ packages/construction-model   reine Domäne: Inputs, Result, Commands, Diff
  └─ packages/calc-engine          deterministische Engine + Packs (raised_bed)
PostgreSQL (JSONB-Dokument + Command-Log)
```

Entscheidungen: [ADR-0001](docs/architecture/adr/0001-modularer-monolith.md) ·
[ADR-0002](docs/architecture/adr/0002-projektmodell-und-command-log.md) ·
[ADR-0003](docs/architecture/adr/0003-llm-gateway.md) · Compliance: [docs/compliance](docs/compliance/README.md)

## Schnellstart

Voraussetzungen: Docker, [uv](https://docs.astral.sh/uv/), Node 24 mit Corepack,
[just](https://just.systems) (optional) sowie Pango für WeasyPrint (`apt install libpango-1.0-0`).

```bash
cp .env.example .env          # LLM_MODE=test läuft ohne API-Key
just install                  # uv sync + pnpm install
just dev                      # Postgres, Migrationen, API :8000, Web :3000
```

Ohne `just`: `uv sync && corepack pnpm install`, `docker compose up -d postgres`,
`uv run --package homeworking-api alembic -c apps/api/alembic.ini upgrade head`,
`uv run uvicorn homeworking.main:app --reload` und `corepack pnpm --filter web dev`.

### Echtes LLM anbinden

Jeder OpenAI-kompatible Endpunkt funktioniert, gesteuert nur über `.env`:

```bash
LLM_MODE=openai
LLM_BASE_URL=https://api.mistral.ai/v1      # oder OpenRouter, Azure, LiteLLM-Proxy, Ollama …
LLM_MODEL=mistral-medium-latest
LLM_API_KEY=…
```

Für die Produktion gilt: EU-Anbieter mit AV-Vertrag und Zero Data Retention, siehe
[DSGVO-Notizen](docs/compliance/dsgvo-dpia-template.md).

## Qualität

| Befehl | Inhalt |
|---|---|
| `just check` | ruff, mypy (strict), import-linter (Modulgrenzen), eslint, tsc |
| `just test` | pytest: Engine-Invarianten (hypothesis), SVG-Golden-Files, API, Agent, PDF |
| `just test-pg` | wie `test`, zusätzlich Integrationstest gegen PostgreSQL |
| `just e2e` | Playwright: Hochbeet planen → „50 cm breiter“ → Undo → Variante → PDF, mit axe-Prüfung (WCAG 2.2 AA) |
| `just openapi` | OpenAPI exportieren und TypeScript-Client neu generieren |

Hinweis für WSL: Liegt das Repo unter `/mnt/c`, sind Python-Imports sehr langsam
(der erste Import von WeasyPrint dauert etwa 20 s). Abhilfe: das Repo ins Linux-Dateisystem
legen oder `UV_PROJECT_ENVIRONMENT` auf einen Pfad unter `~` setzen.

## Ein neues Construction Pack hinzufügen

1. `packages/calc-engine/src/calc_engine/packs/<pack>/` anlegen mit Parametern (Pydantic),
   Geometrie, `build()` (BOM, Zuschnitt, Zeichnungs-IR, Anleitung, Hinweise, `RuleRef`s) und
   `variants()`.
2. Das Pack in `calc_engine.engine.default_engine()` registrieren.
3. Tests schreiben: Referenzfälle, Invarianten mit hypothesis, SVG-Golden-Files.
4. Fachliche Regelvalidierung dokumentieren (Compliance-Gate Schritt 3).
