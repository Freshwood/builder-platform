"use client";

import { Icon } from "@/components/ui";

import type { Result } from "./types";

/** Key figures of the design as small tiles. */
export function Figures({ result }: { result: Result }) {
  const figures = Object.entries(result.key_figures).slice(0, 6);
  if (!figures.length) return null;
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Eckdaten">
      {figures.map(([key, value]) => (
        <li
          key={key}
          className="shrink-0 rounded-md border border-border bg-surface px-3 py-1.5 text-sm"
        >
          <span className="block text-xs text-muted">{key}</span>
          <span className="font-semibold whitespace-nowrap">{value}</span>
        </li>
      ))}
    </ul>
  );
}

/** Warnings of the engine up front, informational notes folded away. */
export function Notices({ result }: { result: Result }) {
  const warnings = result.notices.filter((n) => n.severity !== "info");
  const infos = result.notices.filter((n) => n.severity === "info");
  if (!result.notices.length) return null;
  return (
    <div className="space-y-2">
      {warnings.map((notice) => (
        <p
          key={notice.code}
          className="flex gap-2 rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-sm text-warning"
        >
          <Icon name="warning" className="h-4 w-4 translate-y-0.5" />
          <span>{notice.message}</span>
        </p>
      ))}
      {infos.length > 0 && (
        <details className="group rounded-md border border-border bg-surface px-3 py-2 text-sm">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-muted select-none">
            <Icon name="info" className="h-4 w-4" />
            <span className="flex-1">
              {infos.length} {infos.length === 1 ? "Hinweis" : "Hinweise"} zur Planung
            </span>
            <Icon name="chevronDown" className="h-4 w-4 transition group-open:rotate-180" />
          </summary>
          <ul className="mt-2 space-y-1.5 pl-6">
            {infos.map((notice) => (
              <li key={notice.code}>{notice.message}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
