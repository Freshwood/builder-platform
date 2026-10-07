# Homeworking DIY Platform – Entwicklungsroadmap

## Vision

**Homeworking** ist eine zentrale Plattform für Bauvorhaben aller Größenordnungen – vom privaten DIY-Projekt bis zum professionellen und öffentlichen Bauvorhaben.

Der Nutzer beschreibt, **was gebaut, repariert oder verändert werden soll**. Die Plattform unterstützt ihn bei:

- Planung
- Variantenbildung
- Konstruktion
- Berechnung
- Materialauswahl
- Kostenschätzung
- Einkauf
- Bauanleitung
- Skizzen und technischen Dokumenten
- Beauftragung von Dienstleistungen
- Dokumentation
- später BIM, Ausschreibung und professionellen Workflows

Der zentrale technische Grundsatz lautet:

> **Das Bauvorhaben ist das zentrale Objekt. Der Agent ist nur die intelligente Bedienoberfläche.**

Dadurch kann dieselbe zugrunde liegende Projektdatenstruktur schrittweise von DIY über Professional bis Enterprise/Public erweitert werden.

---

# Die 10 Schritte

## 1. Private DIY-Agent-Plattform

### Ziel

Ein extrem einfacher Einstieg für Privatpersonen.

Startseite:

> **Was möchtest du bauen oder reparieren?**

Der Benutzer beschreibt sein Vorhaben in natürlicher Sprache.

Beispiel:

> „Ich möchte eine 5 × 4,5 m große Holzterrasse auf einem etwa 60 cm höheren Gelände bauen.“

Der Agent:

1. versteht die Aufgabe
2. erkennt fehlende Informationen
3. stellt Rückfragen
4. erzeugt mehrere sinnvolle Varianten
5. schlägt eine Konstruktion vor
6. erstellt Maße und Skizzen
7. berechnet Materialmengen
8. erstellt eine Materialliste
9. schätzt Kosten
10. erzeugt eine vollständige Bauanleitung

### Ergebnis

Zum Beispiel:

```text
Projekt: Terrasse 5,0 × 4,5 m

Variante A
- Holz-Unterkonstruktion
- definierte Trägerabstände
- definierte Fundamente
- Geländer optional

Material
- KVH
- Terrassendielen
- Schrauben
- Verbinder
- Fundamente

Kosten
- Material: ca. X–Y €
- Werkzeuge: ca. X–Y €
- Fremdleistungen: optional

Dokumente
- Gesamtplan
- Draufsicht
- Seitenansicht
- Detailzeichnungen
- Materialliste
- Zuschnittliste
- Bauanleitung
```

### MVP-Technologie

```text
Frontend       Next.js / React
Backend        Python + FastAPI
AI             OpenAI-compatible API
LLM Gateway    OpenRouter / eigener Gateway
Database       PostgreSQL
Vector Search  pgvector
Storage        S3-kompatibel
Drawings       SVG / Canvas
PDF            serverseitige PDF-Erzeugung
```

### Bewusst noch nicht

- Kubernetes
- Microservices
- vollständiges CAD
- BIM
- Marketplace
- mobile Apps
- komplexe Unternehmensrollen
- vollständige Statik

### Erfolgsbedingung

Ein Nutzer kann aus einer einfachen Problembeschreibung innerhalb weniger Minuten einen **brauchbaren ersten Lösungsvorschlag** erhalten.

---

# 2. Das echte Bauprojektmodell

Jetzt wird Homeworking von einem Chat-Tool zu einer Plattform.

Das Ergebnis des Dialogs wird als strukturiertes Projekt gespeichert.

Beispiel:

```text
Project
├── Requirements
├── Constraints
├── Components
├── Materials
├── Quantities
├── Geometry
├── Calculations
├── Risks
├── Documents
├── Instructions
└── Sources
```

## Wichtiger Grundsatz

Das Projektmodell ist die **Single Source of Truth**.

Nicht:

```text
Chat → Text → PDF
```

Sondern:

```text
User
  ↓
Agent
  ↓
Project Model
  ├── Geometry
  ├── Components
  ├── Materials
  ├── Calculations
  └── Documents
```

### Änderbarkeit

Der Nutzer kann sagen:

> „Mach die Terrasse 50 cm breiter.“

