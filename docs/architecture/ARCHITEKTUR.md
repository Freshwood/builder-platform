# Homeworking – Architektur (gültiger Stand)

- Stand: 2026-10-16
- Fasst die Entscheidungen [ADR-0001 bis ADR-0008](adr/archiv/) zusammen und ergänzt sie um
  [ADR-0009](adr/0009-neuanfang-go-backend-vite-spa.md) (Neuanfang mit Go-Backend und Vite-SPA).
- Dieses Dokument ist die verbindliche Beschreibung. Die archivierten ADRs erklären nur noch,
  *wie* es dazu kam. Neue Entscheidungen werden als ADR ab 0010 geschrieben und hier eingearbeitet.

Veraltetes aus den alten ADRs ist hier bewusst weggelassen: Construction Packs, Vorlagen,
Vertrauensstufen (`trust`), die Werkzeuge `create_project`, `create_from_template`,
`design_project`/`redesign_project` und der Python-/Next.js-Stack.

---

## 1. Leitprinzip: Das LLM entwirft, die Engine rechnet

Homeworking macht aus einer Beschreibung eines Heimwerkerprojekts ein berechenbares Bauprojekt.

- Das Sprachmodell **beschreibt** Bauteile in einem parametrischen Entwurf (`AssemblyDesign`).
- Die **deterministische Engine** prüft den Entwurf und leitet alles andere ab: Stückliste,
  Zuschnitt, Kosten, Gewicht, Zeichnungen, Anleitung und 3D-Modell.
- **Das LLM rechnet nie.** Zahlen, die ein Sprachmodell frei erzeugt, sind nicht maßhaltig, nicht
  reproduzierbar und passen nicht zur Stückliste. Neue Kennzahlen gehören in die Engine, der Agent
  gibt sie nur weiter.
- **Jedes Projekt ist ein Unikat** (ADR-0008). Es gibt keine Packs und keine Vorlagen. Die KI
  entwirft jedes Projekt selbst genau nach der Angabe des Kunden. Jeder Entwurf trägt den Hinweis
  „KI-Entwurf“ (Transparenz nach Art. 50 KI-Verordnung).

## 2. Modularer Monolith mit I/O-freiem Kern (ADR-0001, ADR-0009)

- **Ein Deployment-Artefakt:** ein Go-Binary (`backend/cmd/homeworking`). Es liefert die API unter
  `/api` und in Produktion auch die gebaute SPA aus (`go:embed`), sodass kein Reverse-Proxy nötig ist.
- **Fachmodule** unter `backend/internal/modules/*`: `projects`, `conversations`, `identity`,
  `drawings`, `documents`, `compliance`, `agent`.
- **I/O-freier Kern:**
  - `backend/internal/model` ist die Domäne (Eingaben, Commands, Diff, `AssemblyDesign`,
    Zeichnungs-IR).
  - `backend/internal/engine` ist die Rechen-Engine (Prüfung, Geometrie, Ableitung, Katalog).
  - Beide kennen weder HTTP noch Datenbank noch LLM.
- **Modulgrenzen** werden geprüft (`depguard` in golangci-lint, Teil von `task backend:check`):
  - `model` importiert nur die Standardbibliothek und `decimal`.
  - `engine` importiert nur `model`.
  - `modules/agent` wird nur von der HTTP-Schicht importiert.
- **Ports** sind Go-Interfaces im jeweiligen Modul. Adapter werden im Composition Root
  (`backend/internal/app`) verdrahtet.
- Keine Microservices und kein Kubernetes in Phase I.

## 3. Projektmodell: Eingaben plus Command-Log (ADR-0002, ADR-0008)

1. **Eingabe und Ableitung sind getrennt.**
   - Gespeichert werden nur die *Eingaben* (`ProjectInputs`): der Entwurf (`design`, Pflicht),
     Parameterwerte, die gewählte Variante, Name, Region, eigene Preise und Notizen.
   - Das *Ergebnis* (`ConstructionResult`: Bauteile, Stückliste, Zuschnitt, Kosten, Zeichnungen,
     Anleitung, 3D-Daten) erzeugt die Engine bei jeder Änderung neu, mit Versionsangaben
     (`Provenance.engine_version`, `design_version`).
