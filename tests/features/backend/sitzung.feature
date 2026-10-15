# language: de
@backend
Funktionalität: Sitzung und Grundfunktionen
  Jeder Besucher bekommt ohne Anmeldung eine Gast-Sitzung. Projekte gehören immer zu genau
  einer Sitzung.

  Szenario: Der Dienst meldet sich gesund
    Wenn ich "/api/health" abrufe
    Dann ist der Statuscode 200
    Und hat das Feld "status" den Wert "ok"

  Szenario: Ein neuer Besucher wird Gast und behält seine Sitzung
    Wenn ich "/api/me" abrufe
    Dann ist der Statuscode 200
    Und hat das Feld "is_guest" den Wert "true"
    Und bekomme ich bei erneutem Abruf von "/api/me" dieselbe Gast-ID

  Szenario: Die Pflichthinweise kennzeichnen den KI-Assistenten
    Wenn ich "/api/notices" abrufe
    Dann ist der Statuscode 200
    Und enthält das Feld "ai_disclosure" den Text "KI-Assistenten"

  Szenario: Ein Gast sieht keine fremden Projekte
    Angenommen ich habe im Chat "Regal 80 x 30 x 180 cm mit 5 Böden" geplant
    Wenn ein anderer Gast "/api/projects/{projekt}" abruft
    Dann ist der Statuscode 404

  Szenario: Ein unbekanntes Projekt gibt es nicht
    Wenn ich "/api/projects/00000000-0000-4000-8000-000000000000" abrufe
    Dann ist der Statuscode 404
