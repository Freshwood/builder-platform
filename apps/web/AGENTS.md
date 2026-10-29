<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Skripte und Tests

Aus `apps/web` mit `corepack pnpm <skript>`; im Repo-Root decken `task check:web`, `task test:web`
und `task e2e` dasselbe ab.

| Skript | Zweck |
|---|---|
| `dev`, `build`, `start` | Next.js (Port 3000) |
| `lint`, `typecheck` | eslint, tsc (zusammen mit `test` Teil von `task check:web` und CI) |
| `test`, `test:watch` | Vitest für die reine Logik in `src/lib` (`*.test.ts` neben dem Code, Node-Umgebung, Alias `@/`) |
| `test:e2e` | Playwright-Specs in `tests/e2e` (nur Abläufe ohne Gegenstück als Szenario) |
| `test:bdd` | Gherkin-Szenarien in `tests/bdd` (`bddgen`, dann Playwright) |
| `e2e` | `test:e2e` und `test:bdd` zusammen; startet API (8010) und Web (3010) selbst |
| `generate` | TS-Client nach `src/api/gen` aus `openapi.json` (nie von Hand ändern) |
| `format` | prettier |

Neue Logik ohne React und DOM gehört nach `src/lib` und bekommt dort einen Vitest-Test. Browser-Tests
bevorzugt als Szenario in `tests/bdd/features`; gemeinsame Helfer liegen in `tests/support`.
