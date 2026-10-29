# Prompt changelog

Every change to what steers the agent gets an entry here: the system prompt
(`apps/api/src/homeworking/modules/agent/prompts/system.de.md`), tool names, descriptions and
argument schemas (`modules/agent/tools.py`, `packages/construction-model` for the design
schema) and the routing rules (`modules/agent/routing.py`). `tests/test_prompt_lock.py` fails
until `PROMPT_VERSION`, `prompts/prompt.lock` (`task prompt:lock`) and this file are updated.

Each entry names the version, the fingerprint, what changed and why, and the effect on the
offline token benchmark (`task bench`). Every stored agent run carries `prompt_version` and
`prompt_fingerprint`, so a result can be traced back to exactly one entry.

## 2026-10-29.2 (agent, fingerprint `3c4b23056f6e7ccf`; stages unchanged)

Zeitbudget, Chat-Seite: Mit den Bausteinen dauert die Pipeline 3–10 s, aber der Chat-Zug, der ein
Projekt beginnt (er füllt nur den Steckbrief für `plan_design`), brauchte mit `LLM_REASONING=low`
30–70 s und lief mehrfach ins Token-Limit (12000, „Model token limit exceeded“). Mit ausgeschaltetem
Denken: 8–15 s (6 von 6 Läufen), mit `minimal` weiter Ausreißer.

- Routing (`ROUTING_VERSION` 3): jede Nachricht ohne aktives Projekt bekommt Grund `new_project`
  (vorher `default` oder `structural`); Rolle bleibt `designer`.
- Laufzeit: für `new_project` setzt `api/chat.py` das Denken des Zuges auf `LLM_PLAN_REASONING`
  (Standard `off`); alle späteren Züge (Umbau, Fragen) behalten `LLM_REASONING`.
- System-Prompt, Tools und Schemas unverändert; der Fingerprint ändert sich nur durch die
  Routing-Version.
- Offline-Token-Benchmark: unverändert.

## 2026-10-29.4 (stages, fingerprint `137eeb9d017ba830`; agent unchanged)

Zeitbudget (`docs/ai/ZEITBUDGET.md`): mit dem konfigurierten deepseek-v4-flash scheiterten nicht nur
schwere Konstruktionen (Fachwerk, Carport: Geometrie, über 16000 Ausgabetokens im Modul), sondern
schon ein Wandregal in 54 s (ein Modul-Aufruf erzeugt rund 4000 Ausgabetokens bei 40–90 Token/s).
Ursache ist nicht das Modell, sondern dass es Hunderte Bauteile mit Koordinaten setzen soll.

- Neu: **Bausteine** (`calc_engine/pipeline/blocks`). Das Gerüst darf je Modul `block` setzen
  (`house`, `carcass`, `platform`, `table`, `post_frame`, `fence`, Optionen im Schema `BlockSpec`).
  Die Engine erzeugt die Teile selbst (Ausdrücke über die Parameter, Regler und Varianten bleiben
  nutzbar); für Block-Module gibt es keinen Modul-Aufruf und keine Reparatur durch das Modell.
- Gerüst-Prompt, Regel 8: Bausteine, ihre Optionen und `summary` höchstens 200 Zeichen. Das
  Schema wächst um `BlockSpec` und `ModuleBrief.block`.
- Laufzeit ohne Fingerprint-Änderung: Hat das Gerüst nur ein Modul ohne Baustein und nennt der
  Brief eindeutig ein Objekt (Carport, Zaun, Tisch, Regal, …), setzt die Engine den Baustein ein
  (`blocks/suggest.py`, Einstellung `ENGINE_BLOCKS=auto|model`); passt der Baustein nicht zu den
  Maßen, bleibt der Plan des Modells. Ausdrücke dürfen bis 2000 Zeichen lang sein (Dach-Neigung).
- Offline-Token-Budget (`test_stage_budget.py`): Gerüst-Anfrage 1800 → 2900 Token (Regel 8 und
  `BlockSpec`), Prefix 1700 → 2800. Begründung: dafür entfällt der Modul-Aufruf (3,4K Eingabe,
  bis zu 16K Ausgabe) bei allen Objekten, die ein Baustein abdeckt.
