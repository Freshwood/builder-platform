# language: de
@backend
Funktionalität: Echte Konstruktionen rechnen vollständig durch
  Die früheren Vorlagen sind Testentwürfe. Jeder muss sich anlegen lassen und alle Ausgaben
  liefern.

  Szenariogrundriss: Der Testentwurf "<Entwurf>" ergibt ein vollständiges Projekt
    Wenn ich ein Projekt aus dem Entwurf "<Entwurf>" anlege
    Dann wird das Projekt angelegt
    Und trägt das Projekt den Hinweis "AI_DRAFT"
    Und hat das Projekt ein 3D-Modell
    Und hat das Projekt die Zeichnungen "iso"
    Und liegen die Materialkosten über 10 Euro
    Und enthält die Anleitung den Schritt "Material einkaufen"
    Wenn ich "/api/projects/{projekt}/drawings/iso.svg" abrufe
    Dann ist der Statuscode 200
    Wenn ich "/api/projects/{projekt}/document.pdf" abrufe
    Dann ist der Statuscode 200
    Und beginnt die Antwort mit "%PDF-"

    Beispiele:
      | Entwurf      |
      | regal        |
      | hochbeet     |
      | werkbank     |
      | gartenbank   |
      | fensterladen |
      | wolkenregal  |
      | fachwerkhaus |
