# language: de
Funktionalität: Rückgängig machen und Versionen
  Jeder Eintrag im Befehlslog ist eine Version. Wiederherstellen hängt eine neue Version an und
  löscht nichts.

  Grundlage:
    Angenommen ich habe im Chat "Regal 80 x 30 x 180 cm mit 5 Böden" geplant
    Und ich merke mir die Materialkosten

  Szenario: Eine Änderung rückgängig machen
    Wenn ich im Chat schreibe "Bitte 20 cm breiter"
    Und ich die letzte Änderung rückgängig mache
    Dann lautet die Projektzusammenfassung "Standregal mit 5 Böden – 800 × 300 × 1800 mm"
    Und sind die Materialkosten wieder wie gemerkt
    Und kann ich nichts mehr rückgängig machen

  Szenario: Im Chat rückgängig machen
    Wenn ich im Chat schreibe "Bitte 20 cm breiter"
    Und ich im Chat schreibe "Mach das bitte rückgängig"
    Dann ruft der Assistent das Werkzeug "undo_last_change" auf
    Und lautet die Projektzusammenfassung "Standregal mit 5 Böden – 800 × 300 × 1800 mm"

  Szenario: Der Verlauf listet jede Version
    Wenn ich im Chat schreibe "Bitte 20 cm breiter"
    Dann zeigt der Verlauf neueste zuerst:
      | Geändert: Breite (mm) 800 → 1000 |
      | Projekt „Regal“ erstellt         |
    Und ist im Verlauf "Geändert: Breite (mm) 800 → 1000" die aktuelle Version

  Szenario: Eine alte Version ansehen, ohne etwas zu ändern
    Wenn ich im Chat schreibe "Bitte 20 cm breiter"
    Und ich Version 1 ansehe
    Dann lautet die Projektzusammenfassung "Standregal mit 5 Böden – 800 × 300 × 1800 mm"
    Und kann ich nichts mehr rückgängig machen
    Wenn ich den aktuellen Stand neu lade
    Dann lautet die Projektzusammenfassung "Standregal mit 5 Böden – 1000 × 300 × 1800 mm"

  Szenario: Eine alte Version wiederherstellen und das wieder rückgängig machen
    Wenn ich im Chat schreibe "Bitte 20 cm breiter"
    Und ich Version 1 wiederherstelle
    Dann lautet die Projektzusammenfassung "Standregal mit 5 Böden – 800 × 300 × 1800 mm"
    Und zeigt der Verlauf neueste zuerst:
      | Version 1 wiederhergestellt      |
      | Geändert: Breite (mm) 800 → 1000 |
      | Projekt „Regal“ erstellt         |
    Wenn ich die letzte Änderung rückgängig mache
    Dann lautet die Projektzusammenfassung "Standregal mit 5 Böden – 1000 × 300 × 1800 mm"

  Szenario: Eine unbekannte Version gibt es nicht
    Wenn ich Version 99 ansehe
    Dann ist der Statuscode 404
