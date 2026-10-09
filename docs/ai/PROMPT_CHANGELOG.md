# Prompt changelog

Every change to what steers the agent gets an entry here: the system prompt
(`apps/api/src/homeworking/modules/agent/prompts/system.de.md`), tool names, descriptions and
argument schemas (`modules/agent/tools.py`, `packages/construction-model` for the design
schema) and the routing rules (`modules/agent/routing.py`). `tests/test_prompt_lock.py` fails
until `PROMPT_VERSION`, `prompts/prompt.lock` (`task prompt:lock`) and this file are updated.

Each entry names the version, the fingerprint, what changed and why, and the effect on the
offline token benchmark (`task bench`). Every stored agent run carries `prompt_version` and
`prompt_fingerprint`, so a result can be traced back to exactly one entry.

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
