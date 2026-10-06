import type { Metadata } from "next";

import { ProjectList } from "@/components/ProjectList";

export const metadata: Metadata = { title: "Meine Projekte – Homeworking" };

export default function ProjectsPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Meine Projekte</h1>
        <p className="mt-1 text-muted">
          Alles, was du geplant hast – öffne ein Projekt, um weiterzumachen.
        </p>
      </div>
      <ProjectList />
    </div>
  );
}
