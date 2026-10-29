"use client";

import type { ProjectModel, Solid } from "@/api";
import clsx from "clsx";
import dynamic from "next/dynamic";
import { useMemo, useRef, useState } from "react";

import { PositionBadge } from "@/components/ProjectDetails";
import { Icon, Segmented } from "@/components/ui";

const Viewer3D = dynamic(() => import("@/components/Viewer3D"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse" />,
});

type PositionRow = { number: number; name: string; material: string; tone: string; count: number };

function positions(solids: Solid[]): PositionRow[] {
  const rows = new Map<number, PositionRow>();
  for (const s of solids) {
    const row = rows.get(s.position);
    if (row) row.count += 1;
    else
      rows.set(s.position, {
        number: s.position,
        name: s.name,
        material: s.material,
        tone: s.tone,
        count: 1,
      });
  }
  return [...rows.values()].sort((a, b) => a.number - b.number);
}

type StageMode = "model" | "drawings";

/** The hero: 3D model or drawings, with floating controls and a parts legend. */
export function Stage({ project, version }: { project: ProjectModel; version: string }) {
  const result = project.result;
  const solids = useMemo(() => result.solids ?? [], [result.solids]);
  const rows = useMemo(() => positions(solids), [solids]);
  const hasModel = solids.length > 0;
  // The 3D view starts afresh (camera, scene) when the geometry parameters change, not on
  // edits such as prices.
  const modelKey = useMemo(
    () => JSON.stringify(result.effective_params),
    [result.effective_params],
  );
  const [mode, setMode] = useState<StageMode>(hasModel ? "model" : "drawings");
  const [drawing, setDrawing] = useState(0);
  const [showParts, setShowParts] = useState(true);
  const [highlight, setHighlight] = useState<number | null>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const active = rows.find((r) => r.number === highlight);
  const drawings = result.drawings;
  const current = drawings[Math.min(drawing, drawings.length - 1)];

  function fullscreen() {
    const el = stageRef.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el.requestFullscreen?.();
  }

  return (
    <section
      aria-label="Ansicht"
      ref={stageRef}
      className="stage relative overflow-hidden rounded-xl border border-border shadow-sm"
    >
      <div className="relative h-[22rem] sm:h-[30rem] lg:h-[min(62vh,40rem)]">
        {hasModel && (
          <div hidden={mode !== "model"} className="absolute inset-0">
            <Viewer3D
              key={modelKey}
              solids={solids}
              highlight={highlight}
              onHover={setHighlight}
              label={`3D-Modell: ${project.inputs.title}, ${rows.length} Positionen. Ziehen zum Drehen, Mausrad zum Zoomen.`}
            />
          </div>
        )}
        <div
          hidden={mode !== "drawings"}
          className="drawing-frame absolute inset-0 flex items-center justify-center bg-white p-4 pt-16 pb-24"
        >
          {/* Only the visible drawing is mounted: browsers fetch hidden images too, and every
              SVG is rendered by the engine on the server. */}
          {mode === "drawings" && current && (
            // eslint-disable-next-line @next/next/no-img-element -- dynamic SVG from the API
            <img
              key={current.view}
              src={`/api/projects/${project.id}/drawings/${current.view}.svg?v=${version}`}
              alt={current.description}
              className="max-h-full max-w-full object-contain"
              data-testid={`drawing-${current.view}`}
            />
          )}
        </div>

        {/* Floating top bar */}
        <div className="absolute inset-x-3 top-3 flex items-start justify-between gap-2">
          {hasModel ? (
            <Segmented<StageMode>
              label="Ansicht wählen"
              value={mode}
              onChange={setMode}
              options={[
                {
                  value: "model",
                  label: (
                    <>
                      <Icon name="cube" className="h-4 w-4" /> 3D
                    </>
                  ),
                },
                {
                  value: "drawings",
                  label: (
                    <>
                      <Icon name="image" className="h-4 w-4" /> Pläne
                    </>
                  ),
                },
              ]}
            />
          ) : (
            <span />
          )}
          <div className="flex gap-1.5">
            {mode === "model" && rows.length > 0 && (
              <button
                type="button"
                aria-pressed={showParts}
                onClick={() => setShowParts(!showParts)}
                className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface/85 px-3 py-1.5 text-sm font-medium shadow-sm backdrop-blur hover:bg-surface"
              >
                <Icon name="layers" className="h-4 w-4" />
                Bauteile
                <span className="rounded-full bg-surface-muted px-1.5 text-xs">{rows.length}</span>
              </button>
            )}
            <button
              type="button"
              onClick={fullscreen}
              aria-label="Vollbild"
              title="Vollbild"
              className="flex h-[34px] w-[34px] items-center justify-center rounded-md border border-border bg-surface/85 shadow-sm backdrop-blur hover:bg-surface"
            >
              <svg
                viewBox="0 0 24 24"
                aria-hidden="true"
                className="h-4 w-4"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.8}
                strokeLinecap="round"
              >
                <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
              </svg>
            </button>
          </div>
        </div>

        {/* Parts legend */}
        {mode === "model" && showParts && rows.length > 0 && (
          <ol
            aria-label="Positionen"
            className="scrollbar-thin absolute top-14 right-3 hidden max-h-[calc(100%-4.5rem)] w-60 animate-fadein space-y-0.5 overflow-y-auto rounded-lg border border-border bg-surface/90 p-1.5 shadow-lg backdrop-blur sm:block"
          >
            {rows.map((row) => (
              <li key={row.number}>
                <button
                  type="button"
                  onMouseEnter={() => setHighlight(row.number)}
                  onMouseLeave={() => setHighlight(null)}
                  onFocus={() => setHighlight(row.number)}
                  onBlur={() => setHighlight(null)}
                  className={clsx(
                    "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition",
                    highlight === row.number ? "bg-accent-soft" : "hover:bg-surface-muted",
                  )}
                >
                  <PositionBadge number={row.number} tone={row.tone} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{row.name}</span>
                    <span className="block truncate text-xs text-muted">{row.material}</span>
                  </span>
                  <span className="text-xs font-semibold text-muted">{row.count}×</span>
                </button>
              </li>
            ))}
          </ol>
        )}

        {/* Bottom: hint in 3D, filmstrip for drawings */}
        {mode === "model" ? (
          <p className="pointer-events-none absolute bottom-3 left-3 rounded-full bg-surface/85 px-3 py-1 text-xs text-muted shadow-sm backdrop-blur">
            {active
              ? `Pos. ${active.number}: ${active.name}, ${active.material}`
              : "Ziehen dreht, Scrollen zoomt"}
          </p>
        ) : (
          <div className="absolute inset-x-3 bottom-3 flex items-end justify-between gap-3">
            <ul className="scrollbar-thin flex gap-1.5 overflow-x-auto" aria-label="Zeichnungen">
              {drawings.map((d, index) => (
                <li key={d.view} className="shrink-0">
                  <button
                    type="button"
                    aria-pressed={index === drawing}
                    onClick={() => setDrawing(index)}
                    className={clsx(
                      "rounded-md border px-3 py-1.5 text-xs font-medium shadow-sm transition",
                      index === drawing
                        ? "border-text bg-text text-bg"
                        : "border-border bg-surface/90 text-muted hover:text-text",
                    )}
                  >
                    {d.title}
                  </button>
                </li>
              ))}
            </ul>
            {current && (
              <a
                href={`/api/projects/${project.id}/drawings/${current.view}.svg?v=${version}`}
                target="_blank"
                rel="noopener noreferrer"
                className="hidden shrink-0 rounded-md border border-border bg-surface/90 px-3 py-1.5 text-xs font-medium shadow-sm hover:bg-surface sm:inline-block"
              >
                Groß öffnen<span className="sr-only"> (öffnet neues Fenster)</span>
              </a>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
