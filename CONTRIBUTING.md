# Contributing

Start with [AGENTS.md](AGENTS.md). It is written for both humans and AI coding agents: layout,
commands and rules.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/) with a scope that names the
area and a subject that says what changed. "Fix another bug" does not say what changed.

```
<type>(<scope>): <what changed>

<why, if not obvious>
```

- Types: `feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `build`, `ci`, `chore`.
- Scopes: `api`, `web`, `engine`, `model`, `agent`, `prompt`, `db`, `docs`, `infra`.
- **`prompt`** for anything that changes what the LLM sees (system prompt, tool descriptions or
  schemas, routing). The commit body names the new `PROMPT_VERSION`.
- **`agent`** for agent code that does not change the prompt (history handling, usage
  recording, model factory).

Examples:

```
perf(agent): compact history of earlier turns before each model request
feat(prompt): merge design tools into save_design (2026-10-07.3)
fix(web): reload drawings after a redesign with unchanged parameters
```

## Prompt and agent changes

Follow the workflow in [docs/ai/README.md](docs/ai/README.md). CI rejects unversioned prompt
changes (`test_prompt_lock.py`) and token regressions (`test_token_budget.py`).
