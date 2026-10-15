import { Link } from "react-router";

import { useDocumentTitle } from "@/lib/title";

export function NotFoundPage() {
  useDocumentTitle("Seite nicht gefunden – Homeworking");
  return (
    <article className="mx-auto max-w-2xl space-y-3 px-4 py-10">
      <h1 className="text-2xl font-bold">Seite nicht gefunden</h1>
      <p>
        Diese Seite gibt es nicht.{" "}
        <Link to="/" className="underline underline-offset-2">
          Zur Startseite
        </Link>
      </p>
    </article>
  );
}
