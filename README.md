# Homeworking – Builder Platform

> Aus einer natürlichen Beschreibung entsteht ein veränderbares, berechenbares und ausführbares
> Bauprojekt.

Dieses Repository enthält **Phase I**: die private DIY-Agent-Plattform mit Projektmodell und
deterministischer Engine. Vision und Schritte: [ROADMAP](ROADMAP.md).

**Jedes Projekt ist ein Unikat** (keine Packs, keine Vorlagen). Das LLM beschreibt Bauteile
(Material, Maß und Position als Ausdrücke über Parameter), die Engine prüft sie und leitet
Stückliste, Zuschnitt, Schrauben, Kosten, Zeichnungen, 3D-Modell und Anleitung ab. **Das LLM
rechnet nie.** Ohne Preisangabe des Nutzers sind Preise Richtpreise aus dem Katalog.

## Dokumentation

| Frage | Dokument |
|---|---|
| Welche Pakete gibt es, wer importiert wen, was lässt sich refaktorieren? | [docs/architecture/STRUKTUR.md](docs/architecture/STRUKTUR.md) |
| Fachliche Regeln (Modell, Engine, Agent, Sicherheit) | [docs/architecture/ARCHITEKTUR.md](docs/architecture/ARCHITEKTUR.md), Engine-Details in [ENGINE.md](docs/architecture/ENGINE.md) |
| Warum so entschieden? | [ADRs](docs/architecture/adr/README.md) |
| Prompts, Tools, Token-Budget ändern | [docs/ai/README.md](docs/ai/README.md) |
| Recht und Compliance | [docs/compliance](docs/compliance/README.md) |
| Regeln für Mensch und KI-Agent | [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md) |

## Schnellstart

Voraussetzungen: Docker, [uv](https://docs.astral.sh/uv/), Node mit Corepack,
[Task](https://taskfile.dev/installation/), Pango für WeasyPrint (`apt install libpango-1.0-0`).

```bash
task setup    # .env aus .env.example (LLM_MODE=test läuft ohne API-Key), uv sync, pnpm install
task dev      # Postgres, Migrationen, API :8000, Web :3000
task start    # wie Produktion: Seiten vorab gebaut
task          # alle Tasks auflisten; Argumente nach --, z. B. task test -- -k undo
```

Unter WSL mit dem Repo auf `/mnt/c` sind Imports und `next dev` sehr langsam; ein Klon im
Linux-Dateisystem hilft (oder `UV_PROJECT_ENVIRONMENT` unter `~`, siehe `.env.example`).

### Echtes LLM anbinden

Jeder OpenAI-kompatible Endpunkt funktioniert, gesteuert nur über `.env`:

```bash
LLM_MODE=openai
LLM_BASE_URL=https://api.mistral.ai/v1      # oder OpenRouter, Azure, LiteLLM-Proxy, Ollama …
LLM_MODEL=mistral-medium-latest
LLM_API_KEY=…
# optional: LLM_MODEL_FAST für Routine-Turns, AGENT_TOTAL_TOKENS_LIMIT (Standard 1 000 000)
```

Produktion: EU-Anbieter mit AV-Vertrag und Zero Data Retention
([DSGVO-Notizen](docs/compliance/dsgvo-dpia-template.md)). Mit `LLM_MODE=test` entwirft der
Offline-Planer nur Hochbeet und Regal. Echte Entwürfe brauchen ein Modell, das lange,
verschachtelte Werkzeug-Argumente zuverlässig erzeugt.

## Qualität

`task check` (Lint, Typen, Importgrenzen, Vitest) · `task test` (`test:pg` mit PostgreSQL) ·
`task test:web` (Vitest für `apps/web/src/lib`) · `task e2e` (Playwright, einmalig `task e2e:install`) · `task bdd` (Gherkin-Szenarien, API und Browser) · `task openapi` · `task ci` · `task fmt`.

## Die Engine erweitern

Kann die Engine eine Konstruktion nicht abbilden, wird sie allgemein erweitert, nie für ein
einzelnes Objekt:

1. Fähigkeit in `homeworking.construction_model.assembly` und `homeworking.calc_engine.assembly` ergänzen
   (Prompt-Änderung, Skill `prompt-change`).
2. Einen Entwurf, der sie nutzt, in den Corpus aufnehmen
   (`apps/api/tests/support/corpus_designs.py`).
3. Fachliche Regelvalidierung dokumentieren (Compliance-Gate Schritt 3).
