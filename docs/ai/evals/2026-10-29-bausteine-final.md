# Live eval: bausteine-final

- Date: 2026-10-29
- Prompt: `2026-10-29.2` (fingerprint `3c4b23056f6e7ccf`, routing 3)
- Models: designer `~deepseek/deepseek-v4-flash-latest`, fast `~deepseek/deepseek-v4-flash-latest`, roles routed
- Runs per brief: 4, request limit 12, token limit 1000000, temperature 0.2, reasoning low

Overall: **21/24 runs succeeded (88%)**, 3/6 briefs in every run, mean 1.708 attempts (0.667 rejected), cost n/a USD.

| Brief | Class | Budget | Success | Rate | pass any | pass all | Attempts | Rejected | Requests | Intent viol. | View viol. | Cost USD | Time s |
|---|---|---|---:|---:|:-:|:-:|---:|---:|---:|---:|---:|---:|---:|
| carport_zwei_autos | slow_design | heavy 90 s | 4/4 | 100% | yes | yes | 1.0 | 0.0 | 2.25 | 0 | 0 | n/a | 14.525 |
| fachwerk_gartenhaus | slow_design | heavy 90 s | 3/4 | 75% | yes | no | 2.25 | 1.5 | 4.0 | 0 | 0 | n/a | 44.3 |
| gartentisch_sechs | slow_design | medium 60 s | 3/4 | 75% | yes | no | 1.25 | 0.0 | 3.0 | 1 | 0 | n/a | 16.75 |
| schuhe_flur | slow_design | medium 60 s | 4/4 | 100% | yes | yes | 1.0 | 0.0 | 2.5 | 0 | 0 | n/a | 14.725 |
| wandregal_gewuerze | slow_design | medium 60 s | 4/4 | 100% | yes | yes | 2.0 | 0.5 | 3.25 | 0 | 0 | n/a | 33.237 |
| zaun_garten | slow_design | heavy 90 s | 3/4 | 75% | yes | no | 2.75 | 2.0 | 4.25 | 0 | 0 | n/a | 51.604 |

## Failed runs

### fachwerk_gartenhaus run 2 (~deepseek/deepseek-v4-flash-latest, accepted: no, attempts 4, outcomes {"engine_rejected": 2, "plan_limit": 2})
- Final text: 'Der Entwurf ist mehrfach nicht gelungen – die Engine kann Tür und Fenster in der Wand nicht sauber platzieren. Damit ich dir ein passendes Fachwerkhaus plane, brauche ich kurz deine Angaben:\n\n- **Grundfläche:** Wie groß soll das Haus sein (z. B. 3 × 3 m)?\n- **Tür und Fenster:** Sollen beide vorne li'

### gartentisch_sechs run 2 (~deepseek/deepseek-v4-flash-latest, accepted: yes, attempts 2, outcomes {"accepted": 2})
- Intent: [use] Nutzung ist 'indoor', gewünscht war 'outdoor'
- Final text: 'Der Entwurf steht jetzt sauber. Hier die Zusammenfassung:\n\n**Gartentisch für sechs Personen – Douglasie**\n- **Maße:** 1800 × 900 × 750 mm (B × T × H)\n- **Bauweise:** Rahmen mit 4 Beinen (70×70 mm) und umlaufenden Zargen (28×80 mm), Platte aus 6 Douglasie-Brettern (28×150 mm) mit Fugen\n- **Gewicht:**'

### zaun_garten run 4 (~deepseek/deepseek-v4-flash-latest, accepted: no, attempts 8, outcomes {"engine_rejected": 2, "plan_limit": 6})
- Error: `UnexpectedModelBehavior: Model token limit (12000) exceeded before any response was generated. Increase the `max_tokens` model setting, or simplify the prompt to result in a shorter response that will fit within the limit.`
- Too slow: 154.954 s, budget 90 s (heavy)


123 request(s) ran on a model that is not in `docs/ai/models.json`: their cost is missing from the totals.
