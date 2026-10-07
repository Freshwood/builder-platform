# Code-Review 2026-10-07: Token-Verbrauch, Modellwahl, UI-Performance, AI-first

Umsetzung und Entscheidungen: [ADR-0006](../architecture/adr/0006-token-budget-und-modell-routing.md).
Jede Aussage unten ist durch einen Test oder eine reproduzierbare Messung belegt (Spalte „Beleg“).
Gemessen wird offline und deterministisch mit `task bench`, ohne API-Kosten. Die Tokenzahlen sind
Schätzungen (Zeichen / 3,2). Die Differenzen zwischen zwei Messungen sind exakt.

## 1. Warum das Erzeugen eines Projekts so viele Tokens brauchte

| # | Befund | Ort | Beleg |
|---|---|---|---|
| T1 | Jeder Model-Request trug einen festen Präfix von **11.839 Tokens**. Bei einfachen Turns waren das 94 % der Eingabe. | `prompts.py`, `tools.py` | `docs/ai/benchmarks/2026-10-07-baseline.md` |
| T2 | Das `AssemblyDesign`-JSON-Schema war **zweimal** in jedem Request: in `design_project` (3.279 Tok) und in `redesign_project` (2.969 Tok). | `tools.py` | Baseline, Tool-Tabelle |
| T3 | Die Beschreibung der Ausdrucks-Syntax stand **11-mal** im Schema (2,7K Zeichen). | `construction_model/assembly.py` | Schemagröße 9.640 → 7.105 Zeichen |
| T4 | `list_materials` lieferte 8,3K Zeichen JSON. Das Ergebnis blieb im Verlauf und ging bei jedem weiteren Request mit. | `tools.py` | Tabelle jetzt 4,2K |
| T5 | Jedes Create/Change-Ergebnis enthielt die komplette Stückliste. | `project_summary` | — |
| T6 | Jede Reparaturrunde schickte **alle** früheren Entwürfe erneut mit. Das Wachstum innerhalb eines Turns ist quadratisch. | Agent-Loop | `test_history.py` |
| T7 | Der Browser schickte bei jeder Nachricht den **ganzen Chat** inkl. Tool-Ein- und -Ausgaben. Folge-Turns wurden dadurch immer teurer (40–42K Tokens für „20 cm breiter“). | `assistant.ts`, `chat.py` | Baseline `followup_*` |
| T8 | Es gab kein `max_tokens`, keine `temperature` und keine Cache-Punkte für Prompt-Caching. | `model.py` | — |

**Nachher** (`docs/ai/benchmarks/2026-10-07-phase1.md`, gleiche Szenarien):

| Szenario | Input vorher | Input nachher | Δ |
|---|---:|---:|---:|
| Pack-Projekt | 25.187 | 15.421 | −39 % |
| Vorlagen-Projekt | 24.917 | 15.298 | −39 % |
| Freier Entwurf, 2 Reparaturen | 79.728 | 48.733 | −39 % |
| Folge-Turn 1 | 39.998 | 17.186 | −57 % |
| Folge-Turn 2 | 42.239 | 18.693 | −56 % |
| **Summe** | **212.069** | **115.331** | **−46 %** |
| Fester Präfix pro Request | 11.839 | 7.213 | −39 % |

Tests, die das absichern:

- `test_token_budget.py` setzt Obergrenzen pro Szenario und Request auf den neuen Stand und
  prüft, dass der Präfix byte-stabil ist (Voraussetzung für Prompt-Caching).
- `test_history.py` prüft die Kürzung früherer Turns und ersetzter Entwürfe.
- `test_conversations.py` prüft die serverseitige Historie.

Zur Laufzeit kommt noch Prompt-Caching hinzu. Explizite Cache-Punkte werden für OpenRouter
gesetzt, OpenAI-artige Provider cachen automatisch. Der Präfix wird dann nur noch zum
Cache-Preis abgerechnet; bei Solar ist das 1/5 des Input-Preises.

Geschwindigkeit: Weniger Input-Tokens verkürzen die Zeit bis zum ersten Token jedes Requests.
Ein freier Entwurf hat 5 Requests, also ist der Effekt dort am größten. Absolute Latenzen lassen
sich offline nicht messen; siehe Abschnitt 2.

## 2. Mehrere Modelle: lohnt sich das?

Gerechnet wurde mit den offline gemessenen Tokens und den Listenpreisen von OpenRouter vom
2026-10-07 (`docs/ai/models.json`). Angegeben sind US-Cent pro Szenario, das Präfix wird nach
dem ersten Request gecacht:

