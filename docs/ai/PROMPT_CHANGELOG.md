# Prompt changelog

Every change to what steers the agent gets an entry here: the system prompt
(`apps/api/src/homeworking/modules/agent/prompts/system.de.md`), tool names, descriptions and
argument schemas (`modules/agent/tools.py`, `packages/construction-model` for the design
schema) and the routing rules (`modules/agent/routing.py`). `tests/test_prompt_lock.py` fails
until `PROMPT_VERSION`, `prompts/prompt.lock` (`task prompt:lock`) and this file are updated.

Each entry names the version, the fingerprint, what changed and why, and the effect on the
offline token benchmark (`task bench`). Every stored agent run carries `prompt_version` and
`prompt_fingerprint`, so a result can be traced back to exactly one entry.

## 2026-10-28.1 (stages, fingerprint `c0a70f8a81c47d00`)

New, separately versioned prompts for the staged design pipeline (ADR-0010): `intake.de.md`
(stage 1) and `skeleton.de.md` (stage 2) in `modules/pipeline/prompts/`. Fingerprint and lock
(`stages.lock`) cover the instructions and the output schema of both stages; the chat agent's
prompt and `PROMPT_VERSION` are unchanged.

- Intake reads the facts of the description into a `Spec` and words the open questions. The
  engine decides which questions are open (`calc_engine.pipeline.gaps`); the model has no tools.
- Skeleton plans parameters and modules only (no parts). The engine applies the customer's
  facts (use, support, finish, dimensions) and checks every expression before the result is
  accepted; one repair round with the engine's problems.

Offline measurement (`tests/test_stage_budget.py`, request side exact, output a lower bound):
intake 810 input tokens per request (prefix 712), skeleton 1,690 (prefix 1,598). The old single
design call carried a 7,608-token prefix on every request. Neither stage is connected to the
chat yet, so the end-to-end saving is not measured.

## 2026-10-14.1 (fingerprint `417fa06d546c2a92`, routing version 2)

Runtime change without a fingerprint change (regression case
`podest_kinder_modenschau_es_so_art_2`, run 3289388f, upstage/solar-pro4): the kids' podium turn
aborted with `UsageLimitExceeded` (207,638 > 200,000 tokens) before request 8. The superseded
designs were already stubbed, but every repair round's thinking (~3K tokens) was resent, so the
input grew 8K → 32K tokens per request. The sixth design was geometrically valid and failed only
on free-text screws under `hardware`.

- `history.py`: in the current turn only the latest response keeps its thinking.
- `args.py`: `explanation` written into the `design` object is moved to the `save_design` argument
  (the same `extra_forbidden` cost a request in `podium_kids_catwalk`, whose attempt 01 is now
  accepted).
- Engine: screws listed under `hardware` are ignored when `auto_screws` is on (the engine derives
  them); other unknown fittings name the nearest catalog id.
