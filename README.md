# Homeworking – Builder Platform

> Aus einer natürlichen Beschreibung entsteht ein veränderbares, berechenbares und ausführbares
> Bauprojekt.

Vision und Schritte stehen in der [ROADMAP](ROADMAP.md). Dieses Repository enthält **Phase I**:
die private DIY-Agent-Plattform mit Projektmodell und deterministischer Engine. Geplant werden
kann auf drei Vertrauensstufen ([ADR-0004](docs/architecture/adr/0004-freie-entwuerfe-bauteilmodell.md)):

| Stufe | Beispiele | Woher die Konstruktion kommt |
|---|---|---|
| Geprüftes Pack | Hochbeet | programmiertes Construction Pack mit fachlich validierten Regeln |
| Vorlage | Regal, Gartenbank, Werkbank, Fensterladen | parametrischer Entwurf aus `calc_engine/data/templates/` |
| KI-Entwurf | alles aus Holz, Platten und Beschlägen | das LLM entwirft ein Bauteilmodell, die Engine prüft und berechnet |

Auch bei KI-Entwürfen rechnet das LLM nicht: Es beschreibt nur Bauteile (Material, Maß,
Position als Ausdrücke über Parameter). Die Engine prüft Katalogmaße, Kollisionen, Zusammenhang
und Boden- bzw. Wandkontakt und leitet Stückliste, Zuschnitt mit Schnittplan, Schrauben, Kosten,
Zeichnungen (Ansichten, Isometrie mit Positionsnummern) und das 3D-Modell ab.

Holz ist nicht auf die Katalogartikel beschränkt: **Maßholz** `lumber_<holzart>_<stärke>x<breite>`
(z. B. `lumber_douglas_18x96`, oder `lumber_<holzart>` mit Querschnitt aus dem Bauteilmaß) gibt es
in jeder Holzart mit Preis je m³ (`materials` in `data/catalog.json`: Fichte, Kiefer, Douglasie,
Lärche, Eiche, Buche, Robinie) und jedem Querschnitt; der Meterpreis folgt aus dem Holzvolumen.
Beschläge, die eine Bauanleitung nennt (Scharniere/Bänder, Verschlüsse, Griffe), müssen in der
Stückliste stehen, sonst lehnt die Engine den Entwurf ab. Beschläge mit festen Maßen (Ladenbänder,
Schubriegel) werden als Bauteile platziert und erscheinen in Zeichnung und 3D-Modell; bei
Wandmontage gibt es zusätzlich eine Isometrie und eine Rückansicht der Wandseite.

### Preise

Ohne Angabe des Nutzers ist jeder Preis ein **Richtpreis**: eine Spanne typischer Ladenpreise aus
`data/catalog.json` (Stand im Katalog), angezeigt als typischer Wert (Mitte) mit Spanne. Packungen
(Schrauben, Öl, Leim, Rollen) werden voll eingekauft; „davon verbraucht“ zählt nur den Anteil,
den das Projekt braucht (`BomLine.used_share`, `CostSummary.material_used`). Jede Position hat
Such-Links zu Händlern (Hornbach, OBI, Google Shopping) und ein Feld für den echten Preis; der
landet als Command `set_price` im Projekt-Log (rückgängig machbar, `ProjectInputs.prices`) und
ersetzt den Richtpreis in Stückliste, Summen, Varianten und PDF (`calc_engine.pricing`). Auch der
Assistent übernimmt genannte Preise („die Platte kostet bei mir 39,90 €“).

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
                                   + assembly/ (freie Entwürfe, Vorlagen, Projektion)
