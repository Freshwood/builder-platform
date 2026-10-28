# Live eval: pipeline-v4-diag

- Date: 2026-10-28
- Prompt: `2026-10-28.5` (fingerprint `d1a105f6fbee5b28`, routing 2)
- Models: designer `~deepseek/deepseek-v4-flash-latest`, fast `~deepseek/deepseek-v4-flash-latest`, roles routed
- Runs per brief: 1, request limit 12, token limit 1000000, temperature 0.2, reasoning low

Overall: **0/1 runs succeeded (0%)**, 0/1 briefs in every run, mean 6.0 attempts (6.0 rejected), cost n/a USD.

| Brief | Class | Success | Rate | pass any | pass all | Attempts | Rejected | Requests | Intent viol. | View viol. | Cost USD | Time s |
|---|---|---:|---:|:-:|:-:|---:|---:|---:|---:|---:|---:|---:|
| tonie_cloud_shelf | args_syntax | 0/1 | 0% | no | no | 6.0 | 6.0 | 7.0 | 0 | 0 | n/a | 725.699 |

## Failed runs

### tonie_cloud_shelf run 1 (~deepseek/deepseek-v4-flash-latest, accepted: no, attempts 6, outcomes {"engine_rejected": 2, "use_plan_design": 1, "plan_limit": 3})
- Final text: 'Ich muss offen sein: Die Planungsinstanz konnte das Projekt auch in mehreren Vereinfachungen nicht zuverlässig erzeugen (selbst ein schlichtes Rechteckregal schlug fehl). Der Fehler liegt an der automatischen Entwurfserzeugung, nicht an deinen Angaben.\n\nBevor ich weiter probiere, kurz zwei Fragen, d'


9 request(s) ran on a model that is not in `docs/ai/models.json`: their cost is missing from the totals.
