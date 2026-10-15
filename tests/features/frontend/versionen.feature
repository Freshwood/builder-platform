# language: de
@frontend
Funktionalität: Chat und Versionen überleben das Neuladen

  Szenario: Eine alte Version ansehen und wiederherstellen
    Angenommen ich öffne die Startseite
    Wenn ich im Planer schreibe "Regal 80 x 30 x 180 cm mit 5 Böden"
    Dann zeigt die Projektzusammenfassung "Standregal mit 5 Böden – 800 × 300 × 1800 mm"
    Wenn ich im Planer schreibe "Bitte 20 cm breiter"
    Dann zeigt die Projektzusammenfassung "Standregal mit 5 Böden – 1000 × 300 × 1800 mm"
    Wenn ich die Seite neu lade
    Dann zeigen die Nachrichten "Regal 80 x 30 x 180 cm mit 5 Böden"
    Und zeigen die Nachrichten "Bitte 20 cm breiter"
    Wenn ich auf "Verlauf" klicke
    Dann zeigt der Versionsverlauf "Geändert: Breite (mm) 800 → 1000"
    Und zeigt der Versionsverlauf "aktuell"
    Und ist der Bereich "version-history" barrierefrei
    Wenn ich im Versionsverlauf die Version 1 öffne
    Dann zeigt das Versionsbanner "Version 1"
    Und zeigt die Projektzusammenfassung "Standregal mit 5 Böden – 800 × 300 × 1800 mm"
    Und gibt es keinen Reiter "Anpassen"
    Wenn ich auf "Diese Version wiederherstellen" klicke
    Dann ist kein Versionsbanner zu sehen
    Und zeigt die Projektzusammenfassung "Standregal mit 5 Böden – 800 × 300 × 1800 mm"
    Und zeigt der Versionsverlauf "Version 1 wiederhergestellt"
    Und zeigt der Versionsverlauf "Geändert: Breite (mm) 800 → 1000"
