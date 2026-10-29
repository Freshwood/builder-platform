# language: de
Funktionalität: Projekt im Chat planen
  Der Assistent entwirft jedes Projekt selbst und speichert es mit "save_design". Alle Zahlen
  (Stückliste, Zuschnitt, Kosten, Zeichnungen) berechnet die Engine.

  Grundlage:
    Angenommen ich bin ein neuer Gast

  Szenario: Ein Regal planen
    Wenn ich im Chat schreibe "Regal 80 x 30 x 180 cm mit 5 Böden"
    Dann ist der Antwort-Stream vollständig
    Und ruft der Assistent das Werkzeug "save_design" auf
    Und lautet die Projektzusammenfassung "Standregal mit 5 Böden – 800 × 300 × 1800 mm"
    Und trägt das Projekt den Hinweis "AI_DRAFT"
    Und enthält die Stückliste "Leimholzplatte Fichte"
    Und enthält die Zuschnittliste das Teil "Seitenteil"
    Und enthält die Anleitung den Schritt "Material einkaufen"
    Und hat das Projekt die Zeichnungen "iso, front, side, plan"
    Und hat das Projekt ein 3D-Modell
    Und liegen die Materialkosten über 50 Euro
    Und enthält meine Projektliste "Standregal mit 5 Böden"

  Szenario: Ein Hochbeet aus Lärche planen
    Wenn ich im Chat schreibe "Ich möchte ein Hochbeet 2 × 1 m, 80 cm hoch, aus Lärche bauen."
    Dann ruft der Assistent das Werkzeug "save_design" auf
    Und lautet die Projektzusammenfassung "Hochbeet aus Brettern – 2000 × 1000 × 870 mm"
    Und enthält die Stückliste "Brett Lärche"
    Und trägt das Projekt den Hinweis "AI_DRAFT"

  Szenario: Fehlen die Maße, fragt der Assistent nach
    Wenn ich im Chat schreibe "Ich möchte ein Hochbeet bauen"
    Dann ruft der Assistent kein Werkzeug auf
    Und antwortet der Assistent mit "Wie lang und wie breit"
    Und wurde kein Projekt angelegt

  Szenario: Eine allgemeine Frage legt kein Projekt an
    Wenn ich im Chat schreibe "Hallo, was kannst du?"
    Dann ruft der Assistent kein Werkzeug auf
    Und antwortet der Assistent mit "Bauvorhaben"
    Und wurde kein Projekt angelegt
