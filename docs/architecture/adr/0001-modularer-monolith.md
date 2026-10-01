# ADR-0001: Modularer Monolith mit I/O-freien Kernpaketen

- Status: akzeptiert
- Datum: 2026-10-01

## Kontext

Die Roadmap sieht viele fachliche Bereiche vor (Projekt, Engine, Zeichnungen, Dokumente, Katalog, Agent,
Commerce, Services, BIM). Für Phase I gibt es ein kleines Team und keinen Skalierungsdruck.

## Entscheidung

- Ein Deployment-Artefakt (`apps/api`, FastAPI) mit fachlichen Modulen unter `homeworking.modules.*`.
- Die Domäne (`packages/construction-model`) und die Rechen-Engine (`packages/calc-engine`) sind
  **eigene, I/O-freie Python-Pakete** ohne Abhängigkeit zu FastAPI, Datenbank oder LLM.
- Modulgrenzen werden per `import-linter` in CI geprüft:
  - `construction_model` importiert nichts aus der Plattform.
  - `calc_engine` importiert nur `construction_model`.
  - Kein Modul importiert `homeworking.modules.agent` außer dem API-Layer.
- Ports (Python `Protocol`) und Adapter werden im Composition Root (`bootstrap.py`) verdrahtet.

## Konsequenzen

- Engine und Modell lassen sich isoliert testen und später als Worker oder Bibliothek herauslösen.
- Kein Kubernetes und keine Microservices in Phase I (siehe Roadmap „Bewusst noch nicht“).
