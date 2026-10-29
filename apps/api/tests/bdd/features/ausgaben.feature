# language: de
Funktionalität: Zeichnungen, PDF und Export
  Zeichnungen und Dokumente entstehen deterministisch aus dem berechneten Projekt.

  Grundlage:
    Angenommen ich habe im Chat "Regal 80 x 30 x 180 cm mit 5 Böden" geplant

  Szenariogrundriss: Jede Ansicht ist ein SVG
    Wenn ich "/api/projects/{projekt}/drawings/<Ansicht>.svg" abrufe
    Dann ist der Statuscode 200
    Und ist der Inhaltstyp "image/svg+xml"
    Und enthält die Antwort "<svg"
    Und enthält die Antwort "</svg>"

    Beispiele:
      | Ansicht |
      | iso     |
      | front   |
      | side    |
      | plan    |

  Szenario: Die Zeichnung einer festen Version darf zwischengespeichert werden
    Wenn ich "/api/projects/{projekt}/drawings/iso.svg?seq=1" abrufe
    Dann ist der Statuscode 200
    Und enthält der Header "Cache-Control" den Text "immutable"

  Szenario: Eine unbekannte Ansicht gibt es nicht
    Wenn ich "/api/projects/{projekt}/drawings/gibtsnicht.svg" abrufe
    Dann ist der Statuscode 404

  Szenario: Das Projekt als PDF herunterladen
    Wenn ich "/api/projects/{projekt}/document.pdf" abrufe
    Dann ist der Statuscode 200
    Und ist der Inhaltstyp "application/pdf"
    Und beginnt die Antwort mit "%PDF-"
    Und ist die Antwort größer als 20000 Bytes
    Und enthält der Header "Content-Disposition" den Text "homeworking-"

  Szenario: Das Projekt mit Befehlslog exportieren
    Wenn ich "/api/projects/{projekt}/export" abrufe
    Dann ist der Statuscode 200
    Und hat das Feld "commands.0.command.type" den Wert "create_project"

  Szenario: Ein Projekt löschen
    Wenn ich "/api/projects/{projekt}" lösche
    Dann ist der Statuscode 204
    Wenn ich "/api/projects/{projekt}" abrufe
    Dann ist der Statuscode 404
