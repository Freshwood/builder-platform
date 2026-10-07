---
name: prompt-change
description: Change the agent's system prompt, a tool (name, docstring, arguments), the design schema or the model routing in a traceable way. Use whenever a change affects what the LLM sees.
---

# Traceable prompt or agent change

Everything the model sees is fingerprinted (`modules/agent/provenance.py`). Follow these steps for
every change to `prompts/system.de.md`, `modules/agent/tools.py` (names, docstrings, argument
types), `packages/construction-model/.../assembly.py` (design schema) or
`modules/agent/routing.py`.

1. Measure before: `task bench -- --label before --out /tmp/bench`.
2. Make the change. Keep rules in one place, either the system prompt or the tool description,
   never both.
3. Bump `PROMPT_VERSION` in `modules/agent/prompts/__init__.py` (`YYYY-MM-DD.n`). For a routing
   change, also bump `ROUTING_VERSION`.
4. Run `task prompt:lock`.
5. Run `task test -- apps/api/tests/test_prompt_lock.py --snapshot-update`, then read the
   snapshot diff in `apps/api/tests/__snapshots__/test_prompt_lock.ambr`. It is exactly what the
   model will receive.
6. Measure after: `task bench -- --label <PROMPT_VERSION>`. This writes to `docs/ai/benchmarks/`.
7. Add an entry to `docs/ai/PROMPT_CHANGELOG.md`: version, fingerprint (from `prompt.lock`),
   what changed and why, and the token delta from step 1 to step 6.
8. If requests got smaller, tighten `BUDGET` in `apps/api/tests/test_token_budget.py`. If they
   got bigger, justify it in the changelog.
9. Run `task test`. `test_prompt_lock.py` and `test_token_budget.py` must pass.

Old chats are replayed as history. If you rename a tool, keep the old name in
`DESIGN_TOOLS`/`LOOKUP_TOOLS` (`history.py`) and in `apps/web/src/lib/activity.ts`.
