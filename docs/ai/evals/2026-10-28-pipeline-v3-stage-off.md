# Live eval: pipeline-v3-stage-off

- Date: 2026-10-28
- Prompt: `2026-10-28.5` (fingerprint `d1a105f6fbee5b28`, routing 2)
- Models: designer `~deepseek/deepseek-v4-flash-latest`, fast `~deepseek/deepseek-v4-flash-latest`, roles routed
- Runs per brief: 1, request limit 12, token limit 1000000, temperature 0.2, reasoning low

Overall: **0/3 runs succeeded (0%)**, 0/3 briefs in every run, mean 5.0 attempts (5.0 rejected), cost n/a USD.

| Brief | Class | Success | Rate | pass any | pass all | Attempts | Rejected | Requests | Intent viol. | View viol. | Cost USD | Time s |
|---|---|---:|---:|:-:|:-:|---:|---:|---:|---:|---:|---:|---:|
| podium_kids_catwalk | engine_loop | 0/1 | 0% | no | no | 6.0 | 6.0 | 8.0 | 0 | 0 | n/a | 142.521 |
| tonie_cloud_shelf | args_syntax | 0/1 | 0% | no | no | 7.0 | 7.0 | 9.0 | 0 | 0 | n/a | 170.286 |
| window_shutter_reported | intent_mismatch | 0/1 | 0% | no | no | 2.0 | 2.0 | 4.0 | 0 | 0 | n/a | 225.578 |

## Failed runs

### podium_kids_catwalk run 1 (~deepseek/deepseek-v4-flash-latest, accepted: no, attempts 6, outcomes {"engine_rejected": 2, "no_project": 1, "plan_limit": 3})
- Final text: 'Ich habe das Podest jetzt fünfmal entworfen, aber die Planungs-Engine lehnt den Entwurf jedes Mal ab – die Bauteile lassen sich für diese Konstruktion (Kasten/Deck aus Platten oder Bretter mit Rahmen) nicht ohne Überlappungen oder Lücken platzieren. Entweder überlappen das Deck und die Abschlusskant'

### tonie_cloud_shelf run 1 (~deepseek/deepseek-v4-flash-latest, accepted: no, attempts 7, outcomes {"engine_rejected": 2, "use_plan_design": 1, "plan_limit": 3, "no_project": 1})
- Final text: 'Die Engine had mit dem Entwurf weiterhin Probleme – konkret fällt es ihr schwer, die Wolkendecke sauber als oberen Abschluss über die vollen seitlichen Wangen zu setzen, ohne dass sich Bauteile überlappen.\n\nDamit wir vorankommen, hier zwei Wege – sag mir, was dir lieber ist:\n\n1. **Zweistufig bauen:*'

### window_shutter_reported run 1 (~deepseek/deepseek-v4-flash-latest, accepted: no, attempts 2, outcomes {"engine_rejected": 1, "no_project": 1})
- Error: `UnexpectedModelBehavior: Model token limit (12000) exceeded before any response was generated. Increase the `max_tokens` model setting, or simplify the prompt to result in a shorter response that will fit within the limit.`


69 request(s) ran on a model that is not in `docs/ai/models.json`: their cost is missing from the totals.