2. **Speicherung:** `projects.model` als JSON (Postgres: JSONB) mit `schema_version` (aktuell 2).
   Ältere Schemata werden beim Lesen per Upcaster angehoben. Nutzer und Projekte liegen in
   normalisierten Tabellen.
3. **Änderungen nur über typisierte Commands** (diskriminierte Union über `type`):
   `create_project`, `set_parameters`, `change_parameter_by`, `select_variant`, `rename`,
   `set_region`, `add_note`, `replace_design`, `set_price`, `replace_inputs`, `undo`.
   - Jede Ausführung schreibt einen append-only Eintrag in `project_commands`: `seq`, `command`,
     `actor` (user/agent), `llm_trace_id`, `engine_version`, `design_version` und `diff`.
   - Das LLM kann das Modell nie direkt beschreiben, es schlägt nur Commands über Werkzeuge vor.
4. **Undo** ist selbst ein Command (Stapel-Semantik in `effective_commands`). Der Zustand entsteht
   per Replay, was nur geht, weil die Engine deterministisch ist.
5. **Bauteile** tragen eine stabile ID und einen IFC-nahen Typ (`IfcMember`, `IfcPlate`,
   `IfcCovering`, `IfcMechanicalFastener` …). Ein späterer IFC-Export ist damit nur ein Adapter.
6. Integritätsregeln liegen in der Validierung und in den Tests, nicht in DB-Constraints.

## 4. Versionen und gespeicherte KI-Läufe (ADR-0005)

1. **Jeder Log-Eintrag ist eine Version.** `GET /api/projects/{id}/versions` liefert Bezeichnung,
   Akteur, Zeitpunkt und Materialkosten. `GET /api/projects/{id}/versions/{seq}` rekonstruiert
   den Stand per Replay. Zeichnungen und PDF akzeptieren `?seq=`.
2. **Wiederherstellen hängt an, statt zu löschen.** `replace_inputs` trägt die vollständigen
   Eingaben und optional `restored_seq`. Ein Wiederherstellen lässt sich selbst rückgängig machen.
3. **Neu planen bleibt im Projekt.** Ist ein Projekt aktiv, wird ein neuer Entwurf zur nächsten
   Version desselben Projekts. Region, eigene Preise und Nutzernotizen bleiben erhalten. Ein
   separates Projekt entsteht nur mit `new_project=true`.
4. **Jeder KI-Lauf wird gespeichert** (`agent_runs`), auch fehlgeschlagene und abgebrochene:
   - Nutzernachricht und Antwort im UI-Format sowie die vollständigen Modellnachrichten,
   - alle Entwurfsversuche einschließlich abgelehnter,
   - Tokenverbrauch, Modell, Prompt-Version und Fingerprint, Routing-Rolle und -Grund, Dauer,
   - Status (`completed`/`failed`/`cancelled`) und Fehler.
5. **Der Chat gehört zum Projekt.** `GET /api/projects/{id}/chat` baut den Verlauf aus den Läufen
   auf. Fragen vor dem ersten Projekt desselben Chats werden beim Anlegen dem Projekt zugeordnet.

Konsequenzen:
- Alte Versionen werden mit der aktuellen Engine neu berechnet. Ihre Zahlen können leicht
  abweichen, die Eingaben bleiben exakt.
- `agent_runs` enthält personenbezogene Inhalte (redigiert) und wird mit Projekt bzw. Nutzerkonto
  gelöscht (Kaskade).

## 5. LLM-Zugang (ADR-0003, ADR-0006)

- **Provider-agnostisch** über eine OpenAI-kompatible Chat-Completions-API (schlanker eigener Client
  mit Streaming und Tool-Calls, frei konfigurierbare Base-URL). Mögliche Anbieter: OpenRouter, Mistral, Azure OpenAI EU, STACKIT, Scaleway, Ollama, vLLM.
