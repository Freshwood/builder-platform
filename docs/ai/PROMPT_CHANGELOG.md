# Prompt changelog

Every change to what steers the agent gets an entry here: the system prompt
(`apps/api/src/homeworking/modules/agent/prompts/system.de.md`), tool names, descriptions and
argument schemas (`modules/agent/tools.py`, `packages/construction-model` for the design
schema) and the routing rules (`modules/agent/routing.py`). `tests/test_prompt_lock.py` fails
until `PROMPT_VERSION`, `prompts/prompt.lock` (`task prompt:lock`) and this file are updated.

Each entry names the version, the fingerprint, what changed and why, and the effect on the
offline token benchmark (`task bench`). Every stored agent run carries `prompt_version` and
`prompt_fingerprint`, so a result can be traced back to exactly one entry.

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