Das System aktualisiert:

- Geometrie
- Bauteile
- Mengen
- Material
- Kosten
- Zeichnungen
- Anleitung

Dadurch wird das Projekt **parametrisch veränderbar**.

---

# 3. Konstruktions- und Berechnungskern

Ab diesem Schritt entsteht der wichtigste technische Differenzierungsfaktor.

Der LLM soll **nicht alleine rechnen**.

Stattdessen:

```text
LLM
 ↓
Construction Planner
 ↓
Rule / Calculation Engine
 ├── Geometry
 ├── Dimensions
 ├── Loads
 ├── Materials
 ├── Connections
 ├── Quantities
 └── Constraints
```

## Aufgabenverteilung

### LLM

- Anforderungen verstehen
- Varianten erzeugen
- Fragen stellen
- Planungsentscheidungen erklären
- Lösungsmöglichkeiten formulieren

### Deterministische Engine

- Geometrie
- Mengen
- Formeln
- Kosten
- Abhängigkeiten
- Plausibilitätsprüfungen
- technische Regeln

## Modusmodell

### DIY

Einfach und verständlich.

> „Wie kann ich das selbst bauen?“

### Guided

Schritt-für-Schritt-Begleitung.

> „Führe mich durch den Bau.“

### Professional

Mehr technische Parameter.

- detaillierte Bauteile
- Berechnungen
- Varianten
- BOM
- technische Dokumente

### Engineering

Für anspruchsvolle professionelle Anwendungen.

- Lastannahmen
- Materialkennwerte
- Regeln / Normen
- technische Nachweise
- Prüfungen
- Audit Trail

**Sicherheitskritische oder genehmigungspflichtige Konstruktionen dürfen nicht als automatisch prüffähige Statik ausgegeben werden.**

---

# 4. Automatische Dokument- und Planerzeugung

Aus dem Projektmodell werden automatisch vollständige Unterlagen erzeugt.

## Technische Dokumente

```text
Gesamtansicht
Draufsicht
Vorderansicht
Seitenansicht
Schnitt
Detailzeichnungen
Explosionsansicht
```

## Material

```text
Position
Menge
Einheit
Spezifikation
```

## Zuschnitt

```text
Bauteil      Anzahl      Länge
Pfosten      12          2400 mm
Querträger   18          3600 mm
...
```

## Anleitung

```text
1. Untergrund vorbereiten
2. Fundament herstellen
3. Pfosten setzen
4. Unterkonstruktion montieren
5. Belag montieren
6. Geländer montieren
7. Endkontrolle
```

## Technisches Prinzip

Maßhaltige Zeichnungen werden **nicht primär durch ein Bildmodell erzeugt**.

Sondern:

```text
Construction Model
       ↓
Parametric Geometry
       ↓
SVG / DXF / PDF
```

Generative Bildmodelle können später für illustrative Darstellungen verwendet werden.

---

# 5. Produkte, Preise und Affiliate-Commerce

Jetzt entsteht der erste große kommerzielle Hebel.

Die Materialliste wird auf konkrete Produkte abgebildet.

Beispiel:

```text
Benötigt:
KVH 60 × 120 × 4000 mm
Menge: 12
```

Homeworking sucht passende Produkte bei:

- Baumärkten
- Onlineshops
- Spezialhändlern
- Werkzeughändlern
- Mietplattformen

## Ziel

```text
Projekt
 ↓
BOM
 ↓
Produkt-Matching
 ↓
Preis / Verfügbarkeit
 ↓
Warenkorb
 ↓
Affiliate / Partner
```

## Potenzielle Kategorien

- Holz
- Beton
- Schrauben
- Verbindungsmittel
- Werkzeuge
- Maschinen
- Mietgeräte
- Baustoffe
- Transport
- Schutzkleidung

## Strategischer Vorteil

Die Werbung ist **nicht losgelöst vom Nutzerinteresse**.

Sie entsteht aus einem konkreten Bedarf:

> „Du brauchst 18 m² Terrassendielen.“

→ konkrete passende Produkte.

---

# 6. Von Planung zu Umsetzung

Jetzt wird Homeworking vom Planer zur Vermittlungsplattform.

Der Benutzer entscheidet:

```text
☑ Ich mache es selbst
☑ Ich brauche Unterstützung
☑ Ich möchte es komplett vergeben
```

Das Projekt wird automatisch in Leistungen zerlegt:

```text
Terrasse
├── Erdarbeiten
├── Fundament
├── Holzbau
├── Geländer
└── Oberflächenbehandlung
```

Daraus entstehen Services:

```text
Minibagger mieten
Material liefern lassen
Handwerker finden
Statiker finden
Montage beauftragen
Container bestellen
```

## Plattformmodell

Homeworking muss nicht selbst:

- Handwerker beschäftigen
- Maschinen besitzen
- Material verkaufen

Die Plattform kann die notwendigen Leistungen **orchestrieren**.

Dadurch wird die Plattform für Partner wertvoll.

## Community-Bibliothek, Forks und Marktplatz (Ausblick)

Jedes Projekt hat einen vollständigen Versionsverlauf, und jedes KI-Ergebnis ist gespeichert
([ADR-0005](docs/architecture/adr/0005-versionen-und-gespeicherte-ki-laeufe.md)). Darauf lässt sich
eine Community aufbauen:

```text
Privates Projekt ──veröffentlichen──▶ Community-Bibliothek (kostenlos, mit Lizenz, z. B. CC BY-SA)
                                         │
                                         ├── forken: eigene Kopie mit Herkunftsverweis, weiter verbessern
                                         ├── bewerten, kommentieren, „gebaut“-Fotos
                                         └── gute Forks fließen als Vorlage zurück (kuratiert)

Besonderes Projekt ──verkaufen──▶ Marktplatz (Ersteller legt Preis fest, Plattform erhält Provision)
```

- **Veröffentlichen:** Ein Projekt (bzw. eine bestimmte Version) wird öffentlich; private Daten wie
  Region, eigene Preise und Chatverlauf bleiben privat.
- **Forken:** Kopie inklusive Entwurf und Parametern, mit Verweis auf das Original und dessen
  Version (Provenance). Zeichnungen, Stückliste und Kosten rechnet die Engine für den Fork neu.
- **Kosten sparen:** Ein veröffentlichter Entwurf ersetzt teure KI-Läufe – wer etwas Ähnliches
  bauen will, startet vom Fork statt vom leeren Chat. Der Agent kann passende Community-Projekte
  vorschlagen, bevor er frei entwirft.
- **Verkaufen:** Ersteller bieten besondere Pläne kostenpflichtig an; die Plattform verdient über
  eine Provision.
- **Compliance (Gate 6):** Nutzungsbedingungen mit Lizenz für geteilte Inhalte, Moderation und
  Meldeweg (DSA), Ranking-Transparenz (P2B-VO), Meldepflichten für Verkäufer (DAC7),
  Verbraucherrechte bei digitalen Inhalten, klare Haftungshinweise (Planungshilfe, kein
  Standsicherheitsnachweis) auch für verkaufte Pläne.

---

# 7. Interoperabilitäts-Layer

Das ist ein zentraler langfristiger Plattformvorteil.

Homeworking bekommt ein neutrales internes Bauprojektmodell:

```text
Homeworking Construction Model
```

Dazu kommen Adapter:

```text
                HOMEWORKING
                     │
      ┌──────────────┼──────────────┐
      ↓              ↓              ↓
     BIM          Einkauf        Services
      │              │              │
     IFC            APIs          Partner
     IDS
     BCF
```

## Relevante Standards

### IFC

Für offenen, herstellerneutralen BIM-Datenaustausch.

### IDS

Für maschinenlesbare Informationsanforderungen und automatisierbare Prüfungen.

### GAEB

Für strukturierte Bau-Austauschprozesse wie:

- Leistungsverzeichnisse
- Ausschreibungen
- Angebote
- Aufträge
- Mengenermittlung

### Beispiel

```text
Homeworking
   ↓
Projekt
   ↓
Leistungsverzeichnis
   ↓
GAEB
   ↓
Handwerker-Software
   ↓
Angebot
   ↓
Homeworking
   ↓
Vergleich
```

Die Integration sollte als **Adapter-Layer** gebaut werden, nicht als Kernlogik.

---

# 8. Professional Mode

Jetzt wird aus dem DIY-Produkt eine professionelle Plattform.