- `AGENT_TOTAL_TOKENS_LIMIT` default 200,000 → 1,000,000 (maintainer's decision): reasoning
  models use most of the budget for repair rounds.

Offline benchmark: unchanged (`free_design` 48,563), the offline model writes no thinking.

Product direction (ROADMAP.md, "Aktueller Schwerpunkt (2026-10-14)", ADR-0008): every project
is a one-off. A construction pack or a curated template makes every result look the same, so
the agent now designs every project itself from the customer's brief, and the engine checks
it and derives everything else. Packs (`raised_bed`) and the six design templates are removed
from the engine, the API and the agent.

- Tools removed: `create_project` (packs), `create_from_template`, `get_template_design`,
  `list_construction_packs`. The old names stay in `history.LOOKUP_TOOLS` so stored chats are
  still compacted.
- The pack/template overview that was appended to the instructions on every request is gone.
- Rule 9 now says: every project is a one-off, always designed with `save_design` from the
  brief; use, support and "unbehandelt" go straight into the design. Rules 5, 8, 10, 13 and 14
  lose their pack/template wording.
- `save_design` and `get_current_design` descriptions no longer distinguish "free-form" from
  pack/template projects. Tool results no longer carry `trust`.
- Routing (`ROUTING_VERSION` 2): the `pack_or_template` shortcut to the fast model is gone; a
  new project is a design and goes to the designer model.

Offline benchmark (`2026-10-10-prompt-2026-10-10-1.md` → `2026-10-14-prompt-2026-10-14-1.md`):
static prefix 9,163 → 7,607 tokens per request (−1,556, −17 %; instructions 3,531 → 2,867, tool
definitions 5,632 → 4,740). The scenarios `pack_create` and `template_create` are replaced by
`design_create` (one design accepted on the first attempt, 16,880 tokens). Comparable scenarios:
`free_design` 59,518 → 48,563 (−18 %), `followup_1` 21,084 → 17,886 (−15 %), `followup_2`
22,591 → 19,381 (−14 %). `test_token_budget.py` is tightened accordingly.

## 2026-10-10.1 (fingerprint `302126348b5f7ffc`)

Bug report "Could not create a simple project" (`docs/problems/bug.md`): the user wanted a
podium whose top is either boards or a panel. The model used a `choice` parameter
`surface_type` in `when` and got `Unbekannter Name 'surface_type'`. It then rephrased the same
call eight times ("Vielleicht muss ich die when-Bedingung als if(...) schreiben?") without ever
changing the approach, and the turn ended unresolved.

The engine could not do what the prompt implied. `_number_env` put only numeric parameters into
the expression environment, and the evaluator accepted only bool/number constants, so a
`choice` parameter was invisible to `when` no matter how it was written. The prompt mentioned
`when` but never said which parameters were legal there, so the model could only guess.

- Rule 10: expressions compute with numbers only; a `choice` parameter is text and may be
  compared with `==`/`!=` in `when`, never computed with and never ordered with `<`/`>`. A
  choice value as a measurement is rejected – use a `count` parameter.
- Not visible to the model, but the actual fix: `assembly/expr.py` evaluates to `float | str`,
  `assembly/resolve.py` builds the environment from all parameters. Text may only be compared
  for equality, mixed text/number comparisons and arithmetic on text raise a message that names
  the mistake. Both cases from the bug report are regression tests in
  `packages/calc-engine/tests/test_assembly.py`.

Offline benchmark (`2026-10-09-prompt-2026-10-09-1.md` → `2026-10-10-prompt-2026-10-10-1.md`):
static prefix 9,082 → 9,163 tokens per request (+81, +0.9 %, instructions only; tool
definitions unchanged at 5,632), input over all five scenarios 140,662 → 141,707 (+0.7 %).
Accepted: the reported turn spent eight repair rounds on an error that no phrasing could fix,
so the prefix increase pays for itself within a handful of such turns. All scenarios stay
within the existing `test_token_budget.py` limits (unchanged).

## 2026-10-09.1 (fingerprint `95953ba37c29e83d`)

Bug report "Construction not working" (Tonie cloud shelf, no progress in a whole turn): the
model wrote formulas unquoted (`"at": [150, 0, 18 + (i + 1) * …]`), the JSON was invalid, the
error told it to "pass an object, not a string", and it repeated the same mistake until
`save_design` ran out of retries. The `cloud_shelf` template would have fitted, but could not
be wall-mounted, so the model designed freely.

- Rule 10: every expression is a quoted string (with example), only plain numbers unquoted.
- Rule 9: brief location and mounting go to `use`/`support` of the template; a template that
  differs only in mounting or finish still fits (material wishes stay binding, rule 8).
- `create_from_template`: new arguments `use` and `support` (they were silently dropped when
  sent among the params).
- Template `cloud_shelf`: description says "stehend oder an der Wand". The cloud stays birch
  plywood: spruce glulam panels are only 600 mm wide and the template must stay valid over its
  whole parameter range (now also tested wall-mounted).
- Not visible to the model, but part of the fix: `modules/agent/args.py` repairs unquoted
  expressions and unbalanced brackets in the raw tool call (`RepairToolArgs`) and in object
  arguments sent as strings; the error message now names the likely cause.

Offline benchmark (`2026-10-08-prompt-2026-10-08-1.md` → `2026-10-09-prompt-2026-10-09-1.md`):
static prefix 8,894 → 9,082 tokens per request (+188, +2.1 %: instructions +70,
`create_from_template` 309 → 427), input over all five scenarios 138,224 → 140,662 (+1.8 %).
Accepted: a failed design turn like the reported one (about six requests of 11–13K tokens)
costs as much as the added prefix over roughly 400 requests; all scenarios stay within the
existing `test_token_budget.py` limits (unchanged).

## 2026-10-08.1 (fingerprint `f17bb3be32d5a296`)

Free forms, members, carpentry joints and buildings (ADR-0007). The model can now describe
any outline and timber-frame houses; the engine computes contours, angles and lengths:

- Design schema: parts are boxes (`size`/`at`) or members (`start`/`end` with `section`,
  `facing` and end `cuts` square/level/plumb/corner), with an optional `shape` (cloud,
  ellipse, rounded, triangle, arch, polygon) and `cutouts`. New `joints` (tenon, half_lap,
  notch) and `category` ("building"). Field descriptions kept short; the rules live in the
  system prompt.
- Rule 10: members for sloped timbers, shapes instead of box mosaics ("never claim only
  rectangles are possible" – the agent told a user a cloud shelf was impossible), joints,
  buildings with concrete foundations below z = 0, area/volume materials.
- Rule 6: new buildings are planned (with the statics and permit notice); interventions in
  existing load-bearing structures are still referred to professionals.
- Planning overview lists the new templates `cloud_shelf` and `timber_frame_house`.

Offline benchmark (previous commit, identical to `2026-10-07-phase1.md` →
`2026-10-08-prompt-2026-10-08-1.md`): static prefix 7,213 → 8,894 tokens per request
(+23 %: instructions +562, `save_design` definition 2,398 → 3,517), input over all five
scenarios 115,331 → 138,224 tokens (+20 %). Accepted because the schema now carries the
geometry vocabulary that previously made free forms impossible; `test_token_budget.py`
limits were raised accordingly (old values noted there).

## 2026-10-07.3 (fingerprint `aaa89bea761f5d94`)

Token budget overhaul (review 2026-10-07, ADR-0006). Same rules, fewer tokens:

- `design_project` and `redesign_project` merged into `save_design`: the design JSON schema
  was sent twice with every request (−3K tokens per request).
- Expression description in the design schema stated once (in `AssemblyDesign`) instead of on
  11 fields; duplicated tool argument docs shortened.
- System prompt moved to `prompts/system.de.md` and condensed from 10.1K to ~8K characters;
  all 14 rules kept, rule 12 now points to `get_project` for `item_id`, rule 13 to
  `save_design` without title/params.
- `list_materials` returns a compact text table instead of JSON (−50 %).
- Create/change results no longer contain the bill of materials (only `get_project` does).
- History processor: older turns lose design arguments, catalog/template lookups and thinking;
  superseded designs in the current turn are stubbed.
- Routing version 1 (fast model for templates, parameter changes, questions).

Offline benchmark (`docs/ai/benchmarks/2026-10-07-baseline.md` → `2026-10-07-phase1.md`):
static prefix 11,839 → 7,213 tokens per request (−39 %), input over all five scenarios
212,069 → 115,331 tokens (−46 %), follow-up turns 40–42K → 17–19K tokens (−56 %).

## 2026-10-07.2 and earlier

Recorded only as `PROMPT_VERSION` in git history (no fingerprint):
2026-10-02.1, 2026-10-06.1, 2026-10-06.2, 2026-10-06.3, 2026-10-07.1, 2026-10-07.2
(last: rule 5 asks for 4–6 paragraph explanations, docs/problems/bug.md).
