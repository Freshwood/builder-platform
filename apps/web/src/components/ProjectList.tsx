"use client";

import Link from "next/link";

import { useProjects } from "@/lib/api";

export function ProjectList() {
  const { data, isLoading, error } = useProjects();
  if (isLoading) return <p className="text-muted">Projekte werden geladen …</p>;
  if (error) return <p role="alert">Die Projekte konnten nicht geladen werden.</p>;
  if (!data?.length) {
    return (
      <p className="text-muted">
        Noch keine Projekte.{" "}
        <Link href="/" className="underline">
          Starte jetzt dein erstes Vorhaben.
        </Link>
      </p>
    );
  }
  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {data.map((project) => (
        <li key={project.id}>
          <Link
            href={`/projects/${project.id}`}
            className="block rounded-xl border border-border bg-surface p-4 hover:bg-surface-muted"
          >
            <span className="block font-semibold">{project.title}</span>
            <span className="block text-sm text-muted">{project.summary}</span>
            {project.updated_at && (
              <span className="mt-2 block text-xs text-muted">
                Zuletzt geändert {new Date(project.updated_at).toLocaleString("de-DE")}
              </span>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
}