- **Konfiguration nur über Umgebungsvariablen:** `LLM_MODE` (`test` | `openai`), `LLM_BASE_URL`,
  `LLM_API_KEY`, `LLM_MODEL`, optional `LLM_MODEL_FAST`, `LLM_REASONING`.
- **LiteLLM** wird nie als Bibliothek eingebunden (Supply-Chain-Vorfall März 2026). Wenn
  überhaupt, läuft es als separater Proxy-Container mit gepinntem Image-Digest.
- **`LLM_MODE=test`** nutzt ein deterministisches Offline-Modell. Es ruft `save_design` mit
  eigenen Entwürfen auf (Hochbeet, Regal) und verhält sich sonst wie ein echtes Modell.
  Alle Tests, die BDD-Szenarien, CI und lokale Entwicklung laufen ohne API-Key.
- Für die Produktion: EU-gehosteter Anbieter mit AV-Vertrag und Zero Data Retention. Das ist reine
  Konfiguration.

### Werkzeuge des Agenten

`list_materials`, `save_design`, `get_current_design`, `change_project`, `undo_last_change`,
`get_project`, `add_explanation`.

- Werkzeugergebnisse sind kompakter Text oder JSON. Große Daten (komplette Stückliste, Entwurf,
  Katalog) werden nur auf Anfrage geholt.
- Schreibende Werkzeuge laufen innerhalb eines Agent-Laufs nacheinander, damit parallele
  Tool-Aufrufe nicht um dieselbe Sequenznummer konkurrieren.
- Kaputte Tool-Argumente (unquotierte Formeln, überzählige Klammern) werden an genau einer Stelle
  repariert (`modules/agent/args`). Jeder fehlerhafte Aufruf aus einem Fehlerbericht wird dort als
  Testfall abgelegt.
- Modellausgaben und Tool-Argumente sind unvertrauenswürdige Eingaben: strikt validieren, die
  Engine ablehnen lassen, nie `eval`. Ausdrücke laufen nur durch den Ausdrucks-Parser der Engine.

## 6. Freie Entwürfe: `AssemblyDesign` (ADR-0004, ADR-0007)

### 6.1 Was das LLM beschreibt

- **Parameter** mit Name, Einheit, Grenzen und optional Auswahlwerten.
- **Bauteile** mit Katalogmaterial. Maße und Positionen sind **Ausdrücke über die Parameter** in mm
  (x = Breite, y = Tiefe, z = oben). Zwei Platzierungen:
  - *Quader*: `size`, `at`, optional `rotate` um eine Achse;
  - *Stab* zwischen zwei Punkten: `start`, `end`, Querschnitt aus dem Material oder `section`,
    Ausrichtung `facing`, Endschnitte `cuts` (`square`, `level`, `plumb`, `corner`). Die Engine
    bestimmt Zuschnittlänge und Neigung.
- **Formen** (`shape`): `cloud`, `ellipse`, `rounded`, `triangle`, `arch`, `polygon`.
  **Ausschnitte** (`cutouts`): Rechteck, Ellipse, Polygon.
- **Wiederholungen** (`repeat`), **Bedingungen** (`when`), **Varianten**.
- **Beschläge** (`hardware`) und **Holzverbindungen** (`joints`): `tenon` (Zapfen), `half_lap`
  (Blatt), `notch` (Kerve).
- **Bauschritte** (`steps`): Reihenfolge und Montagehinweise. Die konkreten Unterschritte schreibt
  die Engine.
- Einsatzort (innen/außen), Montage (`support`: Boden oder Wand), Oberfläche und Kategorie
  (`category`, z. B. `building`).
- Material-, Holzart-, Stärke- und Bauweisewünsche des Nutzers sind verbindlich. Interne Begriffe
  (Katalog, IDs) werden dem Nutzer gegenüber nicht verwendet.

### 6.2 Was die Engine prüft

Jeder Entwurf wird geprüft. Bei einem Fehler lehnt die Engine ihn mit einer konkreten,
für das LLM verständlichen Meldung ab (`DesignRejectedError`).

