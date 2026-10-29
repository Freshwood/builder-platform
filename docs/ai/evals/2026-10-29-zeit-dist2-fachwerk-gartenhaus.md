# Live eval: dist2-fachwerk_gartenhaus

- Date: 2026-10-29
- Prompt: `2026-10-29.1` (fingerprint `51ed6d86ec4a9c8b`, routing 2)
- Models: designer `openai/gpt-5.6-luna`, fast `openai/gpt-5.6-luna`, roles routed
- Runs per brief: 3, request limit 12, token limit 1000000, temperature 0.2, reasoning low

Overall: **0/3 runs succeeded (0%)**, 0/1 briefs in every run, mean 2.333 attempts (2.333 rejected), cost 0.0141 USD.

| Brief | Class | Budget | Success | Rate | pass any | pass all | Attempts | Rejected | Requests | Intent viol. | View viol. | Cost USD | Time s |
|---|---|---|---:|---:|:-:|:-:|---:|---:|---:|---:|---:|---:|---:|
| fachwerk_gartenhaus | slow_design | heavy 90 s | 0/3 | 0% | no | no | 2.333 | 2.333 | 3.333 | 0 | 0 | 0.0141 | 86.979 |

## Failed runs

### fachwerk_gartenhaus run 1 (openai/gpt-5.6-luna, accepted: no, attempts 2, outcomes {"engine_rejected": 2})
- Final text: 'Der Entwurf konnte wegen einer technischen Zeitüberschreitung nicht erstellt werden. Die Planung wäre weiterhin:\n\n- ungefähr **4.000 × 3.000 mm** Grundfläche\n- Douglasien-Fachwerk mit einfachem Satteldach\n- Eingangstür und zu öffnendes Fenster\n- Nutzung nur als sommerlicher Schlafraum\n- Außenlasur a'

### fachwerk_gartenhaus run 2 (openai/gpt-5.6-luna, accepted: no, attempts 3, outcomes {"invalid_args": 1, "engine_rejected": 2})
- Final text: 'Die automatische Planung ist zweimal an technischen Problemen gescheitert: zuerst an kollidierenden Rahmen- und Öffnungsteilen, danach am Zeitlimit der komplexen Fachwerkberechnung.\n\nIch kann es erneut mit einer vereinfachten Konstruktion versuchen: rechteckiger Holzrahmen mit sichtbaren diagonalen '

### fachwerk_gartenhaus run 3 (openai/gpt-5.6-luna, accepted: no, attempts 2, outcomes {"engine_rejected": 2})
- Final text: 'Die automatische Gebäudeplanung ist an mehreren sich überschneidenden Bauteilen gescheitert. Für ein Fachwerkhaus müssen Pfosten, Rähme, Tür-/Fensteröffnungen und Dachanschlüsse konstruktiv sauber abgestimmt werden.\n\nIch kann den Entwurf mit vereinfachter Konstruktion erneut anlegen, zum Beispiel mi'


30 request(s) ran on a model that is not in `docs/ai/models.json`: their cost is missing from the totals.
