# Funktionale BDD-Szenarien: Backend

Hier steht, **was** das Backend fachlich können muss. Die Szenarien sind in Gherkin auf Deutsch
geschrieben und laufen mit [pytest-bdd](https://pytest-bdd.readthedocs.io/) im selben Prozess gegen
die FastAPI-App (Offline-Modell `LLM_MODE=test`, SQLite). Es werden weder Server noch Schlüssel
oder Netz gebraucht.

```bash
task bdd:backend                 # nur diese Szenarien
task bdd:backend -- -k Regal     # nach Szenarioname filtern
task test                        # sie laufen auch hier mit
```

Browser-Szenarien: `apps/web/tests/bdd/`.

## Ein Szenario hinzufügen

1. Passende Feature-Datei in `features/` wählen oder neu anlegen (erste Zeile `# language: de`).
2. Vorhandene Schritte aus `steps/api_steps.py` wiederverwenden. Schritte beschreiben, was die
   API liefert („lautet …“, „enthält …“). Fehlt einer, ihn dort deutsch formuliert ergänzen.
3. Noch nicht umgesetztes Verhalten mit `@wip` markieren.

### Entwürfe als Testdaten

`designs/<name>.json` enthält Entwürfe im Format `AssemblyDesign`, so wie die KI sie mit
`save_design` speichern würde. Mit einer Tabelle lassen sich einzelne Werte ändern:

```gherkin
Wenn ich ein Projekt aus dem Entwurf "regal" mit diesen Änderungen anlege:
  | Pfad              | Wert             |
  | parts[0].material | mahagoni_gold_99 |
  | parts[+]          | {"id": "x", ...} |
```

`parts[0].material` setzt einen Wert, `parts[+]` hängt ein Element an. Werte werden als JSON
gelesen, sonst als Text.

### Was das Offline-Modell versteht

Im Testbetrieb ersetzt ein regelbasiertes Modell das Sprachmodell. Es versteht nur einfache
Formulierungen:

| Eingabe | Wirkung |
|---|---|
| „Regal 80 x 30 x 180 cm mit 5 Böden“, „Bücherregal …“ | entwirft ein Regal (`save_design`) |
| „Hochbeet 2 × 1 m, 80 cm hoch, aus Lärche“ | entwirft ein Hochbeet |
| „Hochbeet“ ohne Maße | fragt nach den Maßen |
| „20 cm breiter / schmaler / länger / kürzer / höher / niedriger“ | `change_parameter_by` |
| „rückgängig“ | `undo_last_change` |
| „… Variante günstig / langlebig / Komfort“ | `select_variant` |
| „Lärche“, „Douglasie“, „Fichte“ | Holzart setzen |

Die Sicherheitsverweise (Elektro, Gas/Feuerstätten, tragende Bauteile, Schadstoffe) kommen nicht
vom Modell, sondern vom Sicherheits-Gate. Sie funktionieren mit jedem Modell.
