# language: de
@frontend
Funktionalität: Hochbeet im Browser planen, ändern und rückgängig machen

  Szenario: Hochbeet planen, per Chat verbreitern, rückgängig machen und Variante wählen
    Angenommen ich öffne die Startseite
    Dann sehe ich die Überschrift "Was möchtest du bauen oder reparieren?"
    Und weist die Seite auf den KI-Assistenten hin
    Und ist die Seite barrierefrei
    Wenn ich im Planer schreibe "Ich möchte ein Hochbeet 2 × 1 m, 80 cm hoch, aus Lärche bauen."
    Dann zeigt die Projektzusammenfassung "Hochbeet aus Brettern – 2000 × 1000 × 870 mm"
    Und zeigt das Projekt das Kennzeichen "KI-Entwurf"
    Und ist die Adresse eine Projektseite
    Und ich merke mir die angezeigten Materialkosten
    Und ich zähle ab jetzt die geladenen Zeichnungen
    Wenn ich in den Plänen die Ansicht "Draufsicht" wähle
    Dann zeigt die Zeichnung "plan" eine Beschreibung mit "Draufsicht von Hochbeet (2000 × 1000 × 870 mm"
    Wenn ich im Planer schreibe "Mach es 50 cm breiter"
    Dann zeigt die Projektzusammenfassung "Hochbeet aus Brettern – 2000 × 1500 × 870 mm"
    Und haben sich die angezeigten Materialkosten geändert
    Und zeigt die Zeichnung "plan" eine Beschreibung mit "(2000 × 1500 × 870 mm"
    Und wurden nur die Zeichnungen "iso.svg, plan.svg" geladen
    Wenn ich den Reiter "Material" öffne
    Dann zeigt die Materialliste "Brett Lärche"
    Wenn ich auf "Rückgängig" klicke
    Dann zeigt die Projektzusammenfassung "Hochbeet aus Brettern – 2000 × 1000 × 870 mm"
    Und zeigen die Materialkosten wieder den gemerkten Wert
    Wenn ich auf "Variante Douglasie wählen" klicke
    Dann haben sich die angezeigten Materialkosten geändert
    Und zeigt die Materialliste "Brett Douglasie"
    Und ist die Seite barrierefrei
    Und führt der Link "PDF herunterladen" zu einem PDF
    Wenn ich die Projektliste öffne
    Dann sehe ich ein Projekt "Hochbeet" in der Liste
