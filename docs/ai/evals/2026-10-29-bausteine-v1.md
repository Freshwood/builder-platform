# Live eval: bausteine-v1

- Date: 2026-10-29
- Prompt: `2026-10-29.1` (fingerprint `51ed6d86ec4a9c8b`, routing 2)
- Models: designer `~deepseek/deepseek-v4-flash-latest`, fast `~deepseek/deepseek-v4-flash-latest`, roles routed
- Runs per brief: 2, request limit 12, token limit 1000000, temperature 0.2, reasoning low

Overall: **4/12 runs succeeded (33%)**, 0/6 briefs in every run, mean 4.25 attempts (3.417 rejected), cost n/a USD.

| Brief | Class | Budget | Success | Rate | pass any | pass all | Attempts | Rejected | Requests | Intent viol. | View viol. | Cost USD | Time s |
|---|---|---|---:|---:|:-:|:-:|---:|---:|---:|---:|---:|---:|---:|
| carport_zwei_autos | slow_design | heavy 90 s | 0/2 | 0% | no | no | 7.5 | 7.5 | 8.0 | 0 | 0 | n/a | 126.014 |
| fachwerk_gartenhaus | slow_design | heavy 90 s | 1/2 | 50% | yes | no | 6.5 | 6.0 | 8.0 | 0 | 0 | n/a | 139.726 |
| gartentisch_sechs | slow_design | medium 60 s | 0/2 | 0% | no | no | 1.5 | 1.5 | 3.5 | 0 | 0 | n/a | 53.804 |
| schuhe_flur | slow_design | medium 60 s | 1/2 | 50% | yes | no | 2.0 | 0.5 | 4.0 | 0 | 0 | n/a | 76.891 |
| wandregal_gewuerze | slow_design | medium 60 s | 1/2 | 50% | yes | no | 3.5 | 1.5 | 5.0 | 1 | 0 | n/a | 52.264 |
| zaun_garten | slow_design | heavy 90 s | 1/2 | 50% | yes | no | 4.5 | 3.5 | 7.0 | 0 | 0 | n/a | 95.31 |

## Failed runs

### carport_zwei_autos run 1 (~deepseek/deepseek-v4-flash-latest, accepted: no, attempts 12, outcomes {"engine_rejected": 2, "plan_limit": 9, "use_plan_design": 1})
- Error: `UsageLimitExceeded: The next request would exceed the request_limit of 12. Consider raising the limit, or see the docs on usage limits for budget-aware patterns: https://pydantic.dev/docs/ai/core-concepts/agent/#usage-limits`
- Too slow: 161.715 s, budget 90 s (heavy)

### carport_zwei_autos run 2 (~deepseek/deepseek-v4-flash-latest, accepted: no, attempts 3, outcomes {"engine_rejected": 2, "plan_limit": 1})
- Too slow: 90.314 s, budget 90 s (heavy)
- Final text: 'Der Entwurf ist mehrfach nicht gelungen – die Engine kommt bei der großen, offenen Carport-Konstruktion (6000 × 6000 × 2600 mm) an ihre Rechengrenze und bricht ab.\n\nDamit ich dir einen tragfähigen Entwurf liefern kann, bräuchte ich ein paar Anpassungen:\n\n- **Kleinere Maße?** Z. B. 5000 × 5000 mm ode'

### fachwerk_gartenhaus run 2 (~deepseek/deepseek-v4-flash-latest, accepted: no, attempts 11, outcomes {"engine_rejected": 2, "plan_limit": 6, "invalid_args": 2, "use_plan_design": 1})
- Error: `UsageLimitExceeded: The next request would exceed the request_limit of 12. Consider raising the limit, or see the docs on usage limits for budget-aware patterns: https://pydantic.dev/docs/ai/core-concepts/agent/#usage-limits`
- Too slow: 197.141 s, budget 90 s (heavy)

### gartentisch_sechs run 1 (~deepseek/deepseek-v4-flash-latest, accepted: no, attempts 0, outcomes {})
- Error: `UnexpectedModelBehavior: Model token limit (12000) exceeded before any response was generated. Increase the `max_tokens` model setting, or simplify the prompt to result in a shorter response that will fit within the limit.`

### gartentisch_sechs run 2 (~deepseek/deepseek-v4-flash-latest, accepted: no, attempts 3, outcomes {"engine_rejected": 2, "plan_limit": 1})
- Too slow: 62.778 s, budget 60 s (medium)
- Final text: 'Der Entwurf ist leider dreimal in der Berechnung abgebrochen – das passiert, wenn die Konstruktion zu komplex für die Planungs-Engine ist. Das liegt nicht an deinen Angaben, sondern an der internen Berechnung.\n\nDamit es klappt, kann ich ein paar Dinge anpassen. Was passt dir besser?\n\n- **Kleinere Pl'

### schuhe_flur run 1 (~deepseek/deepseek-v4-flash-latest, accepted: yes, attempts 3, outcomes {"accepted": 2, "engine_rejected": 1})
- Too slow: 98.05 s, budget 60 s (medium)
- Final text: 'Fertig! Dein Schuhschrank für den Flur ist geplant:\n\n**Offener Schuhschrank, 1000 × 350 × 500 mm, aus Fichte**\n- Zwei Seitenwangen, dazwischen zwei Böden – einfach und stabil\n- 4 Bauteile, ca. 9 kg, unbehandelt\n- **Materialkosten:** ca. 34–55 € (Einkauf), Verbrauch ca. 18–30 €\n\n**Bau:** Die Böden we'

### wandregal_gewuerze run 1 (~deepseek/deepseek-v4-flash-latest, accepted: yes, attempts 3, outcomes {"accepted": 2, "engine_rejected": 1})
- Intent: [support] Aufstellung ist 'floor', gewünscht war 'wall'
- Final text: 'Dein Gewürzregal ist fertig geplant. Hier die Eckdaten:\n\n**Gewürzregal 60 cm** – 600 × 200 × 500 mm (B × T × H), drei Böden, zur Wandmontage\n- **Material:** Multiplex Birke 18 mm für Seitenteile und Böden, 3 mm HDF-Rückwand\n- **Bauteile:** 6 Teile, ca. 7 kg\n- **Kosten:** ca. 137–212 € Einkauf (Richt'

### zaun_garten run 1 (~deepseek/deepseek-v4-flash-latest, accepted: no, attempts 7, outcomes {"engine_rejected": 2, "plan_limit": 4, "use_plan_design": 1})
- Too slow: 131.115 s, budget 90 s (heavy)
- Final text: 'Die automatische Planung ist leider mehrfach an der Rechenzeit gescheitert – der Zaun mit vielen Einzelbrettern ist für die Engine zu aufwendig, um ihn in einem Durchgang zu entwerfen.\n\nDamit ich dir trotzdem weiterhelfen kann, ein paar Fragen:\n\n1. **Bauweise:** Soll es ein klassischer **Lattenzaun*'


105 request(s) ran on a model that is not in `docs/ai/models.json`: their cost is missing from the totals.
