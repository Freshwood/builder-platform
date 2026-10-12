# Regression cases

One directory per real failure: `apps/api/tests/regressions/<slug>/`. `test_regressions.py`
replays every case offline (no network, no LLM). The schema is `RegressionCase` in `loader.py`;
every model forbids unknown keys, so a typo fails at load time.

```
<slug>/
  case.json          the case (see below)
  attempts/NN.json   recorded tool calls, exactly one `design_attempts` entry each
  golden.json        the hand-fixed correct design (AssemblyDesign JSON), if golden.design is used
```

## case.json

```json
{
  "id": "podium_kids_catwalk",
  "title": "Kinder-Podest: Oberfläche aus Brettern oder Platte",
  "origin": {"kind": "bug_report", "ref": "docs/problems/bug.md", "date": "2026-10-12"},
  "failure_class": "engine_loop",
  "brief": "Erstelle mir ein Podest für Kinder ... maximal 2 Meter lang und 1 Meter breit ...",
  "expect": {"envelope": {"max_length_mm": 2000, "max_width_mm": 1000}, "use": "indoor"},
  "attempts": [
    {
      "file": "attempts/01.json",
      "expect_outcome": "invalid_args",
      "errors_contain": ["design.explanation", "extra_forbidden"],
      "synthetic": true
    }
  ],
  "golden": {"design": "golden.json", "params": {"surface": "boards"}},
  "notes": "free text"
}
```

| Field | Meaning |
|---|---|
| `id` | Equals the directory name (`[a-z][a-z0-9_]*`). |
| `origin.kind` | `agent_run` (ref = `agent_runs.id`), `bug_report` (ref = docs path or commit) or `hand_written`. |
| `failure_class` | `args_syntax`, `schema_validation`, `engine_loop`, `intent_mismatch`, `drawing_defect` or `template_defect`. |
| `brief` | The user's text, verbatim. |
| `expect` | An `Expectation` document, see `calc_engine/assembly/intent.py` (envelope, use, support, materials, features). |
| `attempts[]` | `file`: record under `attempts/`. `expect_outcome`: outcome the replay must produce now. `errors_contain`: substrings that must occur in the replayed errors (the text the model sees). `synthetic`: reconstructed from a report, not recorded from a real run. |
| `golden` | The correct construction: exactly one of `design` (file) and `template` (key of a shipped template), plus `params`. Optional only for `args_syntax` and `schema_validation`. |

## attempts/NN.json

The entry as stored in `agent_runs.design_attempts`: `tool`, `tool_call_id`, `outcome`,
`accepted`, `errors`, `raw_args` (string or object, as the model sent it), `design`. Unknown keys
are rejected. Outcomes: `accepted`, `engine_rejected`, `invalid_args`, `parameter_error`,
`command_error`, `not_found`, `unknown_pack`, `no_project`, `exception`.

## What the test does

1. Replay: attempt `k` is sent through the real agent (`build_agent`, scripted `FunctionModel`)
   with the same tool name and `raw_args`. Earlier attempts with outcome `accepted` run first
   because they create the project later calls act on; earlier failures are skipped (each failed
   call counts against the retry budget of its tool and changes no state). The outcome must equal
   `expect_outcome` and the errors must contain every `errors_contain` string. `expect_outcome` is
   the outcome the code gives today, not necessarily the one of the original run: a bug that has
   been fixed shows up as `accepted`. Unrecorded successful calls (e.g. `create_project`) are not
   replayed; a truncated `raw_args` (`...[truncated, N chars in total]`) cannot be replayed.
2. Golden: the golden design is built and must pass `corpus.check` (all invariants),
   `intent.evaluate` with `expect`, and `intent.view_consistency`.

## Adding a case

Copy the `agent_runs` row's `design_attempts` entries into `attempts/NN.json` (in order), write
the `brief` and `expect`, fix the design by hand into `golden.json`, run
`uv run pytest apps/api/tests/test_regressions.py -k <slug>` and set `expect_outcome` from what
the replay really does. Never loosen `expect` to make a case pass.
