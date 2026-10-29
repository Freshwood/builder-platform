# Funktionale BDD-Szenarien: Browser

Gherkin auf Deutsch, ausgeführt mit [playwright-bdd](https://vitalets.github.io/playwright-bdd/)
in Chromium (de-DE). Die Szenarien bedienen die Oberfläche und kennen keine Implementierungsdetails.

```bash
task bdd:frontend                    # nur diese Szenarien
task bdd:frontend -- --grep Regal    # nach Szenarioname filtern
task e2e                             # alle Browser-Tests (tests/e2e und tests/bdd)
```

Im Paket `apps/web` entsprechen dem die Skripte `pnpm test:bdd` (nur Szenarien), `pnpm test:e2e`
(nur die Specs in `tests/e2e`) und `pnpm e2e` (beides). Die Specs in `tests/e2e` decken nur
Abläufe ab, für die es kein Szenario gibt; was als Szenario ausdrückbar ist, gehört hierher.

Ein Playwright-Lauf (`apps/web/playwright.config.ts`) startet API (Port 8010) und Web (Port 3010)
mit dem Offline-Modell und einer frischen SQLite-Datei `var/e2e.db`. Laufende Server werden lokal
wiederverwendet (nicht in CI).

| Variable | Bedeutung |
|---|---|
| `E2E_API_PORT` / `E2E_WEB_PORT` | andere Ports |
| `E2E_SERVER_LOGS=1` | Server-Ausgaben anzeigen (Fehlersuche) |

Schritte stehen in `steps.ts`, Fixtures in `fixtures.ts`, gemeinsame Helfer (Barrierefreiheit,
Rückfragen des Briefs) in `../support/`. Das Offline-Modell versteht nur einfache Formulierungen,
siehe `apps/api/tests/bdd/README.md`.
