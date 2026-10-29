# language: de
@frontend
Funktionalität: Projekt-Brief
  Der Brief sammelt Details zum Vorhaben und schickt sie mit der ersten Anfrage mit.

  Szenario: Details auswählen und die Planung starten
    Angenommen ich öffne die Startseite
    Wenn ich die Projektidee "Bücherregal" wähle
    Dann steht im Eingabefeld "Bücherregal mit 5 Böden"
    Wenn ich im Brief bei "Oberfläche" die Option "Geölt" wähle
    Dann zeigen die Details im Brief "Geölt"
    Und zeigen die Details im Brief "80 × 30 cm"
    Und ist die Seite barrierefrei
    Wenn ich die Planung starte
    Dann zeigen die Nachrichten "Maße: 80 × 30 cm (Breite × Tiefe), Höhe 180 cm"
    Und zeigen die Nachrichten "Oberfläche: geölt"
    Und zeigt die Projektzusammenfassung "Standregal mit 5 Böden – 800 × 300 × 1800 mm"
    Und zeigen die Arbeitsschritte des Assistenten "Konstruktion berechnet"
    Und ist das Eingabefeld wieder bereit
