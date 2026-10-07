"use client";

import type { VersionEntry } from "@homeworking/api-client";
import clsx from "clsx";

import { Icon, Spinner } from "@/components/ui";
import { formatEur, useVersions } from "@/lib/api";

const TIME = new Intl.DateTimeFormat("de-DE", { dateStyle: "short", timeStyle: "short" });

function cost(entry: VersionEntry): string | null {
  if (!entry.material_cost) return null;
  const [min, max] = entry.material_cost;
  return `${formatEur(min)} – ${formatEur(max)}`;
}

/** All versions of a project, newest first; selecting one shows it read-only. */
export function VersionHistory({
  projectId,
  selected,
  onSelect,
}: {
  projectId: string;
  selected: number | null;
  onSelect: (seq: number | null) => void;
}) {
  const { data, isLoading, error } = useVersions(projectId);
  return (
    <section
      aria-labelledby="versions-heading"
      className="rounded-3xl border border-border bg-surface p-4 shadow-sm"
      data-testid="version-history"
    >
      <div className="flex items-baseline justify-between gap-2">
        <h3 id="versions-heading" className="font-semibold">
          Verlauf
        </h3>
        <p className="text-xs text-muted">
          Jede Änderung bleibt gespeichert – auch jedes KI-Ergebnis.
        </p>
      </div>
      {isLoading && (
        <p className="mt-3 flex items-center gap-2 text-sm text-muted">
          <Spinner /> Lade Versionen …
        </p>
      )}
      {error && (
        <p className="mt-3 text-sm text-warning">Der Verlauf konnte nicht geladen werden.</p>
      )}
      <ol className="scrollbar-thin mt-3 max-h-80 space-y-1 overflow-y-auto pr-1">
        {data?.map((entry) => {
          const active = entry.current ? selected === null : selected === entry.seq;
          return (
            <li key={entry.seq}>
              <button
                type="button"
                onClick={() => onSelect(entry.current ? null : entry.seq)}
                aria-current={active ? "true" : undefined}
                className={clsx(
                  "flex w-full items-start gap-3 rounded-xl px-3 py-2 text-left text-sm transition",
                  active ? "bg-accent-soft ring-1 ring-accent/40" : "hover:bg-surface-muted",
                )}
              >
                <span
                  className={clsx(
                    "mt-0.5 shrink-0 rounded-md px-1.5 font-mono text-xs",
                    entry.construction ? "bg-text text-bg" : "bg-surface-muted text-muted",
                  )}
                >
                  V{entry.seq}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block break-words font-medium">{entry.label}</span>
                  <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
                    <span className="inline-flex items-center gap-1">
                      {entry.actor === "agent" ? (
                        <>
                          <Icon name="sparkles" className="h-3 w-3" /> KI
                        </>
                      ) : (
                        "Du"
                      )}
                    </span>
                    {entry.created_at && <span>{TIME.format(new Date(entry.created_at))}</span>}
                    {cost(entry) && <span>{cost(entry)}</span>}
                    {entry.current && (
                      <span className="rounded-full bg-success-soft px-1.5 font-medium text-success">
                        aktuell
                      </span>
                    )}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
