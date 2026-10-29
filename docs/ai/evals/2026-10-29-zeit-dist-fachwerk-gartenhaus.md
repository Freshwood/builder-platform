# Live eval: dist-fachwerk_gartenhaus

- Date: 2026-10-29
- Prompt: `2026-10-29.1` (fingerprint `51ed6d86ec4a9c8b`, routing 2)
- Models: designer `openai/gpt-5.6-luna`, fast `openai/gpt-5.6-luna`, roles routed
- Runs per brief: 2, request limit 12, token limit 1000000, temperature 0.2, reasoning low

Overall: **0/2 runs succeeded (0%)**, 0/1 briefs in every run, mean 3.0 attempts (3.0 rejected), cost 0.0082 USD.

| Brief | Class | Budget | Success | Rate | pass any | pass all | Attempts | Rejected | Requests | Intent viol. | View viol. | Cost USD | Time s |
|---|---|---|---:|---:|:-:|:-:|---:|---:|---:|---:|---:|---:|---:|
| fachwerk_gartenhaus | slow_design | heavy 90 s | 0/2 | 0% | no | no | 3.0 | 3.0 | 4.0 | 0 | 0 | 0.0082 | 83.331 |

## Failed runs

### fachwerk_gartenhaus run 1 (openai/gpt-5.6-luna, accepted: no, attempts 2, outcomes {"invalid_args": 1, "engine_rejected": 1})
- Final text: 'Die automatische Planung ist an einem technischen Fehler bei zwei Dach-/Wandriegeln gescheitert: Ihre Querschnittsmaße wurden mit der Bauteillänge verwechselt. Bitte starte die Planung mit denselben Angaben erneut; der Fehler lässt sich im nächsten Entwurf korrigieren.'

### fachwerk_gartenhaus run 2 (openai/gpt-5.6-luna, accepted: no, attempts 4, outcomes {"invalid_args": 1, "engine_rejected": 2, "plan_limit": 1})
- Final text: 'Der automatische Entwurf konnte wegen widersprüchlicher Dachmaterial-Vorgaben nicht erstellt werden. Für ein bewohnbares Gartenhaus müssen außerdem **Statik, Gründung und Dachaufbau** durch einen Tragwerksplaner geprüft werden; je nach Bundesland und Größe kann eine Baugenehmigung erforderlich sein.'


22 request(s) ran on a model that is not in `docs/ai/models.json`: their cost is missing from the totals.