- Live (deepseek-v4-flash, `task pipeline:live`): Wandregal 7 s, Schuhregal 8 s, Podest 7 s,
  Fachwerkhaus 9 s (vorher Abbruch nach 54–90 s), 4–5K statt 27K Eingabetokens je Lauf.

## 2026-10-29.1 (agent, fingerprint `51ed6d86ec4a9c8b`; stages, fingerprint `94f26517d46587d5`)

Manual tests showed that a brief without dimensions never led to a design: the system was
unusable for a plain problem description. Causes: rule 3 ("frage gezielt nach") contradicted
rules 9 and 11, and `plan_design`, `/api/pipeline/skeleton` and `/modules` refused a brief
without any dimension (`missing_size`, 409). The live run of the pipeline and of the chat agent
with the child podium brief (dimensions given, height missing) already ended with an accepted
design; the blocker is the case with no dimensions at all.

- System prompt, rule 3: no questions for missing details; assume usual values, deliver, state the
  assumptions. Ask once only if it is unclear what to build.
- Skeleton prompt, rule 1: a missing dimension is chosen by the model (usual size for purpose and
  user), the parameters are created anyway, the assumption goes into `summary`. Never ask back.
- Runtime, no fingerprint change: `is_ready` only requires a non-empty description; the tool error
  `missing_size` became `empty_brief`; the two 409s only fire for an empty brief.
- Offline benchmark: no measurable change (routed flash total 5.199 -> 5.204 US cents).
- Runtime, no fingerprint change (time budget, see `docs/ai/ZEITBUDGET.md`): fixed budgets per
  category (medium 60 s, heavy 90 s) enforced per model request in the pipeline; the stage models
  get their own reasoning (`LLM_STAGE_REASONING` default `off`, `LLM_MODULE_REASONING` default
  `minimal`) and OpenRouter routes by throughput (`LLM_PROVIDER_SORT`); module repair rounds are
  limited by the deadline (up to 4) and all modules run at once; engine collision messages name
  where both parts lie.

## 2026-10-28.5 (agent, fingerprint `d1a105f6fbee5b28`)

First live run of the pipeline (`docs/ai/evals/2026-10-28-pipeline-v1.md`, six regression briefs,
deepseek-v4-flash for every role): 0 of 6 succeeded. Findings and what changed:

- Prompt: rule 9 no longer says "nimm übliche an und sag es" but "frage nicht nach: nimm übliche
  an, plane und nenne die Annahme". With a brief without dimensions the chat model asked a
  question instead of calling `plan_design` (run `kinderpodest_run_615963ad`). The planner's
  question step asks before the chat starts, so the chat should not ask again.
- Runtime, no fingerprint change: a `bool` parameter crashed the module prompt (`TypeError`);
  an unusable skeleton or module answer (`UnexpectedModelBehavior`, output cap) raised out of the
  tool instead of counting as a failed attempt; a failing brief was planned again and again by
  the chat model (3 skeleton and modules runs in one turn). Now: every pipeline error becomes a
  `PlanFailedError`, a turn starts at most two pipeline runs (`MAX_PLAN_RUNS`), and errors that
  no module owns revise the skeleton once (`SKELETON_REVISIONS`).
- Runtime, after the second run (`pipeline-v2`: all four briefs ended with a design, none met
  its expectations): with a real model `save_design` can no longer create a project (it fell
  back to the old one-call loop: 7 attempts, 134K tokens, 922 s); the customer's own wording is
  appended to the brief the chat model wrote (`ChatPlanner`), because wishes such as the
  material or the number of shelves got lost; skeleton and module agents allow two output
  retries and a failed module is asked again with the schema errors it caused; every failed stage
  run is stored with its error (`pipeline_stage` with `FAILED`, `stages.errors` in the eval).
- Runtime, settings: the stages used the chat's reasoning effort (`low`) and output cap (12K).
  Measured output per design: skeleton 8-17K tokens, modules 14-24K, docs 3-6K, mostly
  reasoning; one run took 995 s. New `LLM_STAGE_REASONING` (default `minimal`) and
  `LLM_STAGE_MAX_OUTPUT_TOKENS` (default 16K) apply to the stage models only.

