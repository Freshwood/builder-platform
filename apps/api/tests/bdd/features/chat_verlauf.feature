# language: de
Funktionalität: Der Chat gehört zum Projekt
  Jeder KI-Lauf wird gespeichert. Der Verlauf überlebt das Neuladen, und neu planen bleibt im
  selben Projekt.

  Grundlage:
    Angenommen ich bin ein neuer Gast

  Szenario: Der Chat-Verlauf wird mit dem Projekt gespeichert
    Wenn ich im Chat schreibe "Regal 80 x 30 x 180 cm mit 5 Böden"
    Und ich im Chat schreibe "Bitte 20 cm breiter"
    Dann hat der Chat-Verlauf des Projekts 4 Nachrichten
    Und enthält der Chat-Verlauf des Projekts "Regal 80 x 30 x 180 cm mit 5 Böden"
    Und enthält der Chat-Verlauf des Projekts "Bitte 20 cm breiter"

  Szenario: Fragen vor dem Projekt werden dem Projekt zugeordnet
    Wenn ich im Chat schreibe "Ich möchte ein Hochbeet bauen"
    Und ich im Chat schreibe "Hochbeet 2 x 1 m, 80 cm hoch"
    Dann lautet die Projektzusammenfassung "Hochbeet aus Brettern – 2000 × 1000 × 870 mm"
    Und enthält der Chat-Verlauf des Projekts "Ich möchte ein Hochbeet bauen"

  Szenario: Neu planen bleibt im selben Projekt
    Wenn ich im Chat schreibe "Regal 80 x 30 x 180 cm mit 5 Böden"
    Und ich merke mir das Projekt
    Und ich im Chat schreibe "Doch lieber ein Hochbeet 2 x 1 m, 80 cm hoch"
    Dann ist es dasselbe Projekt wie gemerkt
    Und lautet die Projektzusammenfassung "Hochbeet aus Brettern – 2000 × 1000 × 870 mm"
    Und enthält der Verlauf "Neu geplant: Hochbeet"
