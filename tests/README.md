# Funktionale BDD-Szenarien

Hier steht, **was** Homeworking fachlich können muss. Die Szenarien sind in Gherkin auf Deutsch
geschrieben und laufen mit [playwright-bdd](https://vitalets.github.io/playwright-bdd/).

- `features/backend/*.feature` sprechen nur HTTP mit der API (`/api/...`).
- `features/frontend/*.feature` bedienen die Oberfläche im Browser (Chromium, de-DE).

Die Szenarien kennen keine Implementierungsdetails. Sie liefen zuerst gegen den alten Python- und
Next.js-Stack und gelten unverändert für das Go-Backend und die Vite-SPA (ADR-0009).

## Ausführen

```bash
task check            # alles: backend:check + frontend:check (inkl. dieser Szenarien)
task bdd              # nur die Szenarien, Backend und Frontend
task bdd:backend      # nur API-Szenarien (startet nur das Backend)
task bdd:frontend     # nur Browser-Szenarien
task bdd -- --grep "Regal"   # nach Szenarioname filtern
```

Die Server starten automatisch: Backend auf Port 8010, Frontend auf Port 3010, mit dem
deterministischen Offline-Modell (`LLM_MODE=test`) und einer frischen SQLite-Datei
`var/bdd.db`. Es wird kein API-Schlüssel und kein Netzwerk gebraucht.

| Variable | Bedeutung |
|---|---|
| `BDD_SCOPE` | `backend` startet nur die API, `frontend`/`all` (Standard) beide Server |
| `BDD_BACKEND_CMD` / `BDD_FRONTEND_CMD` | anderer Startbefehl, z. B. ein fertig gebautes Binary |
| `BDD_API_PORT` / `BDD_WEB_PORT` | andere Ports |
| `BDD_DATABASE_URL` | andere Datenbank für das Backend |
| `BDD_SERVER_LOGS=1` | Server-Ausgaben anzeigen (Fehlersuche) |

Laufen schon Server auf den Ports, werden sie lokal wiederverwendet (nicht in CI).

## Ein Szenario hinzufügen

1. Passende Feature-Datei wählen oder neu anlegen, z. B. `features/backend/werkbank.feature`.
   Erste Zeile `# language: de`, dazu das Tag `@backend` bzw. `@frontend`.
2. Vorhandene Schritte wiederverwenden. Sie stehen in `steps/api.steps.ts` (Backend) und
   `steps/ui.steps.ts` (Frontend). Eine Liste aller Schritte zeigt
   `corepack pnpm --filter @homeworking/bdd exec bddgen export`.
3. Fehlt ein Schritt, ihn in der passenden `*.steps.ts` ergänzen, deutsch formuliert. Frontend-
   Schritte beschreiben, was man *sieht* („zeigt …“, „sehe ich …“), Backend-Schritte, was die
   API liefert („lautet …“, „enthält …“).
4. Noch nicht umgesetztes Verhalten mit `@wip` markieren. Solche Szenarien laufen nicht in
   `task check`.

Beispiel:

```gherkin
# language: de
@backend
Funktionalität: Werkbank

  Szenario: Eine Werkbank aus dem Testentwurf anlegen
    Wenn ich ein Projekt aus dem Entwurf "werkbank" anlege
    Dann wird das Projekt angelegt
    Und trägt das Projekt den Hinweis "AI_DRAFT"
    Und enthält die Anleitung den Schritt "Material einkaufen"
```

### Entwürfe als Testdaten

`fixtures/designs/<name>.json` enthält Entwürfe im Format `AssemblyDesign`, so wie die KI sie mit
`save_design` speichern würde. Mit einer Tabelle lassen sich einzelne Werte ändern:

```gherkin
Wenn ich ein Projekt aus dem Entwurf "regal" mit diesen Änderungen anlege:
  | Pfad              | Wert             |
  | parts[0].material | mahagoni_gold_99 |
  | parts[+]          | {"id": "x", ...} |
```

`parts[0].material` setzt einen Wert, `parts[+]` hängt ein Element an. Werte werden als JSON
gelesen, sonst als Text.

### Was das Offline-Modell versteht

Im Testbetrieb ersetzt ein regelbasiertes Modell das Sprachmodell. Es versteht nur einfache
Formulierungen:

| Eingabe | Wirkung |
|---|---|
| „Regal 80 x 30 x 180 cm mit 5 Böden“, „Bücherregal …“ | entwirft ein Regal (`save_design`) |
| „Hochbeet 2 × 1 m, 80 cm hoch, aus Lärche“ | entwirft ein Hochbeet |
| „Hochbeet“ ohne Maße | fragt nach den Maßen |
| „20 cm breiter / schmaler / länger / kürzer / höher / niedriger“ | `change_parameter_by` |
| „rückgängig“ | `undo_last_change` |
| „… Variante günstig / langlebig / Komfort“ | `select_variant` |
| „Lärche“, „Douglasie“, „Fichte“ | Holzart setzen |

Die Sicherheitsverweise (Elektro, Gas/Feuerstätten, tragende Bauteile, Schadstoffe) kommen nicht
vom Modell, sondern vom Sicherheits-Gate. Sie funktionieren mit jedem Modell.
