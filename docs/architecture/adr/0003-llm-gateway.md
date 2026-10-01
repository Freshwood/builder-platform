# ADR-0003: Provider-agnostischer LLM-Zugang über eine OpenAI-kompatible API

- Status: akzeptiert
- Datum: 2026-10-01

## Kontext

Je nach Umgebung und Datenschutzanforderung kommen unterschiedliche LLM-Anbieter in Frage: OpenRouter,
LiteLLM-Proxy, Mistral, Azure OpenAI EU Data Zone, STACKIT, Scaleway, Ollama oder vLLM. Zu beachten:

- OpenRouter bietet einen AV-Vertrag und EU-Routing nur im Enterprise- bzw. Business-Tarif.
- LiteLLM hatte im März 2026 einen Supply-Chain-Vorfall: kompromittierte PyPI-Releases 1.82.7 und 1.82.8.

## Entscheidung

- Als Agent-Framework dient **Pydantic AI** mit `OpenAIChatModel` und frei konfigurierbarer Base-URL.
- Die Konfiguration erfolgt ausschließlich über Umgebungsvariablen:
  - `LLM_MODE` = `test` | `openai`
  - `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
- LiteLLM wird **nicht als Python-Library** eingebunden. Wenn überhaupt, läuft es als separater
  Proxy-Container mit gepinntem Image-Digest (Compose-Profil `llm-proxy`).
- `LLM_MODE=test` nutzt ein deterministisches `FunctionModel`. Darauf laufen CI, E2E und lokale
  Entwicklung ohne API-Key.
- Für die Produktion gilt die Empfehlung: ein EU-gehosteter Anbieter mit AV-Vertrag und Zero Data
  Retention. Das ist reine Konfiguration, kein Code.

## Konsequenzen

- Der Anbieterwechsel braucht keinen Code-Change.
- Jeder Agent-Lauf protokolliert Modellname und Prompt-Version (Provenance).
