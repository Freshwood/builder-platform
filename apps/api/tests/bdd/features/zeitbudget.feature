# language: de
Funktionalität: Zeitbudget der Konstruktion
  Jede Konstruktion muss für den Kunden in einer festen Zeit fertig sein, gemessen von der
  Nachricht bis zum gespeicherten Projekt. Mittlere Konstruktionen (Regale, Schränke, Podeste)
  haben 60 Sekunden, schwere (Fachwerkhaus, Gartenhaus, Carport, große Holzbauten) 90 Sekunden.
  Die Werte und die Einstufung stehen in der Engine (calc_engine/pipeline/budget.py). Dieses
  Szenario prüft die festen Werte und die Einstufung; mit dem echten Modell misst sie
  `task eval:live` (Fälle mit complexity in tests/regressions), und die Pipeline bricht eine
  Stufe ab, die das Budget überschreitet (tests/test_time_budget.py).

  Grundlage:
    Angenommen ich bin ein neuer Gast

  Szenario: Ein Regal ist eine mittlere Konstruktion mit 60 Sekunden
    Wenn ich den Steckbrief "Bei uns im Flur liegen ständig die Schuhe herum, ich brauche ein Regal" prüfe
    Dann ist der Statuscode 200
    Und hat das Feld "complexity" den Wert "medium"
    Und hat das Feld "time_budget_s" den Wert "60"

  Szenario: Ein Podest ist eine mittlere Konstruktion mit 60 Sekunden
    Wenn ich den Steckbrief "Podest für Kinder, 2 Meter lang und 1 Meter breit" prüfe
    Dann hat das Feld "complexity" den Wert "medium"
    Und hat das Feld "time_budget_s" den Wert "60"

  Szenario: Ein Fachwerkhaus ist eine schwere Konstruktion mit 90 Sekunden
    Wenn ich den Steckbrief "Ich möchte im Garten ein kleines Fachwerkhaus bauen" prüfe
    Dann hat das Feld "complexity" den Wert "heavy"
    Und hat das Feld "time_budget_s" den Wert "90"

  Szenario: Ein Carport ist eine schwere Konstruktion mit 90 Sekunden
    Wenn ich den Steckbrief "Carport für zwei Autos" prüfe
    Dann hat das Feld "complexity" den Wert "heavy"
    Und hat das Feld "time_budget_s" den Wert "90"

  Szenario: Ein Haustür-Regal ist trotz des Wortes Haus keine schwere Konstruktion
    Wenn ich den Steckbrief "Ein Regal neben der Haustür für Schuhe" prüfe
    Dann hat das Feld "complexity" den Wert "medium"

  Szenario: Ein mittleres Projekt ist im Chat innerhalb von 60 Sekunden fertig
    Wenn ich im Chat schreibe "Schrank 80 x 40 x 100 cm, innen"
    Dann ruft der Assistent das Werkzeug "plan_design" auf
    Und ist die Planungszeit höchstens 60 Sekunden
    Und enthält meine Projektliste "Objekt nach Kundenangabe"

  Szenario: Ein Brief ohne Maße ist im Chat innerhalb von 60 Sekunden fertig
    Wenn ich im Chat schreibe "Ich brauche einen Schrank für den Flur"
    Dann ruft der Assistent das Werkzeug "plan_design" auf
    Und ist die Planungszeit höchstens 60 Sekunden
    Und enthält meine Projektliste "Objekt nach Kundenangabe"

  Szenario: Ein Fachwerkhaus ist im Chat innerhalb von 90 Sekunden fertig
    Wenn ich im Chat schreibe "Ich möchte im Garten ein kleines Fachwerkhaus bauen, in dem wir im Sommer übernachten können."
    Dann ruft der Assistent das Werkzeug "plan_design" auf
    Und ist die Planungszeit höchstens 90 Sekunden
    Und enthält meine Projektliste "Fachwerk"
