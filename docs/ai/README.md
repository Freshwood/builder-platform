# AI layer: how prompts, agents and their changes stay traceable

This directory is the single place for everything that steers the LLM and for the evidence
behind it. Architecture decision: [ADR-0006](../architecture/adr/0006-token-budget-und-modell-routing.md).

| What | Where |
|---|---|
| System prompt | `apps/api/src/homeworking/modules/agent/prompts/system.de.md` |
| Prompt version | `PROMPT_VERSION` in `modules/agent/prompts/__init__.py` |
| Tools (names, descriptions, argument schemas) | `modules/agent/tools.py`, design schema in `packages/construction-model/src/construction_model/assembly.py` |
| Model routing | `modules/agent/routing.py` (`ROUTING_VERSION`) |
| History compaction | `modules/agent/history.py` |
| Fingerprint lock | `modules/agent/prompts/prompt.lock` |
| Readable snapshot of the full prompt | `apps/api/tests/__snapshots__/test_prompt_lock.ambr` |
| Changelog | [PROMPT_CHANGELOG.md](PROMPT_CHANGELOG.md) |
| Token benchmarks | [benchmarks/](benchmarks/) |
| Model prices (source + date) | [models.json](models.json) |

## Changing a prompt, a tool or the routing

1. Make the change.
2. Bump `PROMPT_VERSION` (`YYYY-MM-DD.n`).
3. Run `task prompt:lock`. It refuses to update the lock without a version bump.
4. Run `task test -- --snapshot-update` and review the snapshot diff: it shows exactly what the
   model will see.
5. Run `task bench -- --label <version>`. It records tokens and costs in `docs/ai/benchmarks/`.
6. Add an entry to `PROMPT_CHANGELOG.md`: what changed, why, and the benchmark delta.
7. If the change makes requests smaller, tighten `BUDGET` in `apps/api/tests/test_token_budget.py`.

CI enforces steps 2–4 and 7 through `test_prompt_lock.py` and `test_token_budget.py`.

## Tracing a result back

Every agent turn is stored in `agent_runs`, including failed and cancelled runs. A run records:

- `prompt_version`, `prompt_fingerprint` and `safety_rules_version`;
- `model` and `model_role` (`designer` | `fast`) with `routing_reason`;
- `duration_ms`;
- `usage`: tokens per request, cache reads, and the model the provider actually used;
- every submitted design in `design_attempts`.

Each project change links back to its run via `project_commands.llm_trace_id`. The logs carry the
same data as JSON lines (`agent_turn`, `agent_turn_done`).

### `design_attempts`: turning a failed run into a test

Despite its name, the JSON column `agent_runs.design_attempts` (no extra column) holds one entry
per submitted design and per failed tool call of any tool, in call order. Successful calls of
other tools are not recorded. Entries are built by `tool_attempt()` in `modules/agent/tools.py`:

```json
{
  "tool": "save_design",
  "tool_call_id": "call_0",
  "outcome": "invalid_args",
  "accepted": false,
  "errors": ["design.explanation: Extra inputs are not permitted [extra_forbidden]"],
  "raw_args": {"title": "Regal", "design": {"...": "..."}},
  "design": null
}
```

- `raw_args` is what the model sent: the JSON string or object before `RepairToolArgs` and
  pydantic validation (cut at 200 000 characters with a `…[truncated, N chars in total]` marker).
  Feeding it to a `FunctionModel` `ToolCallPart` replays the call.
- `outcome`: `accepted`, `engine_rejected` (`errors` = engine messages), `invalid_args` (schema
  violation or unrepairable JSON, `errors` = one `loc: message [type]` line each, or the repair
  hint), `parameter_error`, `command_error`, `not_found`, `unknown_pack`, `no_project`,
  `exception` (unexpected error in a tool).
- `design` is the validated design (origin `ai`) for accepted and engine-rejected `save_design`
  calls, otherwise `null`. `tool`, `accepted`, `errors` and `design` exist in older runs, too;
  those lack `tool_call_id`, `outcome` and `raw_args`.
- Not recorded: calls of unknown tools and `get_template_design` with an unknown key.

Hooks (`RecordToolAttempts`, pydantic-ai capability): `before_tool_validate` keeps the raw
arguments by `tool_call_id`, `on_tool_validate_error` and `on_tool_execute_error` record the
failures that never reach a tool body; the bodies call `_attempt` / `_fail`. Add the `raw_args`
of a bad run as a fixture under `apps/api/tests/fixtures/tool_args/` (see `test_failure_capture.py`).

## Regression cases

Every reported failed project or drawing becomes a regression case that is replayed offline in CI
(`task regress`). Capture a failed run with `task regress:capture -- <run_id>`, finish the draft
and promote it with `task regress:promote -- <slug>`. Format and rules:
[apps/api/tests/regressions/README.md](../../apps/api/tests/regressions/README.md); workflow:
skill `.claude/skills/regress-capture/SKILL.md`. The briefs of these cases can also be run against
a real model: [EVALS.md](EVALS.md) (`task eval:live`).

## Choosing models

`LLM_MODEL` is the designer: free-form designs and structural changes. `LLM_MODEL_FAST` is
optional and takes routine turns. Offline evidence (`task bench`, prices from
`docs/ai/models.json`, 2026-10-07):

- Solar Pro 4, the current model, is the cheapest of the compared models.
- Moving routine turns to a "flash" model would raise costs: Gemini 3.8 Flash costs about 8×
  as much.
- What can pay off is the reverse: keep Solar for routine turns (`LLM_MODEL_FAST`) and use a
  stronger designer (`LLM_MODEL`), **if** it needs fewer repair rounds. One repair round costs
  the designer about one extra request; the benchmark reports this as "+1 repair round".

Design quality and latency cannot be measured offline. Before switching the designer, do a live
run:

1. Set `LLM_MODE=openai` and the candidate models in `.env`.
2. Send the same 5–10 briefs (e.g. the benchmark scenarios) through the UI or `POST /api/chat`.
3. Compare per model, using `agent_runs`:

```sql
select model, model_role,
       avg(duration_ms) as avg_ms,
       avg((usage->>'requests')::int) as avg_requests,
       avg(jsonb_array_length(design_attempts)) as avg_attempts,
       avg((usage->>'input_tokens')::int) as avg_input_tokens
from agent_runs
where prompt_version = '<version>'
group by model, model_role;
```

Fewer design attempts at the same quality is what justifies a more expensive designer.
