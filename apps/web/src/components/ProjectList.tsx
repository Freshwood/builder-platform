"use client";

import clsx from "clsx";
import Link from "next/link";
import { useState } from "react";

import { Icon, buttonClass, relativeTime } from "@/components/ui";
import { useProjects } from "@/lib/api";

// Free designs and templates have an isometric view, packs at least a front view.
const THUMB_VIEWS = ["iso", "front"];

/** Drawing of a project as a thumbnail, falling back to an icon when no view exists. */
export function ProjectThumb({ id, className }: { id: string; className?: string }) {
  const [view, setView] = useState(0);
  const name = THUMB_VIEWS[view];
  return (
    <span
      className={clsx(
        "flex items-center justify-center overflow-hidden border border-border bg-white",
        className,
      )}
    >
      {name ? (
        // eslint-disable-next-line @next/next/no-img-element -- dynamic SVG from the API
        <img
          src={`/api/projects/${id}/drawings/${name}.svg`}
          alt=""
          loading="lazy"
          onError={() => setView(view + 1)}
          className="h-full w-full object-contain p-1"
        />
      ) : (
        <Icon name="cube" className="h-1/2 w-1/2 text-stone-400" />
      )}
    </span>
  );
}

export function ProjectList() {
  const { data, isLoading, error } = useProjects();
  const [query, setQuery] = useState("");

  if (isLoading) {
    return (
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true">
        {[0, 1, 2].map((i) => (
          <li key={i} className="h-64 animate-pulse rounded-2xl bg-surface-muted" />
        ))}
      </ul>
    );
  }
  if (error) return <p role="alert">Die Projekte konnten nicht geladen werden.</p>;

  const projects = (data ?? [])
    .slice()
    .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""));
  const needle = query.trim().toLowerCase();
  const shown = needle
    ? projects.filter((p) => `${p.title} ${p.summary}`.toLowerCase().includes(needle))
    : projects;

  if (!projects.length) {
    return (
      <div className="rounded-3xl border border-dashed border-border px-6 py-16 text-center">
        <Icon name="folder" className="mx-auto h-10 w-10 text-muted" />
        <p className="mt-3 text-lg font-semibold">Noch keine Projekte</p>
        <p className="mt-1 text-muted">
          Beschreib dein erstes Vorhaben – in einer Minute steht der Plan.
        </p>
        <Link href="/" className={clsx(buttonClass.primary, "mt-5")}>
          <Icon name="plus" className="h-4 w-4" /> Neues Projekt
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {projects.length > 3 && (
        <label className="relative block sm:max-w-sm">
          <span className="sr-only">Projekte durchsuchen</span>
          <Icon
            name="search"
            className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted"
          />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Projekte durchsuchen …"
            className="w-full rounded-xl border border-border bg-surface py-2 pr-3 pl-9 focus:border-accent focus:outline-none"
          />
        </label>
      )}
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <li>
          <Link
            href="/"
            className="flex h-full min-h-48 flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-border text-muted transition hover:border-accent/50 hover:text-accent-strong"
          >
            <Icon name="plus" className="h-8 w-8" />
            <span className="font-semibold">Neues Projekt</span>
          </Link>
        </li>
        {shown.map((project) => (
          <li key={project.id}>
            <Link
              href={`/projects/${project.id}`}
              className="group block overflow-hidden rounded-2xl border border-border bg-surface transition hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-lg"
            >
              <ProjectThumb id={project.id} className="h-40 w-full border-0 border-b" />
              <span className="block p-4">
                <span className="block font-semibold group-hover:text-accent-strong">
                  {project.title}
                </span>
                <span className="mt-0.5 line-clamp-2 block text-sm text-muted">
                  {project.summary}
                </span>
                {project.updated_at && (
                  <span className="mt-2 block text-xs text-muted">
                    Zuletzt geändert {relativeTime(project.updated_at)}
                  </span>
                )}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {needle && !shown.length && <p className="text-muted">Kein Projekt passt zu „{query}“.</p>}
    </div>
  );
}
