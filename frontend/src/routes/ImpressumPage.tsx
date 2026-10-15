import { useDocumentTitle } from "@/lib/title";

// Placeholder: must be completed with the operator's details (§ 5 DDG) before going live.
export function ImpressumPage() {
  useDocumentTitle("Impressum – Homeworking");
  return (
    <article className="mx-auto max-w-2xl space-y-3 px-4 py-10">
      <h1 className="text-2xl font-bold">Impressum</h1>
      <p className="rounded-md bg-warning-soft p-3 text-sm text-warning">
        Platzhalter – vor Veröffentlichung mit den Angaben nach § 5 DDG ausfüllen.
      </p>
      <p>
        [Name/Firma, Rechtsform, Vertretungsberechtigte]
        <br />
        [Anschrift]
        <br />
        [E-Mail, Telefon]
        <br />
        [Registergericht, Registernummer, USt-IdNr.]
      </p>
    </article>
  );
}