| Konfiguration | Summe vorher | Summe nachher | +1 Reparaturrunde |
|---|---:|---:|---:|
| nur Solar Pro 4 (heute) | 1,379 | **0,775** | 0,081 |
| nur GPT-5.6 Luna | 3,045 | 1,776 | 0,208 |
| nur Gemini 3.8 Flash | 11,100 | 6,341 | 0,701 |
| Routing: Designer Gemini Flash, sonst Solar | 4,915 | 3,380 | 0,701 |
| Routing: Designer Luna, sonst Solar | 2,025 | 1,279 | 0,208 |

Was das zeigt:

1. **Ein „Flash“-Modell für einfache Turns spart nichts, es kostet mehr.** Solar Pro 4 ist bereits
   das günstigste der verglichenen Modelle. Gemini 3.8 Flash kostet pro Token etwa 8- bis 10-mal
   so viel.
2. Mehrere Modelle lohnen sich nur in umgekehrter Rolle. Solar bleibt für Routine-Turns
   (Vorlagen, Maße, Preise, Fragen). Ein stärkeres Modell übernimmt als Designer die freien
   Entwürfe, aber nur, **wenn** es dabei Reparaturrunden spart.
   - Beispiel Luna: Pro freiem Entwurf kostet sie rund 0,5 Cent mehr als Solar, eine
     Solar-Reparaturrunde kostet 0,08 Cent. Bei den Kosten gleicht Luna das also nicht aus.
   - Gewinnen kann der stärkere Designer bei **Qualität und Durchlaufzeit**: Jede eingesparte
     Runde spart einen kompletten Request plus Wartezeit, und das 200K-Token-Limit wird seltener
     erreicht.
3. **Hypothese, offline nicht belegbar:** dass ein stärkeres Modell weniger Reparaturen und
   bessere Entwürfe liefert, und wie schnell die Modelle antworten. Dafür gibt es eine Anleitung
   für einen Live-Vergleich (`docs/ai/README.md`, SQL über `agent_runs`). Jeder Lauf speichert
   dafür jetzt Rolle, Routing-Grund, Dauer, Tokens pro Request und das tatsächlich genutzte
   Modell.

Umgesetzt ist das Routing konfigurierbar: `LLM_MODEL` ist der Designer, `LLM_MODEL_FAST` ist
optional. Ohne `LLM_MODEL_FAST` bleibt alles wie bisher.

- **Empfehlung auf Basis der Daten:** heute nichts umstellen. Für einen Test
  `LLM_MODEL=<Kandidat>` und `LLM_MODEL_FAST=upstage/solar-pro4` setzen und den Live-Vergleich
  laufen lassen.
- **Belege:** `test_routing.py` (14 Fälle Nachricht → Rolle) und
  `test_agent_run_stores_provenance`.

## 3. UI- und Backend-Performance

| # | Befund | Schwere | Status | Beleg |
|---|---|---|---|---|
| U1 | Jeder Stream-Chunk renderte den ganzen Workspace inkl. Projektpanel neu. | hoch | `ProjectPanel` memoisiert, `useChat({ throttle: 50 })` | — |
| U2 | Alle Zeichnungs-`<img>` wurden gemountet. Browser laden auch versteckte Bilder, also gab es N SVG-Requests, jeder mit Engine-Arbeit auf dem Server, selbst bei sichtbarem 3D-Modell. | hoch | Nur die sichtbare Zeichnung, nur im Plan-Modus | E2E `raised-bed.spec.ts` zählt die Requests (genau 1 Pfad) |
| U3 | Alle Tabs (Stückliste mit Preis-Editoren, Zuschnitt, Bauanleitung) wurden gerendert und nur versteckt. | hoch | Nur der aktive Tab wird gerendert | E2E |
| U4 | Jede Chatnachricht wurde bei jedem Chunk neu geparst. Der Smooth-Scroll startete pro Token neu (Ruckeln). | mittel | Memoisierte `MessageItem`; Smooth-Scroll nur bei neuer Nachricht, sonst sofort und nur, wenn der Nutzer unten ist | — |
| U5 | Der Strg+Z-Listener wurde bei jedem Render neu registriert. | niedrig | Abhängig nur von der stabilen `mutate`-Funktion | — |
| U6 | `Intl`-Formatter wurden pro Aufruf (pro Tabellenzelle) neu erzeugt. | niedrig | Einmal erzeugt | — |
| U7 | **Fehler:** Ein Umbau ohne Parameteränderung ließ die Zeichnungs-URL gleich, also wurde eine veraltete Zeichnung angezeigt. | mittel | URL-Version = Position im Command-Log (`ProjectView.seq`) | `test_performance.py` |
| B1 | `engine.build` und `render_svg` blockierten den Event-Loop und damit auch die Chat-Streams anderer Nutzer. | hoch | Läuft im Worker-Thread (`ProjectService._build`, `run_in_threadpool`) | — |
| B2 | Ältere Versionen wurden bei **jedem** SVG-Request komplett aus dem Log neu berechnet. | hoch | LRU-Cache `(project, seq)`, append-only, also immer gültig; SVG mit `?seq=` ist `immutable` | `test_performance.py` |
| B3 | Projektantworten enthielten die Zeichnungs-Primitives (25–35 % des JSON), die kein Client nutzt. | mittel | `response_model_exclude` | `test_project_view_has_no_drawing_primitives` |
| B4 | Keine Kompression. | mittel | GZip ab 1 KB; SSE-Chat-Stream ausgenommen | `test_json_is_compressed_but_the_chat_stream_is_not` |
| B5 | Kein Logging-Setup, `agent_turn` ging verloren. | mittel | JSON-Logs mit allen `extra`-Feldern, neues `agent_turn_done` (Tokens, Dauer) | `test_log_lines_carry_extra_fields` |

