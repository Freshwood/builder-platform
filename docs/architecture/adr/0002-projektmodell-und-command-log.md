# ADR-0002: Projektmodell als versioniertes Dokument plus Command-Log

- Status: akzeptiert
- Datum: 2026-10-01

## Kontext

Das Projektmodell ist laut Roadmap die Single Source of Truth. Änderungen wie „Mach es 50 cm breiter“
sollen konsistent Geometrie, Bauteile, Mengen, Kosten, Zeichnungen und Anleitung aktualisieren.
Gleichzeitig verlangen Produkthaftung (RL 2024/2853) und spätere Enterprise-Anforderungen
(Provenance, Audit) nachvollziehbare Änderungen.

## Entscheidung

1. **Eingabe und Ableitung sind getrennt.**
   - Gespeichert werden nur die *Eingaben*: Pack, Parameter, gewählte Variante.
   - Das *abgeleitete* Ergebnis (Bauteile, BOM, Zuschnitt, Kosten, Zeichnungen, Anleitung) erzeugt die
     deterministische Engine bei jeder Änderung neu und speichert es als Snapshot mit Versionsangaben.
2. **Speicherung:** `projects.model` als JSONB mit `schema_version`, validiert durch Pydantic. Ältere
   Versionen werden beim Laden per Upcaster migriert. Querschnittsdaten (Nutzer, Projekte) liegen in
   normalisierten Tabellen.
3. **Änderungen nur über typisierte Commands.** Commands sind eine diskriminierte Pydantic-Union, zum
   Beispiel `SetParameter`, `ChangeParameterBy`, `SelectVariant` oder `Rename`. Jede Ausführung schreibt
   einen append-only Eintrag in `project_commands` mit `seq`, `command`, `actor` (user/agent),
   `llm_trace_id`, `engine_version` und `diff`.
4. **Undo** ist ein Replay der Commands bis `seq - 1`. Das ist möglich, weil die Engine deterministisch ist.
5. **Bauteile** tragen eine stabile GUID und einen IFC-nahen Typ (`IfcMember`, `IfcPlate`, `IfcCovering`,
   `IfcMechanicalFastener` usw.), damit ein späterer IFC-Export nur ein Adapter ist.

## Konsequenzen

- Das LLM kann das Modell nicht direkt beschreiben, nur Commands vorschlagen.
- Integritätsregeln liegen in Pydantic und den Tests statt in DB-Constraints.
