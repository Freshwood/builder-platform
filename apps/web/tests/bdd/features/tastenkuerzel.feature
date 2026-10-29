# language: de
@frontend
Funktionalität: Tastenkürzel

  Szenario: Strg+Z nimmt die letzte Änderung zurück, Schrägstrich springt in den Chat
    Angenommen ich öffne die Startseite
    Wenn ich im Planer schreibe "Regal 80 x 30 x 180 cm mit 5 Böden"
    Dann zeigt die Projektzusammenfassung "Standregal mit 5 Böden – 800 × 300 × 1800 mm"
    Wenn ich im Planer schreibe "Bitte 20 cm breiter"
    Dann zeigt die Projektzusammenfassung "Standregal mit 5 Böden – 1000 × 300 × 1800 mm"
    Wenn ich außerhalb eines Eingabefelds die Taste "Control+z" drücke
    Dann zeigt die Projektzusammenfassung "Standregal mit 5 Böden – 800 × 300 × 1800 mm"
    Wenn ich außerhalb eines Eingabefelds die Taste "/" drücke
    Dann hat das Eingabefeld des Chats den Fokus
    Und das Zeichen "/" wurde nicht eingegeben
