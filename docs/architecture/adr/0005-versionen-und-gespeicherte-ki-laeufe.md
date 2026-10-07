# ADR-0005: Versionen und gespeicherte KI-Läufe

- Status: akzeptiert
- Datum: 2026-10-07
- Ergänzt: [ADR-0002](0002-projektmodell-und-command-log.md)
- Problem: [docs/problems/versioning.md](../../problems/versioning.md)

## Kontext

Das Command-Log aus ADR-0002 speichert jede Änderung, war für Nutzer aber unsichtbar:

- Ein früherer Stand ließ sich nicht ansehen, nur schrittweise rückgängig machen.
- Plante die KI ein aktives Projekt neu (andere Vorlage, neuer Entwurf), entstand ein *neues*
  Projekt mit leerer Historie.
- Der Chat lebte nur im Browser und war nach einem Reload weg.
- KI-Läufe wurden nicht gespeichert. Abgelehnte Entwürfe, Tokenverbrauch und Antworten gingen
  verloren, obwohl jeder Lauf Geld kostet.

## Entscheidung

1. **Jeder Log-Eintrag ist eine Version.** `GET /projects/{id}/versions` liefert alle Einträge mit
   lesbarer Bezeichnung, Akteur, Zeitpunkt und Materialkosten. `GET /projects/{id}/versions/{seq}`
   rekonstruiert den Stand per Replay (wie Undo); Zeichnungen und PDF akzeptieren `?seq=`.
2. **Wiederherstellen hängt an, statt zu löschen.** Der neue Command `replace_inputs` trägt die
   vollständigen Eingaben (Replay bleibt eigenständig) und optional `restored_seq`. Wiederherstellen
   ist damit eine normale Änderung und selbst wieder rückgängig zu machen.
3. **Neu planen bleibt im Projekt.** Ist ein Projekt aktiv, erzeugen `create_project`,
   `create_from_template` und `design_project` per `replace_inputs` die nächste Version desselben
   Projekts (Region, eigene Preise und Nutzer-Notizen bleiben). Ein separates Projekt nur mit
   `new_project=true`.
4. **Jeder KI-Lauf wird gespeichert** (`agent_runs`): Nutzernachricht und Antwort im UI-Format,
   die vollständigen Modellnachrichten, alle Entwurfsversuche inklusive abgelehnter, Tokenverbrauch,
   Modell, Prompt-Version, Status (`completed`/`failed`/`cancelled`) und Fehler. Auch abgebrochene
   Läufe werden gespeichert.
5. **Der Chat gehört zum Projekt.** `GET /projects/{id}/chat` baut den Verlauf aus den Läufen auf;
   Fragen vor dem ersten Projekt desselben Chats werden beim Anlegen dem Projekt zugeordnet.

## Konsequenzen

- Ältere Versionen werden mit der aktuellen Engine neu berechnet. Ändert sich die Engine, können
  Zahlen alter Versionen leicht abweichen; die Eingaben bleiben exakt erhalten.
- `agent_runs` enthält personenbezogene Inhalte (Chat, redigiert) und wird mit dem Projekt bzw.
  dem Nutzerkonto gelöscht (Löschkaskade). Der DSGVO-Export sollte die Läufe künftig mit ausgeben.
- Die gespeicherten Entwürfe sind die Grundlage für Veröffentlichen, Forken und einen Marktplatz
  (siehe Roadmap, Schritt 6).