- Material existiert im Katalog; Querschnitt bzw. Plattenstärke passt; Länge ≤ Handelslänge;
  Plattenzuschnitt ≤ Plattenformat; Schüttgut innerhalb seines Stärkenbereichs.
- **Maßholz** (`FD-LUMBER`): Jede Holzart mit `lumber_price_m3` ist in jedem Querschnitt bestellbar
  (Stärke 8–200 mm, Breite bis 400 mm), als `lumber_<holzart>_<t>x<b>` oder `lumber_<holzart>`.
  Preis = Volumen × Preis je m³. Teure Holzarten werden nie ersetzt.
- Keine Durchdringung von Bauteilen, außer bei deklarierten Holzverbindungen.
- Alle Teile hängen zusammen. Bei Wandmontage (`support="wall"`) dürfen getrennte Baugruppen
  existieren, wenn jede an der Wand anliegt.
- Boden- bzw. Wandkontakt; nichts unter Geländeniveau, außer Betonteilen bei Gebäuden.
- Ausschnitte liegen innerhalb der Kontur und überschneiden sich nicht. Endschnitte flacher als
  10° zur Stabachse werden abgelehnt. Kontur und Schrägschnitt lassen sich an einem Stab nicht
  kombinieren.
- **Beschläge sind Pflicht, wenn die Anleitung sie nennt** (`FD-HW`): Nennt ein Bauschritt
  Scharniere, Verschlüsse oder Griffe ohne passenden Beschlag, wird der Entwurf mit den passenden
  Katalog-IDs abgelehnt. Außenprojekte warnen bei nicht außentauglichen Beschlägen.
- Größen- und Mengengrenzen, siehe Kapitel 8.

### 6.3 Was die Engine ableitet

- **Stückliste** inkl. Maßholz-Hinweis, Schüttgut nach m³ bzw. m² mit 5 % Verschnitt.
- **Zuschnitt:** 1D-Handelslängen-Optimierung (First-Fit-Decreasing, 4 mm Sägeschnitt) und
  Plattenaufteilung.
- **Schrauben** aus erkannten Kontaktflächen (geschraubt wird durch das dünnere Teil), Holznägel
  und Holzbauschrauben aus den Holzverbindungen, Oberflächenmittel aus der Fläche.
- **Kosten** (Decimal, keine Gleitkommazahlen), **Gewicht**, **Kippwarnung**, **Werkzeug**.
- **Geometrie:** Bauteile sind Prismen, also eine 2D-Kontur extrudiert über die Stärke. Sie werden
  in konvexe Stücke zerlegt (Ohrenschneiden mit Lochbrücken). Durchdringung prüft der
  Separating-Axis-Test, Kontakt ergibt sich aus koplanaren gegenüberliegenden Flächen.
  Achsparallele Quader haben einen exakten Schnellpfad.
- **Zeichnungen:** Ansichten, Draufsicht, Isometrie mit Positionsnummern, automatische Bemaßung,
  Materiallegende, Sortierung über trennende Ebenen. Bei Wandmontage zusätzlich `iso_back` und
  `back`. Zu jedem geformten Holz- oder Plattenteil eine Schablone `template_<pos>`. Die Engine
  erzeugt eine rendererunabhängige Zeichnungs-IR, daraus wird byte-stabiles SVG und PDF.
- **3D-Daten** für den Browser (Quader und Dreiecksnetze).
- **Anleitung** mit konkreten Unterschritten (`InstructionStep.details`):
  - Einkaufen je Stücklistenzeile;
  - Zuschnitt Stange für Stange (z. B. „Stange 1 von 2 (5,00 m): 6× 800 mm (Pos. 1) … Rest ca. 180 mm“);
  - jede Verschraubung („Pos. A von <Seite> in Pos. B schrauben: n Stellen mit je k Schrauben …“);
  - „Holzverbindungen anreißen und ausarbeiten“, Oberfläche, Kippsicherung.
  - Ein Teil wird im ersten Schritt montiert, der es nennt. Die Schraubenmengen der Unterschritte
    ergeben in Summe die Kennzahl „Schrauben“.
