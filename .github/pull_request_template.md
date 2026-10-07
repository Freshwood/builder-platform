## What and why

<!-- One or two sentences. Link the problem (docs/problems/…) or ADR if there is one. -->

## Checklist

- [ ] `task ci` passes locally (checks, tests, OpenAPI drift)
- [ ] UI changes: `task e2e` passes

### Prompt / agent changes

<!-- Required if this PR changes what the LLM sees: prompts/system.de.md, tool names, docstrings
     or argument types, the AssemblyDesign schema, routing.py. See docs/ai/README.md. -->

- [ ] No prompt/agent change, **or**:
- [ ] `PROMPT_VERSION` bumped: `____`, `task prompt:lock` run (fingerprint `____`)
- [ ] Prompt snapshot diff reviewed (`apps/api/tests/__snapshots__/test_prompt_lock.ambr`)
- [ ] `docs/ai/PROMPT_CHANGELOG.md` entry with reason
- [ ] `task bench` result committed; token delta vs. previous version: `____`
