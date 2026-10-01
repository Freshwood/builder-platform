# EU AI Act (VO 2024/1689) – Einordnung von Homeworking

## Rollen

- Homeworking entwickelt ein eigenes KI-System auf Basis fremder GPAI-Modelle und bietet es unter
  eigenem Namen an. Damit ist Homeworking **Anbieter des KI-Systems** (Art. 3 Nr. 3) und zugleich
  **Betreiber**.
- Die GPAI-Pflichten nach Art. 53 ff. treffen die Modellanbieter. Sie würden Homeworking erst bei
  erheblichem Fine-Tuning betreffen.

## Risikoklasse

- Der DIY-Planer fällt weder unter Annex I noch unter Annex III. Er ist **kein Hochrisiko-System**,
  sondern ein System mit begrenztem Risiko und Transparenzpflichten.
- Der Digital Omnibus on AI (VO 2026/1744, in Kraft seit 27.07.2026) verschiebt nur die
  Hochrisiko-Fristen. **Art. 50 gilt unverändert seit 02.08.2026.**
- Für Roadmap-Schritt 8/9 (Engineering, Prüfungen) ist die Einordnung neu zu prüfen, insbesondere
  ob eine Sicherheitskomponente von Bauprodukten vorliegt.

## Umsetzung

| Anforderung | Umsetzung |
|---|---|
| Art. 50 Abs. 1: Nutzer wissen, dass sie mit KI interagieren | Dauerhafter Hinweis im Chat-UI (`AiDisclosureBanner`) plus erste Agent-Nachricht |
| Art. 50 Abs. 2: maschinenlesbare Kennzeichnung synthetischer Inhalte [?: Schonfrist bis 02.12.2026] | KI-generierte Textabschnitte sind im Projektmodell als `origin="ai"` markiert. PDF-Metadaten (`Keywords`, XMP) enthalten `AI-generated text: yes`. Abschnitte werden im PDF sichtbar gekennzeichnet |
| Abgrenzung | Zeichnungen, Mengen, Kosten und Zuschnitte stammen aus der deterministischen Engine (`origin="engine"`) und sind **kein KI-Output** |
| Art. 4: KI-Kompetenz (durch Omnibus abgeschwächt) | Team-Schulung dokumentieren (organisatorisch) |
| Logging (freiwillig, hilft bei der Produkthaftung) | `project_commands.llm_trace_id`, `prompt_version`, Modellname |