Beispiel:

> Ein Unternehmen baut 35 identische Carports.

Das Projekt wird Teil eines Projektportfolios.

```text
Portfolio
├── Projekt 001
├── Projekt 002
├── Projekt 003
└── ...
```

## Funktionen

- Multi-User
- Rollen
- Berechtigungen
- Freigaben
- Versionierung
- Audit Trail
- BOM
- Kosten
- Termine
- Dokumente
- Ausschreibung
- Lieferanten
- Qualitätsprüfung

## Stärkerer Konstruktionsmodus

```text
Professional
 ├── parametrische Konstruktion
 ├── detaillierte Geometrie
 ├── technische Parameter
 ├── Materialeigenschaften
 └── automatisierte Prüfungen
```

---

# 9. Enterprise und öffentliche Hand

Jetzt kann das System den gesamten Lebenszyklus eines größeren Bauvorhabens abbilden.

Beispiel:

```text
Schulsanierung
     ↓
Bestandsaufnahme
     ↓
Varianten
     ↓
Kosten
     ↓
Ausschreibung
     ↓
Vergabe
     ↓
Bauausführung
     ↓
Dokumentation
     ↓
BIM / Asset
     ↓
Facility Management
```

## Enterprise-Funktionen

- Mandantenfähigkeit
- SSO
- RBAC
- Audit Logs
- Freigabeworkflows
- API
- ERP-Integration
- DMS
- BIM
- Ausschreibung
- Lieferantenmanagement
- Reporting

## Provenance-Layer

Jede relevante Entscheidung soll nachvollziehbar sein:

```text
Requirement
 ↓
Decision
 ↓
Calculation
 ↓
Model Element
 ↓
Material
 ↓
Supplier
 ↓
Execution
```

Damit ist nachvollziehbar:

- warum etwas so geplant wurde
- welche Annahmen verwendet wurden
- welche Daten zugrunde lagen
- welche Version aktiv war
- wer freigegeben hat

---

# 10. Homeworking als Construction Operating System

Die langfristige Vision ist nicht:

> „Homeworking erstellt Baupläne.“

Sondern:

> **Homeworking wird die digitale Orchestrierungsschicht zwischen Idee und gebautem Objekt.**

```text
                    HOMEWORKING
                         │
           ┌─────────────┴─────────────┐
           │                           │
        PRIVATE                   PROFESSIONAL
           │                           │
        DIY Mode                  Engineering
           │                           │
      Guided Mode                 Enterprise
           │                           │
           └─────────────┬─────────────┘
                         │
                  PROJECT MODEL
                         │
     ┌─────────┬─────────┼─────────┬─────────┐
     ↓         ↓         ↓         ↓         ↓
   Design   Calculate    Buy      Build    Document
     ↓         ↓         ↓         ↓         ↓
    CAD       Rules     Shops   Services     BIM
```

Darüber:

```text
                  HOMEWORKING API
                        │
       ┌────────────────┼────────────────┐
       ↓                ↓                ↓
    CAD/BIM          Händler          Services
       ↓                ↓                ↓
      ERP             Shops          Behörden
```

Damit wird Homeworking zum **Orchestrator**, nicht zwangsläufig selbst:

- Hersteller
- Baumarkt
- Handwerksbetrieb
- Planungsbüro
- Vermieter
- Behördenportal

---

# Technische Zielarchitektur

## Frontend

```text
Next.js
React
TypeScript
```

## Backend

```text
Python
FastAPI
Pydantic
```

## Data Layer

```text
PostgreSQL
pgvector
Object Storage
```

## AI Layer

```text
OpenAI-compatible Gateway
        ↓
OpenRouter
OpenAI
Azure OpenAI
Ollama
vLLM
andere Provider
```

## Core Services

```text
Project Service
Construction Engine
Calculation Engine
Material Service
Pricing Service
Document Generator
Knowledge / RAG
Integration Layer
Identity / Access
```

Zu Beginn können diese Komponenten in **einem modularen Monolithen** laufen.

Erst bei realem Bedarf werden einzelne Bereiche herausgelöst.

---

# Zentrales Domänenmodell

Das Kernmodell sollte ungefähr so aussehen:

