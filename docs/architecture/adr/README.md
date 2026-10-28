# Architekturentscheidungen (ADRs)

Der gültige Gesamtstand steht in [ARCHITEKTUR.md](../ARCHITEKTUR.md). ADRs halten fest, warum
eine Entscheidung so gefallen ist. Neue ADRs werden fortlaufend nummeriert
(`NNNN-titel-in-kebab-case.md`, Deutsch, Abschnitte Kontext · Entscheidung · Konsequenzen) und
anschließend in `ARCHITEKTUR.md` eingearbeitet.

## Gültig

| Nr. | Titel | Datum |
|---|---|---|
| [0009](0009-neuanfang-go-backend-vite-spa.md) | Neuanfang mit Go-Backend, Vite-SPA und BDD-Szenarien | 2026-10-16 |
| [0010](0010-gestufte-entwurfspipeline.md) | Gestufte Entwurfspipeline statt eines großen Aufrufs | 2026-10-28 |

## Archiv (in ARCHITEKTUR.md eingearbeitet)

| Nr. | Titel | Datum | Hinweis |
|---|---|---|---|
| [0001](archiv/0001-modularer-monolith.md) | Modularer Monolith mit I/O-freien Kernpaketen | 2026-10-01 | Stack durch 0009 ersetzt |
| [0002](archiv/0002-projektmodell-und-command-log.md) | Projektmodell als versioniertes Dokument plus Command-Log | 2026-10-01 | „Pack“ durch 0008 entfallen |
| [0003](archiv/0003-llm-gateway.md) | Provider-agnostischer LLM-Zugang | 2026-10-01 | Pydantic AI durch 0009 ersetzt |
| [0004](archiv/0004-freie-entwuerfe-bauteilmodell.md) | Freie Entwürfe über ein parametrisches Bauteilmodell | 2026-10-02 | §5/§6 durch 0008, §7 durch 0007 |
| [0005](archiv/0005-versionen-und-gespeicherte-ki-laeufe.md) | Versionen und gespeicherte KI-Läufe | 2026-10-07 | |
| [0006](archiv/0006-token-budget-und-modell-routing.md) | Token-Budget, Modell-Routing und nachvollziehbare Prompts | 2026-10-07 | §5 durch 0008 §7 |
| [0007](archiv/0007-formen-holzverbindungen-gebaeude.md) | Freie Formen, Stäbe, Holzverbindungen und Gebäude | 2026-10-08 | |
| [0008](archiv/0008-unikate-statt-packs.md) | Jedes Projekt ist ein Unikat | 2026-10-14 | |
