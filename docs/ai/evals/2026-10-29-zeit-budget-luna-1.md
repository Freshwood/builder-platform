# Live eval: budget-luna-1

- Date: 2026-10-29
- Prompt: `2026-10-29.1` (fingerprint `51ed6d86ec4a9c8b`, routing 2)
- Models: designer `openai/gpt-5.6-luna`, fast `openai/gpt-5.6-luna`, roles routed
- Runs per brief: 1, request limit 12, token limit 1000000, temperature 0.2, reasoning low

Overall: **0/2 runs succeeded (0%)**, 0/2 briefs in every run, mean 2.0 attempts (2.0 rejected), cost 0.0065 USD.

| Brief | Class | Budget | Success | Rate | pass any | pass all | Attempts | Rejected | Requests | Intent viol. | View viol. | Cost USD | Time s |
|---|---|---|---:|---:|:-:|:-:|---:|---:|---:|---:|---:|---:|---:|
| fachwerk_gartenhaus | slow_design | heavy 90 s | 0/1 | 0% | no | no | 2.0 | 2.0 | 3.0 | 0 | 0 | 0.0038 | 91.715 |
| schuhe_flur | slow_design | medium 60 s | 0/1 | 0% | no | no | 2.0 | 2.0 | 3.0 | 0 | 0 | 0.0027 | 56.716 |

## Failed runs

### fachwerk_gartenhaus run 1 (openai/gpt-5.6-luna, accepted: no, attempts 2, outcomes {"engine_rejected": 2})
- Too slow: 91.715 s, budget 90 s (heavy)
- Final text: 'Die Planung ist erneut wegen einer technischen Zeitüberschreitung fehlgeschlagen. Dein Vorhaben ist grundsätzlich planbar; ich kann es mit vereinfachten Angaben erneut versuchen, zum Beispiel zunächst als kleines Gartenhaus mit Holzrahmen und Satteldach.\n\nFür ein bewohnbares Gebäude müssen Statik, F'

### schuhe_flur run 1 (openai/gpt-5.6-luna, accepted: no, attempts 2, outcomes {"engine_rejected": 2})
- Final text: 'Die Planung konnte wegen einer technischen Zeitüberschreitung nicht abgeschlossen werden. Bitte versuche es noch einmal; ich plane dann dasselbe Schuhregal erneut mit den bisherigen Annahmen.'


13 request(s) ran on a model that is not in `docs/ai/models.json`: their cost is missing from the totals.
