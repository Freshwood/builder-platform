# language: de
@frontend
Funktionalität: PDF herunterladen

  Grundlage:
    Angenommen ich öffne die Startseite
    Und ich im Planer schreibe "Regal 80 x 30 x 180 cm mit 5 Böden"
    Und zeigt die Projektzusammenfassung "Standregal mit 5 Böden – 800 × 300 × 1800 mm"

  Szenario: Das vollständige PDF wird heruntergeladen
    Wenn ich das PDF herunterlade
    Dann ist die Datei ein PDF mit mehr als 20000 Bytes

  Szenario: Ein Fehler bei der PDF-Erstellung zeigt eine Meldung statt einer kaputten Datei
    Angenommen die PDF-Erstellung ist gestört
    Wenn ich auf den Link "PDF herunterladen" klicke
    Dann sehe ich die PDF-Fehlermeldung "PDF konnte nicht erstellt werden"
    Und wurde nichts heruntergeladen
    Angenommen die PDF-Erstellung funktioniert wieder
    Wenn ich das PDF herunterlade
    Dann ist die Datei ein PDF mit mehr als 20000 Bytes
    Und sehe ich keine PDF-Fehlermeldung