```text
Project
├── Identity
├── Requirements
├── Constraints
├── Locations
├── Components
│   ├── Geometry
│   ├── Material
│   ├── Properties
│   └── Connections
├── Calculations
├── Quantities
├── Products
├── Suppliers
├── Services
├── Tasks
├── Costs
├── Risks
├── Documents
├── Models
├── Versions
├── Decisions
└── Provenance
```

Dieses Modell ist wichtiger als die konkrete AI-Technologie.

---

# Die verschiedenen Produktmodi

Alle Modi verwenden dasselbe Projektmodell.

## Private DIY

```text
Einfach
Preiswert
Verständlich
Schritt für Schritt
```

## Guided

```text
Mehr Erklärungen
Checklisten
Fehlervermeidung
```

## Professional

```text
Parameter
BOM
Kosten
Versionierung
Technische Dokumente
```

## Engineering

```text
Berechnungen
Regeln
Materialdaten
Nachweise
Validierung
Audit
```

## Enterprise/Public

```text
Multi-User
Workflow
Freigaben
BIM
GAEB
ERP
DMS
API
SSO
Audit
```

---

# Was NICHT in Schritt 1 gebaut werden sollte

```text
❌ vollständiges CAD-System
❌ komplette Statikplattform
❌ vollständige BIM-Suite
❌ eigener LLM
❌ Mobile App
❌ Handwerker-Marktplatz
❌ Behördenplattform
❌ ERP
❌ 100 Gewerke
❌ Microservice-Architektur
❌ Kubernetes
```

Die erste Version soll nur eine Sache außergewöhnlich gut machen:

> **„Ich habe ein konkretes Bauproblem. Homeworking versteht es und liefert mir einen brauchbaren, umsetzbaren Plan.“**

---

# Empfohlene erste Domänen

Der MVP sollte nicht wirklich „alles“ können.

Der interne Datenstandard kann universal sein.

Die ersten Construction Packs sollten beispielsweise sein:

```text
Terrasse
Carport
Gartenhaus
Schuppen
Zaun
Hochbeet
Werkbank
Regal
Holzunterkonstruktion
Spielgeräte
```

Danach:

```text
Wood
Metal
Concrete
Masonry
Interior
Garden
Electrical
Plumbing
Roofing
HVAC
Industrial
Civil
```

---

# Wirtschaftliches Modell

## Private

Freemium / günstiges Abo.

```text
Free
├── einfache Planung
└── begrenzte Projekte

Premium
├── unbegrenzte Projekte
├── bessere Modelle
├── Dokumente
├── Varianten
└── erweiterte Berechnungen
```

## Commerce

Affiliate / Provisionen:

```text
Material
Werkzeug
Maschinen
Lieferung
Mietgeräte
Services
```

## Professional

Monatliches Abo.

```text
Professional
├── Projekte
├── Berechnungen
├── Dokumentation
├── BIM
├── Ausschreibung
└── Zusammenarbeit
```

## Enterprise

```text
Enterprise
├── API
├── SSO
├── RBAC
├── On-Prem / Private Cloud
├── Integrationen
├── Audit
└── individuelle Workflows
```

---

# Wichtigste technische Differenzierung

Homeworking sollte nicht primär als:

> „KI plant dein Bauprojekt.“

positioniert werden.

Der stärkere Kern ist:

> **Aus einer natürlichen Beschreibung entsteht ein veränderbares, berechenbares und ausführbares Bauprojekt.**

Also:

```text
„Ich möchte eine Terrasse.“
           ↓
     Anforderungen
           ↓
      Konstruktion
           ↓
       Geometrie
           ↓
      Berechnung
           ↓
          BOM
           ↓
    konkrete Produkte
           ↓
       Preis
           ↓
      Bauanleitung
           ↓
      Dienstleister
           ↓
    Dokumentation
```

Und:

> „Mach sie 50 cm breiter.“

führt nicht zu einer neuen Chat-Antwort, sondern zu einer **konsistenten Änderung des gesamten Projekts**.

---

# Priorisierung der 10 Schritte

