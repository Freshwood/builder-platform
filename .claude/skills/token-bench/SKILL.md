---
name: token-bench
description: Measure the agent's token use and cost offline (no API calls) and compare it with earlier runs. Use when asked about token usage, LLM cost, prompt size or model choice.
---

# Offline token benchmark

`task bench -- --label <name>` replays five fixed scenarios through the real agent, tools and
engine with a scripted model:

- pack project;
- template project;
- free design with two engine rejections;
- two follow-up turns.

It meters every model request: instructions, tool definitions, history and output.

- Results go to `docs/ai/benchmarks/<date>-<label>.{json,md}`, including the static prefix per
  tool.
- Costs per model configuration are computed from `docs/ai/models.json`. The prices there carry
  a source and a date; update them by hand from https://openrouter.ai/api/v1/models.
- Token counts are estimates (`CHARS_PER_TOKEN` in `modules/agent/metering.py`). Deltas between
  runs are exact.
- Compare against `docs/ai/benchmarks/2026-10-07-baseline.md`.

Latency and design quality need a live run; see "Choosing models" in `docs/ai/README.md`.
