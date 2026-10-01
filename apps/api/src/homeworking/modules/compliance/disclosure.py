"""Fixed notice texts (AI Act Art. 50, liability, building law). Versioned for provenance."""

from __future__ import annotations

NOTICES_VERSION = "2026-10-01"

AI_CHAT_DISCLOSURE = (
    "Du sprichst mit einem KI-Assistenten. Maße, Mengen, Kosten und Zeichnungen berechnet "
    "Homeworking regelbasiert; die KI formuliert Fragen und Erklärungen."
)

AI_CONTENT_LABEL = "KI-generiert"

AI_DOCUMENT_STATEMENT = (
    "Abschnitte mit der Kennzeichnung „KI-generiert“ wurden von einem KI-System erstellt "
    "(Art. 50 KI-Verordnung). Zeichnungen, Mengen, Zuschnitte und Kosten stammen aus der "
    "regelbasierten Berechnung von Homeworking."
)

PLANNING_DISCLAIMER = (
    "Planungshilfe – kein Standsicherheitsnachweis und keine geprüfte Statik. Prüfe Maße und "
    "Material vor dem Kauf und lass sicherheitsrelevante Bauteile im Zweifel von einer "
    "Fachperson beurteilen."
)

PERMIT_NOTICE = (
    "Ob ein Vorhaben genehmigungs- oder anzeigepflichtig ist, regeln die Landesbauordnung deines "
    "Bundeslandes und ggf. ein Bebauungsplan. Homeworking gibt dazu nur allgemeine Hinweise; "
    "verbindlich ist die Auskunft des örtlichen Bauamts."
)

PRICE_NOTICE = (
    "Preise sind unverbindliche Richtwerte aus dem Homeworking-Katalog und keine Angebote. "
    "Tatsächliche Preise variieren nach Händler, Region und Zeitpunkt."
)

WORK_SAFETY = (
    "Arbeitsschutz: Bei Säge- und Bohrarbeiten Schutzbrille und Gehörschutz tragen, beim "
    "Umgang mit Gitter und Holz Handschuhe. Herstellerhinweise der Werkzeuge beachten."
)

DOCUMENT_NOTICES: list[str] = [PLANNING_DISCLAIMER, PERMIT_NOTICE, PRICE_NOTICE, WORK_SAFETY]
