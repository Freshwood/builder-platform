package compliance

// NoticesVersion versions the fixed notice texts for provenance.
const NoticesVersion = "2026-10-01"

// AIChatDisclosure is shown next to the chat (AI Act Art. 50).
const AIChatDisclosure = "Du sprichst mit einem KI-Assistenten. Maße, Mengen, Kosten und Zeichnungen berechnet " +
	"Homeworking regelbasiert; die KI formuliert Fragen und Erklärungen."

// AIContentLabel marks AI-written sections in documents.
const AIContentLabel = "KI-generiert"

// AIDocumentStatement explains the AI label in the PDF.
const AIDocumentStatement = "Abschnitte mit der Kennzeichnung „KI-generiert“ wurden von einem KI-System erstellt " +
	"(Art. 50 KI-Verordnung). Zeichnungen, Mengen, Zuschnitte und Kosten stammen aus der " +
	"regelbasierten Berechnung von Homeworking."

// PlanningDisclaimer states that results are a planning aid without structural proof.
const PlanningDisclaimer = "Planungshilfe – kein Standsicherheitsnachweis und keine geprüfte Statik. Prüfe Maße und " +
	"Material vor dem Kauf und lass sicherheitsrelevante Bauteile im Zweifel von einer " +
	"Fachperson beurteilen."

// PermitNotice points to the state building code.
const PermitNotice = "Ob ein Vorhaben genehmigungs- oder anzeigepflichtig ist, regeln die Landesbauordnung deines " +
	"Bundeslandes und ggf. ein Bebauungsplan. Homeworking gibt dazu nur allgemeine Hinweise; " +
	"verbindlich ist die Auskunft des örtlichen Bauamts."

// PriceNotice says that prices are estimates.
const PriceNotice = "Preise sind unverbindliche Richtwerte aus dem Homeworking-Katalog und keine Angebote. " +
	"Tatsächliche Preise variieren nach Händler, Region und Zeitpunkt."

// WorkSafety lists basic protective equipment.
const WorkSafety = "Arbeitsschutz: Bei Säge- und Bohrarbeiten Schutzbrille und Gehörschutz tragen, beim " +
	"Umgang mit Gitter und Holz Handschuhe. Herstellerhinweise der Werkzeuge beachten."

// DocumentNotices are printed in every project document.
var DocumentNotices = []string{PlanningDisclaimer, PermitNotice, PriceNotice, WorkSafety}