PostgreSQL (JSONB-Dokument + Command-Log)
```

Entscheidungen: [ADR-0001](docs/architecture/adr/0001-modularer-monolith.md) ·
[ADR-0002](docs/architecture/adr/0002-projektmodell-und-command-log.md) ·
[ADR-0003](docs/architecture/adr/0003-llm-gateway.md) · Compliance: [docs/compliance](docs/compliance/README.md)

## Schnellstart

Voraussetzungen: Docker, [uv](https://docs.astral.sh/uv/), Node 24 mit Corepack,
[Task](https://taskfile.dev/installation/) sowie Pango für WeasyPrint (`apt install libpango-1.0-0`).

```bash
task setup                    # .env aus .env.example (LLM_MODE=test läuft ohne API-Key), uv sync, pnpm install
task dev                      # Postgres, Migrationen, API :8000, Web :3000
task start                    # wie Produktion: Seiten vorab gebaut, kein Kompilieren beim ersten Aufruf
task                          # alle Tasks auflisten
```

`task dev` kompiliert jede Seite beim ersten Aufruf; damit das nicht beim Öffnen eines Projekts
passiert, ruft es nach dem Start alle Seiten einmal im Hintergrund auf (`apps/web/scripts/warmup.mjs`).
Unter WSL mit dem Repository unter `/mnt/c` dauert das trotzdem lange – schneller ist ein Klon im
Linux-Dateisystem oder `task start`.

Abhängigkeiten werden nur neu installiert, wenn sich Lockfiles ändern; `task dev`, `task test`
usw. installieren bei Bedarf selbst. Zusätzliche Argumente gehen nach `--`, z. B.
`task test -- -k undo`.

Ohne Task: `uv sync && corepack pnpm install`, `docker compose up -d postgres`,
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

Ohne LLM (`LLM_MODE=test`) versteht der Offline-Planer Hochbeet und die Vorlagen, z. B.
„Regal 80 × 30 × 180 cm mit 5 Böden“, „Gartenbank 1,6 m aus Lärche“, „Werkbank 150 × 70 cm mit
Rollen“. Freie Entwürfe brauchen ein Modell, das zuverlässig lange, verschachtelte
Werkzeug-Argumente erzeugt (Klasse Claude Sonnet, Mistral Medium 3.5 oder vergleichbar); für
Vorlagen und Maßänderungen genügt ein kleines Modell. Optional übernimmt `LLM_MODEL_FAST` diese
Routine-Turns, und `LLM_MODEL` bleibt für freie Entwürfe ([ADR-0006](docs/architecture/adr/0006-token-budget-und-modell-routing.md)).
`AGENT_TOTAL_TOKENS_LIMIT` (Standard 200 000) begrenzt einen Chat-Turn inklusive
Korrekturrunden.

Prompts, Tool-Definitionen und Routing sind versioniert und per Fingerprint jedem gespeicherten
Lauf zugeordnet. Den Token-Verbrauch misst `task bench` offline; Ablauf für Prompt-Änderungen
und Modellvergleich: [docs/ai/README.md](docs/ai/README.md).

Die Startseite fragt neben der freien Beschreibung einen optionalen Steckbrief ab (Einsatzort,
Montage, Maße, Holzart, Oberfläche, Budget, Erfahrung, Werkzeug, Nutzung); er wird als
strukturierte Liste an die erste Chat-Nachricht angehängt. Während der Assistent arbeitet, zeigt
der Chat jeden Arbeitsschritt live (Werkzeugaufrufe, Gedankengang, beim freien Entwurf die
Anzahl der bereits geschriebenen Bauteile), rechts erscheint ein Fortschrittspanel mit Laufzeit.
Um Modell-Runden zu sparen, stehen Packs und Vorlagen direkt in den Instruktionen, und die
Erläuterung wird beim Erstellen mitgegeben (`explanation`) statt per eigenem Aufruf.

## Qualität

| Befehl | Inhalt |
|---|---|
| `task check` | ruff, mypy (strict), import-linter (Modulgrenzen), eslint, tsc – Python und Web parallel |
| `task test` | pytest: Engine-Invarianten (hypothesis), SVG-Golden-Files, API, Agent, PDF |
| `task test:pg` | wie `test`, zusätzlich Integrationstest gegen PostgreSQL |
| `task e2e` | Playwright: Hochbeet planen → „50 cm breiter“ → Undo → Variante → PDF, mit axe-Prüfung (WCAG 2.2 AA); Browser einmalig mit `task e2e:install` |
| `task openapi` | OpenAPI exportieren und TypeScript-Client neu generieren (nur wenn sich die API geändert hat) |
| `task ci` | `check`, `test` und OpenAPI-Drift-Prüfung wie in der CI |
| `task fmt` | formatieren und Autofixes anwenden |

Hinweis für WSL: Liegt das Repo unter `/mnt/c`, sind Python-Imports sehr langsam
(der erste Import von WeasyPrint dauert etwa 20 s). Abhilfe: das Repo ins Linux-Dateisystem
legen oder `UV_PROJECT_ENVIRONMENT` auf einen Pfad unter `~` setzen (z. B. in `.env`, siehe
`.env.example`; Task lädt `.env` automatisch).

## Eine neue Vorlage hinzufügen

1. JSON-Datei in `packages/calc-engine/src/calc_engine/data/templates/` anlegen (`key`, `title`,
   `description`, `keywords`, `design` im Format `construction_model.assembly.AssemblyDesign`,
   `origin: "engine"`). Materialien und Maße stammen aus `data/catalog.json`; Holz in beliebigem
   Querschnitt als Maßholz `lumber_{wood}` (Querschnitt aus dem Bauteilmaß).
2. In `packages/calc-engine/tests/test_assembly.py` einen hypothesis-Test über den ganzen
   Parameterbereich ergänzen – er findet Kombinationen, bei denen Teile nicht mehr aufs
   Plattenformat passen oder sich durchdringen.
3. Die Schlüsselwörter machen die Vorlage auch für den Offline-Planer verfügbar.

## Ein neues Construction Pack hinzufügen

1. `packages/calc-engine/src/calc_engine/packs/<pack>/` anlegen mit Parametern (Pydantic),
   Geometrie, `build()` (BOM, Zuschnitt, Zeichnungs-IR, Anleitung, Hinweise, `RuleRef`s) und
   `variants()`.
2. Das Pack in `calc_engine.engine.default_engine()` registrieren.
3. Tests schreiben: Referenzfälle, Invarianten mit hypothesis, SVG-Golden-Files.
4. Fachliche Regelvalidierung dokumentieren (Compliance-Gate Schritt 3).
