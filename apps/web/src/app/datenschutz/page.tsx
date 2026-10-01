import type { Metadata } from "next";

export const metadata: Metadata = { title: "Datenschutz – Homeworking" };

// Draft based on docs/compliance/dsgvo-dpia-template.md; requires legal review before launch.
export default function DatenschutzPage() {
  return (
    <article className="max-w-2xl space-y-4">
      <h1 className="text-2xl font-bold">Datenschutzerklärung (Entwurf)</h1>
      <p className="rounded-md bg-warning-soft p-3 text-sm text-warning">
        Entwurf – vor Veröffentlichung rechtlich prüfen und Verantwortlichen ergänzen.
      </p>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Welche Daten wir verarbeiten</h2>
        <ul className="list-inside list-disc text-sm">
          <li>Ein Gastkonto mit zufälliger Kennung (Session-Cookie, technisch notwendig).</li>
          <li>Deine Projekte: Parameter, Ergebnisse und der Änderungsverlauf.</li>
          <li>
            Chat-Nachrichten werden zur Beantwortung an einen KI-Dienst übermittelt und von
            Homeworking nicht gespeichert. Erkennbare personenbezogene Angaben (E-Mail, Telefon,
            Adresse) werden vorher entfernt.
          </li>
        </ul>
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Keine Tracking-Cookies</h2>
        <p className="text-sm">
          Wir setzen ausschließlich ein technisch notwendiges Session-Cookie (§ 25 Abs. 2 TDDDG)
          und verwenden keine Analyse- oder Marketing-Dienste.
        </p>
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Deine Rechte</h2>
        <p className="text-sm">
          Du kannst jedes Projekt als JSON exportieren und löschen. Es gelten die Rechte aus Art.
          15–21 DSGVO.
        </p>
      </section>
    </article>
  );
}
