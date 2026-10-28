# Live evaluation (`task eval:live`)

Answers one question that nothing else in the repo can: **does a real model solve the briefs?**
It sends the user texts of the regression cases through the full agent path with a real LLM and
checks what the agent built. It costs money, takes minutes and is never part of CI.

## Where it fits

| Tool | Checks | Needs an LLM | Cost | Where |
|---|---|---|---|---|
| `task bench` | prompt/tool size and repair-round cost (estimated tokens) | no | none | on every prompt change |
| `task test` (`test_regressions.py`) | tools and engine give the recorded outcome, the golden design builds and meets the intent | no | none | CI |
| `task eval:live` | a real model ends with a project that meets the intent of the brief | **yes** | cents to a few USD | before switching models, after a prompt change |

The offline tests prove the machinery is correct; the live eval measures the model.

## What it measures

Per brief (`apps/api/tests/regressions/<slug>/case.json`: `brief`, `expect`) and run k times
(`--runs`), through the same path as `api/chat.py`: redaction, safety gate, routing (`route()`),
`models.for_role`, the agent with all tools, the engine and the configured usage limits
(`AGENT_REQUEST_LIMIT`, `AGENT_TOTAL_TOKENS_LIMIT`). A fresh guest and no active project per
run, a throw-away SQLite database; nothing is written to `agent_runs`.

| Metric | Meaning |
|---|---|
| `accepted` | the run ended with a project whose engine result exists |
| `intent_violations` | `intent.evaluate` of the final project against the case's `expect` (envelope, use, support, materials, features). Empty = the brief is met |
| `view_violations` | `intent.view_consistency`: dimensions in the drawings agree with the solids. Reported, but not part of `success` |
| **`success`** | `accepted` AND no intent violation AND the agent run did not fail (usage limit, provider error) |
| `attempts` / `rejected` | entries of `AgentDeps.design_attempts`: every submitted design and every failed tool call; `rejected` = those that were not accepted (invalid arguments, engine rejection, ...). `outcomes` counts them by outcome. Fewer is better: each one is a repair round |
| `requests`, tokens | model requests and provider-reported input/output/cache tokens of the chat turn |
| `stages`, `stage_input_tokens`, `stage_output_tokens` | what `plan_design` spent in the pipeline stages (skeleton, modules, docs; ADR-0010): runs, failed runs, requests and tokens per stage. Read from the stage runs the planner stores in the throw-away database |
| `cost_usd` | chat turn plus stages, see below |
| `duration_s` | wall clock of the agent turn |
| `final_text` | the last assistant text (first 2000 characters), for reading failures |

Aggregates per brief and overall: `success_rate` (= `pass_at_1`, expected success of one run),
`pass_any` (at least one of the k runs succeeded), `pass_all` (every run succeeded), mean
attempts, rejected, requests and duration, cost.

### Cost

From the usage the provider reports per request (`AgentDeps.requests`, and the stored stage runs) and the list prices in
`docs/ai/models.json` (USD per 1M tokens): fresh input at `input`, cached input at `cache_read`,
output at `output`. A model is matched by its id, or by the longest listed id that prefixes the
answered name (dated variants). A model that is not in `models.json` has no cost (`n/a`, counted
as `unpriced_requests`); add it there in a reviewed commit first.

## What it cannot tell you

- It does not read the model's text for quality: only the intent rules in `expect` count. A
  construction that meets every rule can still be ugly or unwise; `expect` is the contract, so a
  brief is only as good as its `expect`. Never loosen `expect` to make a model pass.
- Only first messages: no follow-up turns, no existing project, no history. Routing therefore
  often picks the `fast` role for template-like briefs (see the plan table), as in the app.
- Non-streaming `agent.run`, while the app streams. Provider differences in streaming are not
  covered.
- Few runs are noisy: the models sample (temperature 0.2). One run per brief shows gross
  problems; for a decision use `--runs 3` or more and compare success rates, not single runs.
- Three cases are a smoke test, not a benchmark. The suite grows with every bug report.
- Latency depends on the provider's load at that moment.

## Running it

Prerequisites: `.env` with `LLM_MODE=openai`, `LLM_MODEL` (and optionally `LLM_MODEL_FAST`) and
the API key. Never paste the key anywhere else.

```bash
task eval:live -- --dry-run                         # plan and worst-case cost, no calls
task eval:live -- --label solar-v1 --runs 3 --yes   # real run
task eval:live -- --case podium_kids_catwalk --runs 5 --yes
task eval:live -- --model-role designer --label designer-only --yes   # skip the router
task eval:live -- --compare docs/ai/evals/2026-10-12-before.json docs/ai/evals/2026-10-12-after.json
```

Options: `--label` (report name, default `current`), `--runs N` (default 1), `--case SLUG`
(repeatable), `--model-role designer|fast`, `--cases-dir`, `--out` (default `docs/ai/evals`),
`--prices`, `--budget-usd` (default 5), `--yes`, `--dry-run`, `--allow-offline`, `--compare OLD NEW`.

### Guards against accidental spend

- Refuses in `LLM_MODE=test` (nothing real to evaluate), unless `--allow-offline`: then the
  offline model runs (free; a self-test of the harness, the numbers mean nothing).
- Real calls need `--yes` (or `LIVE_EVAL_YES=1`) and print a warning first. Without it the
  program exits with code 2 before a container or provider client exists.
- `--dry-run` lists every run with role, model and worst-case USD (token limit per run, all tokens
  at the dearer price) and exits.
- Each run is bounded by the usage limits of the app. `--budget-usd` stops starting new runs once
  the actual spend reaches it (the report is marked `aborted`). Needs a priced model.
- An existing report is never overwritten (`-2`, `-3`, ... is appended).

Costs, as a rule of thumb: one run is a normal chat turn, a few cents on Solar Pro 4 even with
several repair rounds (the worst case of a run is 0.07 USD at the default limits). Flash-class
designers cost several times that. A `--runs 3` pass over all briefs is typically well below
1 USD; check `--dry-run` for the bound.

## Reading the report

`docs/ai/evals/<date>-<label>.md` (and `.json` for `--compare`):

1. The header names the prompt version and fingerprint, the models per role, the run settings and
   whether the run was aborted. Reports of different fingerprints are exactly what you compare.
2. The table has one row per brief: successes/runs, `pass any`/`pass all`, mean attempts, intent
   and view violations, cost, time.
3. "Failed runs" list the violations (German texts of the engine rules, e.g. envelope or missing
   walkable top), the outcomes of the attempts and the model's final text. Start there: a failing
   brief usually shows either engine errors the model cannot repair (improve an error message or
   the prompt: the `prompt-change` skill) or a valid construction that misses the intent
   (prompt or template).
4. Compare mode prints per brief the success rate, mean attempts and cost per run, old to new, and
   marks `BROKEN` (succeeded before, never now), `REGRESSED` (rate dropped) and `improved`.
   Exit code 1 if anything regressed.

## When to run it

- **Before switching `LLM_MODEL` / `LLM_MODEL_FAST`:** run the same label scheme for the current
  and the candidate model (`--runs 3`), then `--compare`. Combine with `task bench` for the cost
  side and `docs/ai/README.md` ("Choosing models").
- **After a prompt, tool or schema change** (the `prompt-change` skill): run old and new once each
  if the change aims at model behaviour. Keep the report of the baseline.
- After adding a regression case, to see whether the current model solves it.
- **Never in CI**: it needs a key, costs money and is non-deterministic.

Reports in `docs/ai/evals/` are results of a run; commit one only when it backs a decision
(model change, changelog entry) and reference it there.
