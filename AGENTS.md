# Homeworking – guide for AI coding agents

Homeworking turns a DIY project description into a computable build project. The core rule
is that **the LLM never calculates**. It describes the parts; the deterministic engine checks
them and derives everything else (BOM, cut list, costs, drawings, 3D model).

## Layout

| Path | What |
|---|---|
| `apps/api` | FastAPI modular monolith (`homeworking`). The agent lives in `modules/agent`, the HTTP layer in `api/`. |
| `apps/web` | Next.js 16 + React 19 client (Vercel AI SDK `useChat`). See `apps/web/AGENTS.md`. |
| `packages/construction-model` | Pure domain model: inputs, commands, diff, `AssemblyDesign`. |
| `packages/calc-engine` | Deterministic engine, construction packs, design templates, catalog. |
| `packages/api-client` | Generated OpenAPI TypeScript client. Never edit `src/gen` by hand. |
| `docs/architecture/adr` | Architecture decisions (German). |
| `docs/ai` | Prompts, changelog, token benchmarks, model prices. |

Import boundaries are enforced by `lint-imports`. The domain model and the engine import no
platform, DB or LLM code, and only `homeworking.api` may use `modules.agent`.

## Commands (Taskfile)

- `task check`: ruff, mypy (strict), import-linter, eslint, tsc.
- `task test`: pytest on SQLite. `task test:pg` adds PostgreSQL.
- `task e2e`: Playwright with the offline LLM (`LLM_MODE=test`).
- `task bench`: offline token benchmark of the agent. No API calls, deterministic.
- `task prompt:lock`: record the prompt fingerprint after a prompt or tool change.
- `task openapi`: regenerate `openapi.json` and the TS client after API model changes.
- `task ci`: what CI runs.

## Rules

- **Code comments are in English**, also in files with German comments. User-facing texts and
  ADRs are German.
- **Prompt and agent changes are traceable.** Anything that changes what the model sees counts:
  `prompts/system.de.md`, tool names, tool docstrings, tool argument types, the `AssemblyDesign`
  schema and `routing.py`. Each such change requires a new `PROMPT_VERSION`, `task prompt:lock`,
  an updated snapshot and an entry in `docs/ai/PROMPT_CHANGELOG.md`. `tests/test_prompt_lock.py`
  enforces this. The workflow is in `docs/ai/README.md`.
- **Token budget.** `tests/test_token_budget.py` fails when requests grow. Do not raise a limit
  without a reason in the changelog. Tighten it when you make requests smaller.
- **Never let the LLM compute numbers.** New figures belong in the engine. The agent only passes
  them on.
- Tool results are compact text or JSON for the model. Large data (full BOM, designs, catalog)
  is fetched on demand, not returned by every tool.
- Every agent turn is stored in `agent_runs`, also failed ones; keep it that way (cost and
  provenance).
- CPU-bound engine or render work in request handlers runs in a worker thread
  (`ProjectService._build`, `run_in_threadpool`).
- Tests use the offline model. No test may need an API key or network access.

## Environment notes

- The repo usually sits on `/mnt/c` under WSL, so `next dev` compiles slowly. Use
  `task dev:warmup`, or `task start` for prebuilt pages.
- `.env` is loaded by Task. `LLM_MODE=test` needs no key.