- **Intent-Checks** (`Expectation`): Hüllmaße, begehbare Oberseite, Ebenen, Türen u. a., plus
  Konsistenz der Ansichten. Sie sichern Regressionsfälle ab.

### 6.4 Holzverbindungen und Schüttgut (ADR-0007)

| Verbindung | Regel |
|---|---|
| `tenon` | Stärke 1/3 des Holzes, Länge 0,4 × Gegenholz (30–60 mm), Zuschnitt je Zapfenende verlängert, 1 Holznagel (2 ab 200 mm Breite) |
| `half_lap` | Überlappung erlaubt, je Teil halbe Überdeckung, 1 Holznagel |
| `notch` | Überlappung bis 1/3 der Bauteilhöhe, 1 Holzbauschraube |

An deklarierten Verbindungen entfallen automatische Schrauben.

Schüttgut und Flächenmaterial (`kind="bulk"`): Ausfachung, Beton und Dämmung nach m³,
Dachdeckung und Schalung nach m², jeweils mit erlaubtem Stärkenbereich.

### 6.5 Der Katalog

`backend/internal/engine/data/catalog.json` ist die zentrale Fachquelle für Querschnitte,
Handelslängen, Formate, Preise, Eignung außen und Beschlagtypen. Seine Pflege ist ein
fachlicher Vorgang.

## 7. Token-Budget, Routing und Prompt-Provenienz (ADR-0006, ADR-0008)

1. **Token-Budget als Test.** Ein Offline-Benchmark (`task bench`) spielt fünf feste Szenarien
   durch die echten Werkzeuge und die Engine und misst jeden Request. Ein Test setzt Obergrenzen.
   Eine Grenze wird nur mit Begründung im Changelog angehoben und enger gezogen, wenn Requests
   kleiner werden.
2. **Kleiner, stabiler Präfix.** Ein Design-Werkzeug (`save_design`), die Ausdrucks-Syntax steht
   einmal im Schema, der System-Prompt ist eine kompakte Datei (`prompts/system.de.md`). Der Präfix
   ist byte-stabil (Test), damit Prompt-Caching greift. Für OpenRouter werden explizite
   Cache-Punkte gesetzt.
3. **Kompakte Historie.** Frühere Entwurfsargumente, Katalogabfragen und Reasoning werden durch
   Stubs ersetzt. Im laufenden Turn bleibt nur der letzte Entwurf vollständig. Jeder Entwurf bleibt
   in `agent_runs` vollständig erhalten.
4. **Serverseitige Historie.** Der Browser sendet nur die neue Nachricht. Die Historie kommt aus
   `agent_runs`, damit der Client keine Tool-Ergebnisse einschleusen kann.
5. **Modell-Routing pro Turn,** deterministisch und ohne zusätzlichen LLM-Call (`ROUTING_VERSION` 2):
   - neue Projekte, Entwürfe und strukturelle Änderungen gehen an `LLM_MODEL` (Designer);
   - Parameter-, Preis- und Variantenänderungen, Undo und Fragen in einem offenen Projekt gehen an
     `LLM_MODEL_FAST`, falls gesetzt, mit Rückfall auf den Designer bei Provider-Fehlern;
   - im Zweifel der Designer.
6. **Prompt-Provenienz.** Ein Fingerprint über Instructions, alle Werkzeugdefinitionen und die
   Routing-Version wird mit jedem Lauf gespeichert. `prompt.lock`, ein Snapshot-Test und
   `docs/ai/PROMPT_CHANGELOG.md` erzwingen für jede Prompt-Änderung eine neue `PROMPT_VERSION` und
   einen Changelog-Eintrag.

## 8. Sicherheit und Grenzen (ADR-0004 §7, ADR-0007)

