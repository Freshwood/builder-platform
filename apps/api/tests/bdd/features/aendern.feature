# language: de
Funktionalität: Projekt ändern
  Änderungen laufen über typisierte Befehle. Die Engine rechnet danach alles neu.

  Grundlage:
    Angenommen ich habe im Chat "Regal 80 x 30 x 180 cm mit 5 Böden" geplant
    Und ich merke mir die Materialkosten

  Szenario: Relativ im Chat ändern
    Wenn ich im Chat schreibe "Bitte 20 cm breiter"
    Dann ruft der Assistent das Werkzeug "change_project" auf
    Und lautet die Projektzusammenfassung "Standregal mit 5 Böden – 1000 × 300 × 1800 mm"
    Und hat der Parameter "width_mm" den Wert "1000"

  Szenario: Einen Parameter direkt setzen
    Wenn ich den Parameter "shelves" auf "6" setze
    Dann ist die Änderung erfolgreich
    Und lautet die Projektzusammenfassung "Standregal mit 6 Böden – 800 × 300 × 1800 mm"
    Und kann ich rückgängig machen

  Szenario: Einen Parameter um einen Betrag ändern
    Wenn ich den Parameter "height_mm" um -200 ändere
    Dann ist die Änderung erfolgreich
    Und hat der Parameter "height_mm" den Wert "1600"

  Szenario: Eine Variante wählen
    Wenn ich die Variante "wide" wähle
    Dann ist die Änderung erfolgreich
    Und hat der Parameter "width_mm" den Wert "1200"
    Und haben sich die Materialkosten geändert

  Szenario: Das Projekt umbenennen
    Wenn ich das Projekt in "Regal fürs Kinderzimmer" umbenenne
    Dann ist die Änderung erfolgreich
    Und hat das Projekt den Titel "Regal fürs Kinderzimmer"

  Szenario: Einen eigenen Preis eintragen
    Wenn ich für "glulam_spruce_18" den Preis "39.90" eintrage
    Dann ist die Änderung erfolgreich
    Und hat die Stückliste für "glulam_spruce_18" einen eigenen Preis
    Und haben sich die Materialkosten geändert

  Szenario: Eine Notiz hinzufügen
    Wenn ich die Notiz "Kanten vorher schleifen" hinzufüge
    Dann ist die Änderung erfolgreich

  Szenariogrundriss: Werte außerhalb der Grenzen werden abgelehnt
    Wenn ich den Parameter "<Parameter>" auf "<Wert>" setze
    Dann wird die Änderung abgelehnt mit "<Meldung>"

    Beispiele:
      | Parameter | Wert | Meldung                      |
      | width_mm  | 5000 | muss zwischen 400 und 1400   |
      | height_mm | 100  | muss zwischen 600 und 2000   |
      | shelves   | 20   | muss zwischen 2 und 9        |

  Szenario: Eine unbekannte Variante wird abgelehnt
    Wenn ich die Variante "gibt-es-nicht" wähle
    Dann wird die Änderung abgelehnt mit "gibt-es-nicht"
