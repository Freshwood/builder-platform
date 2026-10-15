# language: de
@backend
Funktionalität: Die Engine prüft jeden Entwurf
  Das Sprachmodell rechnet nie. Ein fehlerhafter Entwurf wird mit einer verständlichen Meldung
  abgelehnt, damit das Modell ihn korrigieren kann.

  Szenario: Ein gültiger Entwurf wird angelegt
    Wenn ich ein Projekt aus dem Entwurf "regal" anlege
    Dann wird das Projekt angelegt
    Und lautet die Projektzusammenfassung "Standregal mit 5 Böden – 800 × 300 × 1800 mm"

  Szenario: Parameter aus dem Entwurf werden übernommen
    Wenn ich ein Projekt aus dem Entwurf "regal" mit den Parametern "{\"width_mm\": 600, \"shelves\": 3}" anlege
    Dann wird das Projekt angelegt
    Und lautet die Projektzusammenfassung "Standregal mit 3 Böden – 600 × 300 × 1800 mm"

  Szenario: Unbekanntes Material
    Wenn ich ein Projekt aus dem Entwurf "regal" mit diesen Änderungen anlege:
      | Pfad              | Wert             |
      | parts[0].material | mahagoni_gold_99 |
    Dann wird der Entwurf abgelehnt mit "unbekanntes Material 'mahagoni_gold_99'"

  Szenario: Parameter außerhalb seiner Grenzen
    Wenn ich ein Projekt aus dem Entwurf "regal" mit den Parametern "{\"height_mm\": 2400}" anlege
    Dann wird der Entwurf abgelehnt mit "height_mm: muss zwischen 600 und 2000 liegen"

  Szenario: Zuschnitt größer als das Plattenformat
    Wenn ich ein Projekt aus dem Entwurf "regal" mit diesen Änderungen anlege:
      | Pfad          | Wert |
      | params[2].max | 3000 |
      | params[2].default | 3000 |
    Dann wird der Entwurf abgelehnt mit "ist größer als das Plattenformat"

  Szenario: Bauteile dürfen sich nicht durchdringen
    Wenn ich ein Projekt aus dem Entwurf "regal" mit diesen Änderungen anlege:
      | Pfad     | Wert |
      | parts[+] | {"id": "doppelt", "name": "Seitenteil", "material": "{material}", "size": [18, "depth_mm - 3 * back_panel", "height_mm"], "at": [0, 0, 0]} |
    Dann wird der Entwurf abgelehnt mit "durchdringen sich"

  Szenario: Nennt die Anleitung Scharniere, müssen sie in der Stückliste stehen
    Wenn ich ein Projekt aus dem Entwurf "regal" mit diesen Änderungen anlege:
      | Pfad          | Wert                            |
      | steps[0].text | Scharniere an die Tür schrauben |
    Dann wird der Entwurf abgelehnt mit "nennt Scharniere/Bänder"
