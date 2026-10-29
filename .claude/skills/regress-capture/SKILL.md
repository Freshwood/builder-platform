---
name: regress-capture
description: Turn a reported broken project, drawing or failed/looping agent run into a regression case, fix the root cause and keep it fixed. Use when a user reports a wrong or unbuildable result, when an agent run failed or looped, or when someone pastes a report like docs/problems/bug.md.
---

# Capture a failure as a regression case

Every reported failed project or drawing becomes a case in `apps/api/tests/regressions/<slug>/`
(format: `apps/api/tests/regressions/README.md`). A bug fix is not done without one. Never
commit; the maintainer reviews and commits.

## Workflow

1. **Capture.** With a run id (`agent_runs.id` or `trace_id`):
   `task regress:capture -- <run_id> [--slug name]`. Without database access, from an exported
   row: `task regress:capture -- --from-json row.json`. The draft lands in
   `apps/api/tests/regressions/_drafts/<slug>/` and is never discovered as a case. For a pasted
   report without a run (docs/problems/bug.md), write the case by hand
   (`origin.kind: bug_report`, `attempts[].synthetic: true`) and skip to step 2.
2. **Read and classify.** Read `case.json`, the `attempts/NN.json` files and the brief. The
   `failure_class` is only a guess from the recorded outcomes; set the right one (table below).
   Fill in `title` (German, one line).
3. **Write `expect` from the BRIEF.** Use the vocabulary of `homeworking/calc_engine/assembly/intent.py` and
   only constraints the user actually stated. Never invent a constraint to make a case pass and
   never loosen one later.
   - `envelope`: `max_length_mm`, `max_width_mm`, `max_height_mm` and `min_*` ("maximal 2 m lang").
   - `use`: `indoor` / `outdoor` ("drinnen", "im Garten").
   - `support`: `floor` / `wall` ("an die Wand", "steht auf dem Boden").
   - `materials_any` / `materials_none`: "aus Brettern" is `materials_none: ["square_"]`, "Lärche"
     is `materials_any: ["larch"]`.
   - `features`: `walkable_top`, `choice_param:<name>=<v1>|<v2>` ("aus Brettern oder Platte"),
     `hinged_doors`, `standing_stable`, `levels`, `contoured`.
   - `parts` (min/max component count) only when the user named a count.
4. **Produce the reference.** The corrected design that satisfies the brief, built through the
   engine (the LLM never calculates): `reference.json` (an `AssemblyDesign`) plus the `params`
   in the `reference` block. Run it: `task regress -- -k <slug>` must show the reference meeting
   the corpus invariants, `expect` and the view consistency. Fix the reference, not `expect`. For
   `args_syntax` and `schema_validation` the `reference` block may be removed.
5. **Confirm the case reproduces the failure on the OLD behaviour.** A case that never failed is
   worthless. Replay with the code before your fix: the recorded call must show the reported
   outcome and `errors_contain` must match what the model saw. Once the bug is fixed, set
   `expect_outcome` to what the code does now (often `accepted`); the reference and the intent
   checks keep guarding. For a draft from a run the recorded outcome is the starting point.
6. **Fix the root cause** (table below). A change to the system prompt, a tool, the design schema
   or routing goes through the `prompt-change` skill (new `PROMPT_VERSION`, lock, snapshot,
   changelog). Do not paper over an engine defect in the prompt.
7. **Promote.** Delete every `TODO` (title, `notes`, `expect.note`), then
   `task regress:promote -- <slug>`. It loads the draft with the real loader, replays it and
   moves it to `regressions/<slug>/` only when that is green. Run `task regress`, then `task
   check` and `task test`, and hand back to the maintainer. Never commit or push.

## Failure classes

| `failure_class` | Typical sign | Usually fixed in |
|---|---|---|
| `args_syntax` | `invalid_args`, "Kein gültiges JSON" (broken brackets, unquoted formulas) | `modules/agent/args.py` repair; add the call to `apps/api/tests/fixtures/tool_args/` |
| `schema_validation` | `invalid_args`, `loc: message [type]` (extra or missing fields, wrong types) | schema or tool description via `prompt-change`; clearer validator messages in `construction-model` |
| `engine_loop` | two or more `engine_rejected` in a row, the model cannot repair | engine error messages (what to change), expression/resolve rules, template; prompt only if the rule is missing |
| `intent_mismatch` | accepted design that ignores the brief (too big, wrong material, no door) | engine/template defaults, prompt rule, or a missing `intent` feature |
| `drawing_defect` | project builds but views, dimensions or cut list disagree | drawing generation in `calc_engine`; extend `intent.view_consistency` |
| `template_defect` | shipped template fails for some parameters | `homeworking/calc_engine/data/templates/*.json` and the construction pack |

The heuristic of `capture` picks: unrepairable JSON, else any `invalid_args`, else at least two
`engine_rejected`, else `intent_mismatch`. A run with one schema error followed by an engine
loop is guessed as `schema_validation`; reclassify it.

## Rules

- Redaction is automatic (no user id, chat id, e-mail, connection string), but read the draft
  before it is committed: the brief is the user's own text.
- Attempts of older runs lack `raw_args`/`outcome`; they stay as files but are not replayed
  (the draft `notes` say so). Reconstruct the call by hand and mark it `synthetic` if needed.
- `expect_outcome` is the outcome the code gives today, never a wish.
- Live checks against a real model (`task eval:live`, costs money, not in CI) use the briefs of
  these cases; see `docs/ai/EVALS.md`.