| Schritt | Schwerpunkt | Ergebnis |
|---:|---|---|
| 1 | Private AI-DIY | Erster echter Nutzerwert |
| 2 | Projektmodell | Persistente Bauprojekte |
| 3 | Construction Engine | Technischer Kern |
| 4 | Dokumente & Zeichnungen | Umsetzbare Pläne |
| 5 | Produkte & Affiliate | Erste Monetarisierung |
| 6 | Services & Umsetzung | Marktplatz-Orchestrierung |
| 7 | Interoperabilität | Standards & Integrationen |
| 8 | Professional | Unternehmensnutzung |
| 9 | Enterprise/Public | Große Bauvorhaben |
| 10 | Construction OS | Plattform & Ökosystem |

---

# Empfohlene Reihenfolge der Investitionen

```text
             USER VALUE
                 ↑
                 │
      1 ──────── 2
       \\          /
        \\        /
         3 ──── 4
              │
              5
              │
              6
              │
              7
              │
          8 ── 9
              │
             10
                 → PLATFORM
```

Die wichtigste Regel lautet:

> **Nicht versuchen, Schritt 10 früh zu bauen.**
>
> **Aber Schritt 10 bereits in den Daten- und Integrationsentscheidungen von Schritt 1 berücksichtigen.**

So bleibt das Produkt am Anfang einfach und günstig, ohne später in eine Sackgasse zu laufen.

---

# MVP-Zielbild für den ersten Release

Ein Nutzer kommt auf Homeworking und schreibt:

> „Ich möchte für meine Kinder einen 2,5 × 2 m großen Holz-Spielschuppen bauen. Er soll ein Pultdach haben und möglichst günstig sein.“

Nach wenigen Minuten erhält er:

```text
✓ 3 Konstruktionsvarianten
✓ Maße
✓ 2D-Skizzen
✓ Materialliste
✓ Zuschnittliste
✓ Werkzeugliste
✓ Kostenschätzung
✓ Schritt-für-Schritt-Bauanleitung
✓ Sicherheits-/Risiko-Hinweise
✓ alternative günstigere Konstruktion
✓ konkrete Produkte
✓ gespeichertes Projekt
```

Das ist das **erste Produkt**.

Der Rest ist die Evolution dieses Projekts zu einer universellen Bauplattform.

---

# Ergänzung (2026-10-01): Umsetzungsentscheidungen und Compliance-Gates

## Anpassungen für Phase I

1. **Schritt 1 und 2 zusammengezogen:** Projektmodell und Command-Log gibt es ab dem ersten Release
   ([ADR-0002](docs/architecture/adr/0002-projektmodell-und-command-log.md)).
2. **Schritt 3 für genau ein Pack in Phase I:** Mengen und Kosten kommen von Anfang an aus der
   deterministischen Engine.
3. **Erstes Construction Pack ist das Hochbeet:** statisch unkritisch, genehmigungsfrei, deckt aber die
   ganze Kette ab: Geometrie, BOM, Zuschnitt, SVG, PDF, Kosten. Danach folgen Terrasse und Schuppen.
4. **Der Agent mutiert nur über typisierte Commands.** Daraus ergibt sich die Provenance aus Schritt 9
   von Beginn an.
5. **Bauteile bekommen stabile GUIDs und IFC-nahe Typen.** Damit ist Schritt 7 später nur ein Adapter.
6. **Compliance ist ein eigenes Modul:** Sicherheitsklassifikator, Hinweisbausteine, KI-Kennzeichnung,
   versionierte Regeln.

## Compliance-Gates

Jeder Schritt hat ein Compliance-Gate, siehe [docs/compliance/roadmap-gates.md](docs/compliance/roadmap-gates.md).

| Schritt | Gate (Kurzform) |
|---:|---|
| 1–2 | AI Act Art. 50, DSGVO/AV-Vertrag mit LLM-Anbieter, § 5 DDG, § 25 TDDDG, AGB, WCAG 2.2 AA |
| 3–4 | Fachliche Regelvalidierung, keine Normtexte, „kein Standsicherheitsnachweis“, PDF/UA |
| 5 | UWG § 5a/5b, PAngV, EmpCo |
| 6 | P2B-VO, DSA, DAC7 |
| 7 | Lizenzen der Standards, Data Act |
| 8 | Abo-Buttons (§§ 312j, 312k, 356a BGB), Audit |
| 9 | AI-Act-Neubewertung, Vergaberecht, NIS2, ISO 27001/C5 |
| 10 | Data Act, CRA |
