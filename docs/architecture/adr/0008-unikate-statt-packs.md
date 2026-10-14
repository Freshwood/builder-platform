# ADR-0008: Jedes Projekt ist ein Unikat – keine Construction Packs, keine Vorlagen

- Status: akzeptiert
- Datum: 2026-10-14
- Löst ab: [ADR-0004](0004-freie-entwuerfe-bauteilmodell.md) §5 (Vertrauensstufen) und §6
  („Vorlagen zuerst“)
- Bezug: [ROADMAP](../../../ROADMAP.md), Abschnitt „Aktueller Schwerpunkt (2026-10-14)“

## Kontext

Bis hierhin gab es drei Wege zu einem Projekt: ein programmiertes Construction Pack (Hochbeet),
eine von uns kuratierte Vorlage (Regal, Gartenbank, Werkbank, Fensterladen, Wolkenregal,
Fachwerkhaus) und den freien KI-Entwurf. Der Agent sollte zuerst Pack oder Vorlage nehmen und nur
frei entwerfen, wenn nichts passte.

Das widerspricht dem Produkt: Wer ein Hochbeet oder ein Regal beschreibt, bekam immer dieselbe
Konstruktion mit anderen Maßen. Ein Unikat kann nicht aus einem Paket stammen. Dazu kamen zwei
Kosten: Die Pack- und Vorlagenübersicht stand in jeder Modellanfrage (rund 1 600 Token Präfix),
und Pack-Projekte hatten einen eigenen Code-Pfad (Parameter, Zeichnungen, Fehlerarten), der
neben dem Entwurfspfad gepflegt werden musste.

## Entscheidung

1. **Jedes Projekt ist ein Entwurf.** `ProjectInputs.design` ist Pflicht, `pack_id`,
   `pack_version` und `ConstructionResult.trust` entfallen. Die Herkunftsangabe nennt statt der
   Pack-Version die Version des Entwurfsformats (`Provenance.design_version`). Schema-Version 2.
2. **Packs und Vorlagen sind entfernt**: das Hochbeet-Pack (`calc_engine/packs/`), der
   Vorlagen-Loader und `data/templates/`, die Endpunkte `/api/packs` und `/api/templates` sowie
   die Agent-Werkzeuge `create_project`, `create_from_template`, `get_template_design` und
   `list_construction_packs`. Die Engine kennt nur noch `DesignRejectedError`.
3. **Die KI entwirft jedes Projekt selbst** mit `save_design`, genau nach der Angabe des Kunden;
   Einsatzort, Montage und Oberfläche gehören direkt in den Entwurf. Jeder Entwurf trägt den
   Hinweis „KI-Entwurf“ (AI Act Art. 50); es gibt keine Stufe „geprüft“ oder „Vorlage“ mehr.
4. **Die früheren Vorlagen bleiben nur als Testdaten** (`packages/calc-engine/tests/fixtures/designs/`).
   Sie halten die Engine über echte Konstruktionen ehrlich, der Agent sieht sie nie.
5. **Der Offline-Planer** (`LLM_MODE=test`) verhält sich wie ein Modell: Er ruft `save_design`
   mit einem eigenen Entwurf auf (`modules/agent/offline_designs/`, Hochbeet und Regal). Diese
   Entwürfe ersetzen in Tests und E2E das Sprachmodell und gelangen nie in einen Prompt.
6. **Gespeicherte Daten:** Migration 0004 löscht Projekte, deren Befehlslog ein Pack benutzt hat
   (sie lassen sich ohne Pack nicht mehr nachspielen); ihre Agent-Läufe bleiben für Kosten und
   Herkunft erhalten, nur der Projektbezug wird geleert. `projects.pack_id` entfällt,
   `project_commands.pack_version` heißt `design_version`. Entwurfsprojekte aus Schema 1 hebt das
   Repository beim Lesen auf Schema 2 an (`UPCASTERS`, `load_command`).
7. **Routing:** Die Abkürzung „Pack oder Vorlage → schnelles Modell“ entfällt; ein neues Projekt
   ist immer ein Entwurf und geht an das Entwurfsmodell (`ROUTING_VERSION` 2).

## Konsequenzen

- Ein Pfad statt drei: Prüfkette, Fehlerprotokoll, Zeichnungen und 3D-Modell sind für jedes
  Projekt gleich. Darauf bauen die nächsten Schritte der Roadmap auf (Vektorprofile → 3D,
  maschinenlesbare Fehlercodes, Strict-Output).
- Jede Anfrage ist rund 17 % kleiner (Präfix 9 163 → 7 607 Token, `docs/ai/PROMPT_CHANGELOG.md`
  2026-10-14.1).
- Ein neues Projekt kostet immer einen Entwurf durch das stärkere Modell; ein Regal ist nicht
  mehr in Sekunden fertig. Das ist gewollt: Qualität und Individualität gehen vor.
- Fachspezifisches Wissen des Hochbeet-Packs (Füllschichten und Erdmengen, Noppenbahn,
  Wühlmausgitter, Querstreben gegen Erddruck) ist im Entwurfsformat nicht abgebildet. Was davon
  gebraucht wird, kommt als allgemeine Engine-Fähigkeit zurück (z. B. Füllvolumen eines
  Hohlraums), nicht als Pack.
- Bestehende Pack-Projekte gehen beim Upgrade verloren (Punkt 6). Vor dem Go-Live betrifft das
  nur Test- und Gastdaten.
