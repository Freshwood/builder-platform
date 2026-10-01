# Compliance-Übersicht (Stand 2026-10-01)

> **Keine Rechtsberatung.** Diese Dokumente halten die technische Umsetzung rechtlicher Anforderungen
> fest. Alle mit **[?]** markierten Punkte müssen vor dem Go-Live anwaltlich geprüft werden.

| Dokument | Inhalt |
|---|---|
| [ai-act.md](ai-act.md) | Einordnung nach EU AI Act, Transparenzpflichten nach Art. 50, Umsetzung |
| [dsgvo-dpia-template.md](dsgvo-dpia-template.md) | Datenschutz: Rechtsgrundlagen, LLM-Auftragsverarbeitung, Vorlage für die Datenschutz-Folgenabschätzung |
| [safety-guardrails.md](safety-guardrails.md) | Sicherheitsleitplanken des Agenten, Hinweisbausteine, Haftung |
| [roadmap-gates.md](roadmap-gates.md) | Compliance-Gates je Roadmap-Schritt (1–10) |

## Phase I – Pflichten und technische Maßnahmen

| Pflicht | Gilt ab | Maßnahme im Code |
|---|---|---|
| AI Act Art. 50 (KI-Interaktion, Kennzeichnung) | 02.08.2026 | `compliance.ai_disclosure`: Hinweis im Chat, Kennzeichnung im PDF und in den PDF-Metadaten |
| DSGVO Art. 5, 25, 28, 44 ff. | gilt | Prompts gehen nur durch `compliance.redaction`, Provider über ENV konfigurierbar, keine Analytics |
| § 25 TDDDG | gilt | ausschließlich technisch notwendige Cookies (Session) |
| § 5 DDG | gilt | Seiten `/impressum` und `/datenschutz` (Platzhalter, müssen ausgefüllt werden) |
| BGB §§ 327 ff., § 309 Nr. 7 | gilt | Hinweis „Planungshilfe, kein Standsicherheitsnachweis“, kein pauschaler Haftungsausschluss |
| ProdHaftG-neu (RL 2024/2853) [?] | 09.12.2026 | Provenance: Engine-, Pack-, Katalog-, Prompt- und Modellversion pro Ergebnis, Replay über den Command-Log |
| LBO / RDG | gilt | keine verbindlichen Genehmigungsaussagen, nur allgemeine Information mit Verweis aufs Bauamt |
| DIN-Urheberrecht | gilt | keine Normtexte oder Normtabellen in Code, Prompts oder PDFs, nur eigene Regeln mit Normverweis |
| BFSG / WCAG 2.2 AA [?] | 28.06.2025 | axe-Prüfung in Playwright, SVG mit `<title>`/`<desc>`, PDF mit Tags (PDF/UA) |