## 2026-10-28.4 (agent, fingerprint `7384fcb1e8b62535`)

New designs now run through the staged pipeline (ADR-0010) instead of one `save_design` call;
the stage side is entry 2026-10-28.3 below.

- New tool `plan_design(spec, title, new_project)`. The chat model only fills the brief (`Spec`,
  lengths in mm); the API layer runs skeleton, modules, engine check and documentation and
  returns the usual project summary. `save_design` stays for structural rebuilds (rule 13).
- System prompt: rule 9 sends new projects to `plan_design`, rule 10 is now headed "Umbau-
  Entwürfe", rule 14 names `plan_design` for re-planning, rule 5 says that `plan_design` writes
  the explanation itself. The numbering of the rules is unchanged.
- Routing is unchanged (`ROUTING_VERSION` 2). The agent depends on a `DesignPlanner` protocol;
  `api/planner.py` owns the pipeline and stores every stage run with the chat id.

## 2026-10-28.3 (stages, fingerprint `4840ba6854eacfb4`)

Stage 5 of the staged design pipeline, used by `plan_design` (entry 2026-10-28.4 above).

- New stage 5 `docs.de.md` with the `Documentation` output (explanation and one step text per
  module). The engine assigns each module's parts to its step, validates the steps and falls
  back to module title and role if the engine rejects the wording or the model fails; the
  explanation stays empty then. Intake, skeleton and module prompts are unchanged.

Offline measurement (`task bench`, `tests/test_stage_budget.py`; chat requests are estimates):

| | before (2026-10-14.1) | after |
|---|---:|---:|
| Chat prefix per request | 7,608 | 8,371 (+763: `plan_design` 686, prompt +78) |
| New design, chat side (`design_create` / `plan_create`) | 16,880 in, 1,170 out | 17,379 in, 142 out |
| Docs request | – | 778 in |

The chat side of a new design stays at two requests but no longer writes the design: its output
drops from 1,170 to 142 tokens, and a repair no longer re-sends the 8K prefix (`free_design`:
5 requests, 48.6K, now 52.4K because `save_design` remains for rebuilds). The design itself costs
the stages: 1.7K skeleton (the 0.8K intake belongs to the planner question step), 3.3K per module and 0.8K documentation
on the request side; modules and documentation run on the small model. The prefix grew because
both `plan_design` and `save_design` are offered; removing `save_design` is only possible once
rebuilds go through the pipeline, too. Real output sizes and repair rates need a live run.

## 2026-10-28.2 (stages, fingerprint `f9c52dbd91ee58cf`)

Stage 3 of the design pipeline (ADR-0010): `modules.de.md` and the `ModuleDesign` output schema,
one small-model call per module of the skeleton. `STAGE_PROMPT_VERSION` covers all stages; the
intake and skeleton prompts are unchanged, the chat agent's prompt and `PROMPT_VERSION` too.

- A module call gets the catalog digest (`calc_engine.pipeline.materials`: ids and sizes, no
  prices), the brief, the skeleton parameters, its own box and its neighbours' boxes. It designs
  in module-local coordinates; the engine shifts and merges (`calc_engine.pipeline.merge`).
- The engine checks the merged design. Errors that name a part go back to the owning module only,
  with the module's own part ids; at most two repair rounds. Errors without a part (skeleton) end
  the stage with a rejection.
- No steps, explanation or prices in a module call; documentation becomes its own stage.

Offline measurement (`tests/test_stage_budget.py`, request side exact, output a lower bound):
3,293 input tokens per module request (prefix 2,697, of which the catalog digest is ~500). Calls
of one design share this prefix, so a provider cache can serve it. A four-module design costs
about 13K input tokens in modules plus 1.7K for the skeleton, against a 7.6K prefix on every
request of the old design call (2 to 8+ requests). Real output sizes are not measured yet.

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

Ältere Einträge (2026-10-07 bis 2026-10-14): [archiv/PROMPT_CHANGELOG-2026-10-07-bis-14.md](archiv/PROMPT_CHANGELOG-2026-10-07-bis-14.md).