**Offen (bewusst nicht umgesetzt):**

- React Compiler. Er braucht eine neue Babel-Abhängigkeit, und Babel verlangsamt den ohnehin
  langsamen `next dev` auf /mnt/c. Die gezielte Memoisierung deckt den Hauptfall ab.
- `can_undo` lädt weiter das ganze Command-Log. Das ist korrekt, aber linear in der
  Historienlänge. Lohnt sich erst bei langen Historien; dann `max(seq)` plus ein gespeichertes
  `can_undo`.
- Keine Paginierung für `/projects` und `/versions`.

## 4. AI-first und Nachvollziehbarkeit

| Vorher | Nachher |
|---|---|
| Kein `CLAUDE.md`/`AGENTS.md` im Root. | `AGENTS.md` (Layout, Befehle, Regeln), `CLAUDE.md` → `@AGENTS.md`, `CONTRIBUTING.md` |
| Prompt als Python-String; nur ein manuell gepflegtes `PROMPT_VERSION`. | `prompts/system.de.md` plus Fingerprint über Prompt, alle Tool-Definitionen und Routing. `prompt.lock` und Snapshot zeigen jede Änderung im Diff. |
| Tool-Beschreibungen und Schemas unversioniert. | Im Fingerprint und Snapshot enthalten |
| Kein Prompt-Changelog. | `docs/ai/PROMPT_CHANGELOG.md`, rückwirkend mit allen Versionen aus Git |
| `agent_runs` ohne Latenz und ohne Tokens bei Fehlschlag. | Migration 0003: `prompt_fingerprint`, `safety_rules_version`, `model_role`, `routing_reason`, `duration_ms`; Usage pro Request inkl. aufgelöstem Modell, auch bei Fehlschlag |
| `.claude/` nur mit einem Worktree, nicht ignoriert. | `.claude/settings.json` (Allowlist, `.env` gesperrt), Skills `prompt-change` und `token-bench`, Worktrees und lokale Settings ignoriert |
| Kein PR-Template. | Checkliste für Prompt- und Agent-Änderungen inkl. Token-Delta |
| Pre-commit ohne Architektur- und Prompt-Checks. | `lint-imports` und `prompt-lock` als Hooks |
| ADR-0005 verlinkte eine gelöschte Datei. | Aus Git wiederhergestellt nach `docs/problems/archiv/versioning.md` |

Belege:

- `test_prompt_lock.py`: Gegenprobe gemacht. Eine zusätzliche Prompt-Zeile macht den Test rot,
  und `task prompt:lock` verweigert das Update ohne neue Version.
- `test_agent_run_stores_provenance`.

**Offen:**

- `CODEOWNERS` für `modules/agent/prompts/` braucht die GitHub-Handles des Teams.
- Die Commit-Historie („Fix another bug“): ab jetzt Conventional Commits mit den Scopes `prompt`
  und `agent` (`CONTRIBUTING.md`).

## 5. Verhaltensänderungen, die man kennen sollte

- `design_project` und `redesign_project` heißen jetzt `save_design`. Gespeicherte Chats mit den
  alten Namen funktionieren weiter: Der History-Processor und die UI-Aktivitätsanzeige kennen
  beide.
- `ProjectView` hat jetzt `seq`. Der TS-Client ist neu generiert, `primitives` ist dort optional.
- Gekürzte Entwürfe erscheinen auch in den gespeicherten `model_messages`. Vollständig liegen sie
  in `design_attempts`.
- `task e2e` löscht `var/e2e.db` vor jedem Lauf. Eine alte Datei ohne die neuen Spalten ließ den
  Reload-Test scheitern.
