# Datenschutz (DSGVO, BDSG, TDDDG) und Vorlage für die Datenschutz-Folgenabschätzung

## Verarbeitungen in Phase I

| Zweck | Daten | Rechtsgrundlage | Speicherdauer |
|---|---|---|---|
| Gastkonto | zufällige Kennung im signierten Session-Cookie (keine E-Mail in Phase I) | Art. 6 Abs. 1 lit. b | bis zur Kontolöschung; Cookie 180 Tage |
| Projekte | Projektparameter, Ergebnisse, Command-Log | Art. 6 Abs. 1 lit. b | bis zur Löschung des Projekts oder Kontos |
| Agent-Chat | Nachrichtentexte (vor Übermittlung an das LLM redigiert) | Art. 6 Abs. 1 lit. b | wird serverseitig **nicht** gespeichert, nur im Browser-Tab gehalten |
| Betriebslogs | Request-IDs, Agent-Trace-ID, Modell- und Prompt-Version | Art. 6 Abs. 1 lit. f | **offen:** IP-Kürzung und 14-Tage-Rotation beim Hosting umsetzen |

Ausgeschlossen sind in Phase I: Analytics, Tracking, Marketing-Cookies und das Training mit Nutzerdaten.

## LLM-Anbieter (Auftragsverarbeitung, Art. 28; Drittlandtransfer, Art. 44 ff.)

- Der Anbieter wird über ENV konfiguriert (ADR-0003). Vor dem Produktiveinsatz sind erforderlich:
  - [ ] AV-Vertrag. OpenRouter bietet ihn nur Enterprise-Kunden an. Die Upstream-Anbieter sind
    Unterauftragsverarbeiter.
  - [ ] Zero Data Retention bzw. kein Training vertraglich zusichern lassen.
  - [ ] EU-Verarbeitung bevorzugen. Optionen: Mistral, Azure OpenAI EU Data Zone, STACKIT, Scaleway,
    AWS Bedrock EU.
  - [ ] Bei US-Anbietern: Zertifizierung unter dem Data Privacy Framework prüfen. Das DPF ist gültig,
    die Revision C-703/25 P beim EuGH ist anhängig. Als Fallback Standardvertragsklauseln plus
    Transfer-Folgenabschätzung vorsehen.
- **Datenminimierung:** `compliance.redaction` entfernt vor dem Prompt E-Mail-Adressen,
  Telefonnummern, IBANs und Straßenadressen (Heuristik). Es wird nur die Projektzusammenfassung
  übergeben, keine Kontodaten.

## Cookies (§ 25 TDDDG)

Gesetzt wird nur das Session-Cookie (technisch notwendig, `HttpOnly`, `Secure`, `SameSite=Lax`).
Ein Consent-Banner ist deshalb nicht nötig. Sobald Analytics hinzukommt, ist eine Consent-Management-
Plattform Pflicht.

## Vorlage für die Datenschutz-Folgenabschätzung (Art. 35), vor dem Go-Live ausfüllen

1. Systematische Beschreibung der Verarbeitung und der Zwecke
2. Notwendigkeit und Verhältnismäßigkeit
3. Risiken für Betroffene, z. B. sensible Angaben in Freitext-Prompts oder Adressen von Grundstücken
4. Abhilfemaßnahmen: Redaction, Löschfristen, EU-Provider, Verschlüsselung, Zugriffskontrolle
5. Stellungnahme des Datenschutzbeauftragten
6. Datum und Version der Prüfung

## Betroffenenrechte

- Datenexport: `GET /api/projects/{id}/export` liefert Modell und Command-Log als JSON. Das unterstützt
  auch die Wechselregeln des Data Act [?].
- Löschung: Löschen des Kontos bzw. Projekts entfernt Projekte, Commands und Chat (hartes Löschen).
