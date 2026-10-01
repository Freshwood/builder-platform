import type { Metadata } from "next";

import { ProjectList } from "@/components/ProjectList";

export const metadata: Metadata = { title: "Meine Projekte – Homeworking" };

export default function ProjectsPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Meine Projekte</h1>
      <ProjectList />
    </div>
  );
}
