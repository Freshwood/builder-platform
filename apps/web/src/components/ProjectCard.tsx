"use client";

import type { ProjectListEntry } from "@/api";
import clsx from "clsx";
import Link from "next/link";
import { useState } from "react";

import { Icon, relativeTime } from "@/components/ui";

// Designs have an isometric view; the front view is the fallback.
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
        <Icon name="cube" className="h-1/2 w-1/2 text-muted" />
      )}
    </span>
  );
}

/**
 * Link to a project: ``full`` is the card of the project list (thumbnail on top, summary),
 * ``compact`` the one-line variant for the landing page.
 */
export function ProjectCard({
  project,
  variant = "full",
}: {
  project: ProjectListEntry;
  variant?: "full" | "compact";
}) {
  const href = `/projects/${project.id}`;
  if (variant === "compact") {
    return (
      <Link
        href={href}
        className="flex items-center gap-3 rounded-lg border border-border bg-surface p-2 pr-3 transition hover:border-text/40"
      >
        <ProjectThumb id={project.id} className="h-14 w-14 shrink-0 rounded-md" />
        <span className="min-w-0">
          <span className="block truncate font-semibold">{project.title}</span>
          {project.updated_at && (
            <span className="block text-xs text-muted">{relativeTime(project.updated_at)}</span>
          )}
        </span>
      </Link>
    );
  }
  return (
    <Link
      href={href}
      className="group block overflow-hidden rounded-lg border border-border bg-surface transition hover:border-text/40"
    >
      <ProjectThumb id={project.id} className="h-40 w-full border-0 border-b" />
      <span className="block p-4">
        <span className="block font-semibold group-hover:text-accent-strong">{project.title}</span>
        <span className="mt-0.5 line-clamp-2 block text-sm text-muted">{project.summary}</span>
        {project.updated_at && (
          <span className="mt-2 block text-xs text-muted">
            Zuletzt geändert {relativeTime(project.updated_at)}
          </span>
        )}
      </span>
    </Link>
  );
}
