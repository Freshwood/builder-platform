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

# Aktueller Schwerpunkt (2026-10-14)

Diese drei Leitsätze haben Vorrang vor allen folgenden Schritten. Wo ältere Abschnitte ihnen
widersprechen, gelten die Leitsätze ([ADR-0008](docs/architecture/adr/archiv/0008-unikate-statt-packs.md)).

## 1. Jedes Projekt ist ein Unikat

Es gibt **keine Construction Packs und keine Vorlagen**. Ein Unikat kann nicht aus einem Paket
stammen, sonst sieht jedes Ergebnis gleich aus.

Die KI hat stattdessen die **handwerkliche Fertigkeit**, aus der Angabe des Kunden einen eigenen,
fertigen und brauchbaren Entwurf zu erstellen: Bauteile, Maße als Ausdrücke, Verbindungen,
Bauschritte. Die Engine prüft den Entwurf und leitet alles Weitere ab. Die KI rechnet dabei nie.

```text
Kundenangabe ──▶ KI entwirft frei (Unikat) ──▶ Engine prüft ──▶ Engine leitet ab
                                                  │                ├── 3D-Modell
                                                  │                ├── Zeichnungen (SVG/PDF)
                                                  └─ Fehler ──▶ KI ├── Stückliste, Zuschnitt
                                                     korrigiert    ├── Kosten
                                                                   └── Bauanleitung
```

## 2. 3D-Modell aus Vektorgrafiken – günstig und tokenarm

Das 3D-Modell entsteht auf einfache Weise aus Vektorprofilen:

```text
Bauteil = 2D-Vektorprofil (Polygon/Pfad, Maße als Ausdrücke)
        + Stärke / Extrusionsrichtung
        + Lage im Projekt
              ↓  Engine (deterministisch)
        Extrusion → 3D-Körper → Ansichten, Bemaßung, Stückliste, Zuschnitt
```

- Der Quader ist nur ein Sonderfall des Profils (Rechteck × Stärke).
- 3D-Modell und 2D-Zeichnungen kommen aus **derselben Geometrie**; sie können sich nicht
  widersprechen.
- **Tokenoptimiert:** ein Tool-Aufruf pro Entwurf, kompakte Profilsyntax, keine Katalog- oder
  Vorlagenlisten im Prompt, Großdaten nur auf Abruf. Jede Änderung wird mit `task bench` gemessen,
  das Token-Budget darf nur sinken.
- Kein Bildmodell, kein CAD-Kernel: die Extrusion ist einfache, prüfbare Mathematik in der Engine.

## 3. Wasserdichte Verträge zwischen KI und Engine

Der Entwurf eines Projekts darf nie fehlerhaft beim Nutzer ankommen. Dafür sind die Verträge
zwischen KI-Agent(en) und Engine fest definiert:

1. **Ein Schema als einzige Quelle** (`AssemblyDesign`, keine unbekannten Felder), versioniert.
   Wo der Provider es kann, wird es als Strict-/Structured-Output erzwungen.
2. **Feste Prüfkette:** zentrale Reparatur von Tool-Argumenten → Schemaprüfung → Ausdrücke →
   Auflösung → Konstruktionsprüfung (Material, Querschnitt, Durchdringung, Zusammenhang,
   Auflager, Verbindungen) → Ableitung.
3. **Jede Ablehnung ist maschinenlesbar:** Fehlercode, genauer Pfad im Entwurf, konkreter
   Korrekturvorschlag. Die KI muss nicht raten.
4. **Begrenzte Reparaturschleife.** Gelingt die Korrektur nicht, bekommt der Nutzer eine klare
   Rückfrage statt eines kaputten Entwurfs.
5. **Vertragstests:** Entwurfs-Corpus, Property-Tests, Sammlung fehlerhafter Tool-Argumente. Jeder
   gemeldete Fehler wird ein Regressionsfall. Die Live-Evaluation mit Erfolgsquote ist Gate für
   jede Prompt- oder Schemaänderung.

> **Harte Garantie:** Kein ungeprüfter oder fehlerhafter Entwurf erreicht den Nutzer.
>
> Die Ausgabe eines Sprachmodells selbst ist nie garantiert fehlerfrei. Garantiert wird, dass
> die Engine jeden Fehler erkennt, die KI ihn gezielt korrigiert und nichts Fehlerhaftes
> ausgeliefert wird.

## Nächste Meilensteine

| # | Meilenstein | Ergebnis |
|---:|---|---|
| 1 | Packs und Vorlagen entfernt | Jeder Entwurf entsteht frei aus der Kundenangabe |
| 2 | Profil-Bauteil (Vektorprofil + Extrusion) im Schema | 3D aus Vektorgrafik, Quader als Sonderfall |
| 3 | Maschinenlesbare Fehlercodes in der Prüfkette | Gezielte Korrektur, weniger Reparaturrunden |
| 4 | Strict-/Structured-Output für den Entwurfs-Aufruf | Formfehler kommen gar nicht erst an |
| 5 | Erfolgsquote der Live-Evaluation als Release-Gate | Messbar fehlerfreie Entwürfe |

---

---

# Die 10 Schritte (Kurzfassung)

| # | Schritt | Kern |
|---:|---|---|
| 1 | Private DIY-Agent-Plattform | Beschreibung → Entwurf → Stückliste, Kosten, Zeichnung, Anleitung (**aktuell**) |
| 2 | Echtes Bauprojektmodell | Eingaben plus Command-Log, Versionen, Provenance |
| 3 | Konstruktions- und Berechnungskern | Das LLM beschreibt, die Engine rechnet |
| 4 | Dokumente und Pläne | Zeichnungen, Zuschnitt, Anleitung, PDF |
| 5 | Produkte, Preise, Commerce | Händlerpreise, Affiliate |
| 6 | Von Planung zu Umsetzung | Dienstleister, Community, Marktplatz |
| 7 | Interoperabilität | IFC, IDS, GAEB |
| 8 | Professional Mode | Stärkere Konstruktion, Abos |
| 9 | Enterprise und öffentliche Hand | Audit, Vergabe, Provenance-Layer |
| 10 | Construction Operating System | Plattform für alle Bauvorhaben |

Details, Zielarchitektur, Produktmodi, Wirtschaftsmodell und die Compliance-Gates je Schritt:
[docs/archiv/ROADMAP-langfassung.md](docs/archiv/ROADMAP-langfassung.md) und
[docs/compliance/roadmap-gates.md](docs/compliance/roadmap-gates.md). Technischer Ist-Stand:
[docs/architecture/STRUKTUR.md](docs/architecture/STRUKTUR.md).