| Bereich | Regel |
|---|---|
| Möbel und Kleinbauten | max. 4 m Kantenlänge, 2,5 m Höhe, 400 Bauteile |
| Gebäude (`category="building"`) | max. 25 × 25 m Grundfläche, 15 m Höhe, 1500 Bauteile; nur Beton unter Geländeniveau (Fundamente); Warnhinweis `BUILDING` (`FD-BUILD`): Statik vom Tragwerksplaner, meist Baugenehmigung; keine Prüfung von Standsicherheit, Wärme-, Feuchte-, Brand- oder Schallschutz |
| Ausgeschlossen | Balkone, Treppen, Absturzsicherungen, Spielgeräte mit Absturzhöhe, feste Elektroinstallation, Gas |
| An Fachleute verwiesen | Eingriffe in *bestehende* tragende Bauteile (Wanddurchbruch, Dachstuhl ändern, Sparren kürzen) |

- Das Sicherheits-Gate (`modules/compliance/safety`) prüft jede Nutzernachricht vor dem Modell.
  Ändern sich die Regeln, steigt `SAFETY_RULES_VERSION`.
- Alle Ergebnisse sind Planungshilfen ohne Standsicherheitsnachweis.
- Geheimnisse (`.env`) werden nie gelesen, ausgegeben oder eingecheckt; nur `.env.example` ist versioniert.

## 9. Technologie-Stack (ADR-0009)

| Schicht | Technik |
|---|---|
| Backend | Go (ein Binary), `net/http` (ServeMux mit Mustern), `log/slog` |
| API-Vertrag | contract-first: `backend/openapi.json` ist die Quelle; ein Go-Test prüft, dass der Router jede Operation bedient |
| Datenbank | SQLite (`modernc.org/sqlite`, ohne CGO) für Entwicklung und Tests; PostgreSQL (`pgx`) für Produktion; eingebettete SQL-Migrationen je Dialekt, beim Start ausgeführt |
| LLM | eigener Client für OpenAI-kompatible Chat-Completions (OpenRouter-Reasoning, Cache-Punkte); eigenes Offline-Modell |
| Chat-Stream | AI-SDK-UI-Message-Stream (SSE), serverseitig in Go implementiert |
| PDF | Go-Renderer aus der Zeichnungs-IR (ohne WeasyPrint, ohne Browser) |
| Frontend | Vite + React 19 + TypeScript, React Router, TanStack Query, Vercel AI SDK `useChat`, three.js, Tailwind 4 |
| API-Client | generiert mit `@hey-api/openapi-ts` aus `backend/openapi.json` |
| Funktionale Tests | Gherkin (Deutsch) mit playwright-bdd unter `tests/` |
| Build und Aufgaben | Task (`Taskfile.yml`), pnpm-Workspace |

## 10. Teststrategie

- **`task check`** ist das eine Signal für Mensch und KI-Agent. Es ruft `task backend:check` und
  `task frontend:check` auf. Beide enthalten Linter, Typprüfung, Unit-Tests und die
  **funktionalen BDD-Szenarien** unter `tests/features/`.
- **BDD-Szenarien** (`tests/features/backend/*.feature`, `tests/features/frontend/*.feature`)
  beschreiben das Verhalten fachlich und technologieunabhängig: Backend-Szenarien sprechen nur
  HTTP, Frontend-Szenarien nur den Browser. Sie laufen mit dem Offline-Modell.
- **Engine-Tests:** Golden-Dateien, Korpus-Invarianten über alle Testentwürfe, Intent-Checks,
  Fuzzing des Ausdrucks-Parsers.
- **Regressionsfälle:** Jeder gemeldete fehlerhafte Entwurf oder Agent-Lauf wird ein Fall unter
  `backend/testdata/regressions/` (`task regress:capture`). Ein Bugfix ist ohne Fall nicht fertig.
- **Agent-Tests:** Tool-Argument-Reparatur, Routing, Prompt-Lock, Token-Budget, Stream-Format.
- **Live-Evaluation** (`task eval:live`) kostet Geld, braucht einen Schlüssel und läuft nicht in CI.
- Kein Test braucht einen API-Key oder Netzwerkzugriff.
