# language: de
@frontend
Funktionalität: Regal mit 3D-Modell, Plänen und Zuschnitt

  Grundlage:
    Angenommen ich öffne die Startseite
    Und ich im Planer schreibe "Regal 80 x 30 x 180 cm mit 5 Böden"
    Und zeigt die Projektzusammenfassung "Standregal mit 5 Böden – 800 × 300 × 1800 mm"

  Szenario: 3D-Modell, Isometrie, Zuschnitt und Parameter
    Dann zeigt das Projekt das Kennzeichen "KI-Entwurf"
    Und ist das 3D-Modell sichtbar
    Und zeigt die Positionsliste "Fachboden"
    Wenn ich in den Plänen die Ansicht "Isometrie" wähle
    Dann zeigt die Zeichnung "iso" eine Beschreibung mit "800 × 300 × 1800 mm"
    Wenn ich im Planer schreibe "Bitte 20 cm breiter"
    Dann zeigt die Projektzusammenfassung "Standregal mit 5 Böden – 1000 × 300 × 1800 mm"
    Wenn ich den Reiter "Zuschnitt" öffne
    Dann zeigt der Reiterinhalt "Einkauf und Schnittplan"
    Wenn ich den Reiter "Anpassen" öffne
    Und ich das Feld "Anzahl Böden" auf "6" setze und bestätige
    Dann zeigt die Projektzusammenfassung "Standregal mit 6 Böden – 1000 × 300 × 1800 mm"
    Und ist die Seite barrierefrei

  Szenario: Die Materialliste erklärt Preise und übernimmt eigene Preise
    Wenn ich den Reiter "Material" öffne
    Dann sehe ich den Text "Woher kommen die Preise?"
    Und zeigt der Preisstatus "Noch keine eigenen Preise eingetragen."
    Und verweist der erste Link "Hornbach" auf "https://www.hornbach.de/s/Leimholzplatte"
    Und ich merke mir die Summe der Materialliste
    Wenn ich das Feld "Dein Preis je Platte für Leimholzplatte Fichte" auf "39,90" setze und bestätige
    Dann zeigt der Preisstatus eigene Preise für 1 Position
    Und zeigt die Materialliste "dein Preis"
    Und hat sich die Summe der Materialliste geändert
    Und ist die Seite barrierefrei
    Wenn ich auf "Rückgängig" klicke
    Dann zeigt der Preisstatus "Noch keine eigenen Preise eingetragen."
