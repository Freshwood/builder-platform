# ADR-0006: Token-Budget, Modell-Routing und nachvollziehbare Prompts

- Status: akzeptiert
- Datum: 2026-10-07
- Review: [docs/reviews/2026-10-07-code-review.md](../../reviews/2026-10-07-code-review.md)

## Kontext

Ein Projekt zu erstellen war langsam und teuer. Die Offline-Messung (`task bench`) zeigt die
Ursachen:

- Jeder Model-Request trug einen festen Präfix von ~11.800 Tokens: System-Prompt plus 12
  Tool-Definitionen. Das `AssemblyDesign`-Schema war darin doppelt enthalten
  (`design_project` und `redesign_project`).
- Bei einfachen Turns machte dieser Präfix 94 % der Eingabe aus.
- Innerhalb eines Turns ging bei jeder Reparaturrunde der gesamte Verlauf erneut mit: alle
  früheren Entwürfe, der Materialkatalog (8K Zeichen JSON) und jede Projektzusammenfassung inkl.
  Stückliste.
- Über mehrere Turns schickte der Browser den kompletten Chat mit allen Tool-Ein- und -Ausgaben
  bei jeder Nachricht erneut.
- Ein einziges Modell erledigte alles, von „50 cm breiter“ bis zum freien Möbelentwurf.
- Prompt-Änderungen waren nur über ein manuell gepflegtes `PROMPT_VERSION` nachvollziehbar.
  Tool-Beschreibungen und Schemas, die ebenfalls Prompt sind, waren nicht versioniert.

## Entscheidung

1. **Token-Budget als Test.**
   - `modules/agent/bench.py` spielt fünf feste Szenarien durch die echten Tools und die Engine
     und misst jeden Request offline.
   - `tests/test_token_budget.py` setzt Obergrenzen. Eine Regression fällt in CI auf.
2. **Kleiner, stabiler Präfix.**
   - Ein einziges Design-Tool (`save_design`).
   - Die Ausdrucks-Syntax steht einmal im Schema statt 11-mal.
   - Kompakter System-Prompt als Datei.
   - Der Präfix ist byte-stabil (Test), damit Provider-Prompt-Caching greift.
   - Für OpenRouter werden explizite Cache-Punkte gesetzt (Anthropic, Gemini).
3. **Kompakte Historie.**
   - Ein History-Processor kürzt frühere Turns: Entwurfs-Argumente, Katalog- und
     Vorlagen-Abfragen sowie Reasoning werden durch Stubs ersetzt.
   - Im laufenden Turn bleibt nur der jeweils letzte Entwurf vollständig.
   - Jeder Entwurf bleibt in `agent_runs.design_attempts` vollständig erhalten.
4. **Serverseitige Historie.**
   - Der Browser sendet nur die neue Nachricht.
   - Die Historie kommt aus den gespeicherten `agent_runs.model_messages` (vertrauenswürdig,
     keine vom Client eingeschleusten Tool-Ergebnisse).
5. **Modell-Routing pro Turn** (`modules/agent/routing.py`).
   - Deterministisch, ohne zusätzlichen LLM-Call.
   - Freie Entwürfe und strukturelle Änderungen gehen an `LLM_MODEL` (Designer).
   - Vorlagen, Parameter-, Preis- und Variantenänderungen, Undo und Fragen gehen an
     `LLM_MODEL_FAST`, falls gesetzt.
   - Das Fast-Modell fällt bei Provider-Fehlern auf den Designer zurück (`FallbackModel`).
   - Im Zweifel wird der Designer genommen.
6. **Prompt-Provenienz.**
   - Ein Fingerprint über Instructions, alle Tool-Definitionen und die Routing-Version wird mit
     jedem Lauf gespeichert, zusammen mit Rolle, Routing-Grund, Dauer und Usage pro Request
     (auch bei Fehlschlägen).
   - `prompts/prompt.lock`, ein Snapshot-Test und `docs/ai/PROMPT_CHANGELOG.md` erzwingen, dass
     jede Prompt-Änderung eine neue Version und einen Changelog-Eintrag bekommt.

## Konsequenzen

- Gemessen sinkt der Input über die 5 Szenarien um 46 % (212K → 115K Tokens). Folge-Turns
  brauchen weniger als die Hälfte. Details stehen in `docs/ai/benchmarks/`.
- **Modellwahl ist eine Kosten-/Qualitätsfrage, keine reine Geschwindigkeitsfrage.**
  - Mit den Listenpreisen vom 2026-10-07 (`docs/ai/models.json`) ist das aktuelle Modell Solar
    Pro 4 das günstigste der verglichenen Modelle.
  - Ein „Flash“-Modell für einfache Turns würde Kosten **erhöhen**.
  - Sinnvoll ist Routing nur umgekehrt: Solar für Routine-Turns, ein stärkeres Modell als
    Designer, wenn es Reparaturrunden spart. Das ist eine Hypothese, die ein Live-Lauf belegen
    muss (`docs/ai/README.md`).
- Ohne `LLM_MODEL_FAST` ändert sich nichts am Verhalten (ein Modell für alles).
- Alte Chats mit `design_project`/`redesign_project` funktionieren weiter. History-Processor und
  UI kennen beide Namen.
