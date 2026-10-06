"use client";

import type { ProjectModel, Solid } from "@homeworking/api-client";
import clsx from "clsx";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { BomTable } from "@/components/BomTable";
import { PdfDownload } from "@/components/PdfDownload";
import {
  BuildSteps,
  CutList,
  Notes,
  ParamEditor,
  PositionBadge,
} from "@/components/ProjectDetails";
import { Icon, Pill, Segmented, TRUST, buttonClass, type IconName } from "@/components/ui";
import { formatEur, useProject, useProjectCommand, useUndo } from "@/lib/api";
import { formatCost, formatRange, isExact, typical } from "@/lib/prices";

const Viewer3D = dynamic(() => import("@/components/Viewer3D"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse" />,
});

type Result = ProjectModel["result"];

function costLabel(result: Result): string {
  const priced = result.costs.user_priced ?? 0;
  if (priced === 0) return "Material · Richtpreis";
  return priced === result.bom.length ? "Material · deine Preise" : "Material · teils deine Preise";
}

function CostCard({ result }: { result: Result }) {
  const used = result.costs.material_used;
  const leftover = used ? Number(result.costs.material.min) - Number(used.min) : 0;
  return (
    <div className="rounded-2xl bg-accent px-4 py-2 text-on-accent shadow-sm">
      <span className="block text-[11px] font-medium tracking-wide uppercase">
        {costLabel(result)}
      </span>
      <span
        className="block text-2xl leading-tight font-bold tabular-nums"
        data-testid="material-cost"
      >
        {formatCost(result.costs.material)}
      </span>
      <span className="block text-[11px]">
        {!isExact(result.costs.material) && formatRange(result.costs.material)}
        {used && leftover > 0.5 && <> · verbraucht {formatCost(used)}</>}
      </span>
    </div>
  );
}

function Header({
  project,
  canUndo,
  version,
}: {
  project: ProjectModel;
  canUndo: boolean;
  version: string;
}) {
  const undo = useUndo(project.id);
  const result = project.result;
  const trust = TRUST[result.trust ?? "pack"] ?? TRUST.pack!;

  // Ctrl/Cmd+Z undoes the last change unless the user is typing.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = target?.closest("input, textarea, select, [contenteditable]");
      if (typing || !(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "z") return;
      if (event.shiftKey || !canUndo || undo.isPending) return;
      event.preventDefault();
      undo.mutate();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [canUndo, undo]);

  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">{project.inputs.title}</h2>
          <Pill className={trust.className} title={trust.hint} testId="trust-badge">
            {trust.label}
          </Pill>
        </div>
        <p className="mt-1 text-muted" data-testid="project-summary">
          {result.summary}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <CostCard result={result} />
        <div className="flex flex-col gap-1.5">
          <PdfDownload projectId={project.id} version={version} />
          <button
            type="button"
            onClick={() => undo.mutate()}
            disabled={!canUndo || undo.isPending}
            title="Rückgängig (Strg + Z)"
            className={buttonClass.secondary}
          >
            <Icon name="undo" className="h-4 w-4" />
            Rückgängig
          </button>
        </div>
      </div>
    </header>
  );
}

function Figures({ result }: { result: Result }) {
  const figures = Object.entries(result.key_figures).slice(0, 6);
  if (!figures.length) return null;
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Eckdaten">
      {figures.map(([key, value]) => (
        <li
          key={key}
          className="shrink-0 rounded-xl border border-border bg-surface px-3 py-1.5 text-sm"
        >
          <span className="block text-[11px] font-medium tracking-wide text-muted uppercase">
            {key}
          </span>
          <span className="font-semibold whitespace-nowrap">{value}</span>
        </li>
      ))}
    </ul>
  );
}

function Notices({ result }: { result: Result }) {
  const warnings = result.notices.filter((n) => n.severity !== "info");
  const infos = result.notices.filter((n) => n.severity === "info");
  if (!result.notices.length) return null;
  return (
    <div className="space-y-2">
      {warnings.map((notice) => (
        <p
          key={notice.code}
          className="flex gap-2 rounded-xl border border-warning/40 bg-warning-soft px-3 py-2 text-sm text-warning"
        >
          <Icon name="warning" className="h-4 w-4 translate-y-0.5" />
          <span>{notice.message}</span>
        </p>
      ))}
      {infos.length > 0 && (
        <details className="group rounded-xl border border-border bg-surface px-3 py-2 text-sm">
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
function Stage({ project, version }: { project: ProjectModel; version: string }) {
  const result = project.result;
  const solids = useMemo(() => result.solids ?? [], [result.solids]);
  const rows = useMemo(() => positions(solids), [solids]);
  const hasModel = solids.length > 0;
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
      className="stage relative overflow-hidden rounded-3xl border border-border shadow-sm"
    >
      <div className="relative h-[22rem] sm:h-[30rem] lg:h-[min(62vh,40rem)]">
        {hasModel && (
          <div hidden={mode !== "model"} className="absolute inset-0">
            <Viewer3D
              key={version}
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
          {drawings.map((d, index) => (
            // eslint-disable-next-line @next/next/no-img-element -- dynamic SVG from the API
            <img
              key={d.view}
              src={`/api/projects/${project.id}/drawings/${d.view}.svg?v=${version}`}
              alt={d.description}
              hidden={index !== drawing}
              className="max-h-full max-w-full object-contain"
              data-testid={`drawing-${d.view}`}
            />
          ))}
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
                className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface/85 px-3 py-1.5 text-sm font-medium shadow-sm backdrop-blur hover:bg-surface"
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
              className="flex h-[34px] w-[34px] items-center justify-center rounded-xl border border-border bg-surface/85 shadow-sm backdrop-blur hover:bg-surface"
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
            className="scrollbar-thin absolute top-14 right-3 hidden max-h-[calc(100%-4.5rem)] w-60 animate-fadein space-y-0.5 overflow-y-auto rounded-2xl border border-border bg-surface/90 p-1.5 shadow-lg backdrop-blur sm:block"
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
                    "flex w-full items-center gap-2 rounded-xl px-2 py-1.5 text-left text-sm transition",
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
              ? `Pos. ${active.number} · ${active.name} · ${active.material}`
              : "Ziehen zum Drehen · Scrollen zum Zoomen"}
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
                      "rounded-xl border px-3 py-1.5 text-xs font-medium shadow-sm transition",
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
                className="hidden shrink-0 rounded-xl border border-border bg-surface/90 px-3 py-1.5 text-xs font-medium shadow-sm hover:bg-surface sm:inline-block"
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

function Variants({ project }: { project: ProjectModel }) {
  const command = useProjectCommand(project.id);
  const variants = project.result.variants;
  if (variants.length === 0) return null;
  const selected = variants.find((v) => v.is_selected);
  const base = typical(selected?.material_cost ?? project.result.costs.material);
  const cheapest = Math.min(...variants.map((v) => Number(v.material_cost.min)));
  return (
    <section aria-labelledby="variants-heading">
      <h3
        id="variants-heading"
        className="mb-2 text-sm font-semibold tracking-wide text-muted uppercase"
      >
        Varianten
      </h3>
      <ul className="scrollbar-thin -mx-1 flex snap-x gap-3 overflow-x-auto px-1 pb-1">
        {variants.map((variant) => {
          const delta = Math.round(typical(variant.material_cost) - base);
          return (
            <li key={variant.key} className="w-64 shrink-0 snap-start sm:w-auto sm:flex-1">
              <button
                type="button"
                disabled={variant.is_selected || command.isPending}
                onClick={() => command.mutate({ type: "select_variant", variant_key: variant.key })}
                aria-label={`Variante ${variant.name} wählen`}
                className={clsx(
                  "flex h-full w-full flex-col rounded-2xl border p-3 text-left transition",
                  variant.is_selected
                    ? "border-accent bg-accent-soft/60 ring-1 ring-accent"
                    : "border-border bg-surface hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-md",
                )}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="font-semibold">{variant.name}</span>
                  {variant.is_selected ? (
                    <Pill className="bg-accent text-on-accent">
                      <Icon name="check" className="h-3 w-3" /> aktiv
                    </Pill>
                  ) : (
                    Number(variant.material_cost.min) === cheapest && (
                      <Pill className="bg-success-soft text-success">günstigste</Pill>
                    )
                  )}
                </span>
                <span className="mt-0.5 flex-1 text-sm text-muted">{variant.description}</span>
                <span className="mt-2 flex items-baseline gap-2">
                  <span className="text-lg font-bold tabular-nums">
                    {formatCost(variant.material_cost)}
                  </span>
                  {!variant.is_selected && delta !== 0 && (
                    <span
                      className={clsx(
                        "text-xs font-semibold tabular-nums",
                        delta < 0 ? "text-success" : "text-muted",
                      )}
                    >
                      {delta > 0 ? "+" : "−"}
                      {formatEur(Math.abs(delta))}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

type TabKey = "adjust" | "bom" | "cuts" | "steps" | "notes";

function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: { key: TabKey; label: string; icon: IconName; count?: number }[];
  active: TabKey;
  onChange: (key: TabKey) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Projektdetails"
      className="scrollbar-thin flex gap-1 overflow-x-auto rounded-2xl bg-surface-muted p-1"
    >
      {tabs.map((tab) => (
        <button
          key={tab.key}
          id={`tab-${tab.key}`}
          role="tab"
          type="button"
          aria-selected={active === tab.key}
          aria-controls={`panel-${tab.key}`}
          tabIndex={active === tab.key ? 0 : -1}
          onClick={() => onChange(tab.key)}
          onKeyDown={(event) => {
            const index = tabs.findIndex((t) => t.key === active);
            const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
            if (delta) {
              const next = tabs[(index + delta + tabs.length) % tabs.length]!;
              onChange(next.key);
              document.getElementById(`tab-${next.key}`)?.focus();
            }
          }}
          className={clsx(
            "inline-flex flex-1 items-center justify-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium whitespace-nowrap transition",
            active === tab.key ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text",
          )}
        >
          <Icon name={tab.icon} className="h-4 w-4" />
          {tab.label}
          {tab.count != null && (
            <span className="rounded-full bg-surface-muted px-1.5 text-xs text-muted">
              {tab.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

function Panel({ tab, active, children }: { tab: TabKey; active: TabKey; children: ReactNode }) {
  return (
    <div
      role="tabpanel"
      id={`panel-${tab}`}
      aria-labelledby={`tab-${tab}`}
      hidden={tab !== active}
      className="pt-5"
    >
      {children}
    </div>
  );
}

export function ProjectPanel({ projectId }: { projectId: string }) {
  const { data, isLoading, error } = useProject(projectId);
  const [tab, setTab] = useState<TabKey | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-4" aria-busy="true">
        <div className="h-16 animate-pulse rounded-2xl bg-surface-muted" />
        <div className="h-[30rem] animate-pulse rounded-3xl bg-surface-muted" />
        <p className="sr-only">Projekt wird geladen …</p>
      </div>
    );
  }
  if (error || !data) return <p role="alert">Das Projekt konnte nicht geladen werden.</p>;

  const { project, can_undo: canUndo } = data;
  const result = project.result;
  const notes = project.inputs.notes ?? [];
  const version = encodeURIComponent(JSON.stringify(result.effective_params));
  const hasParams = (result.param_specs ?? []).length > 0;

  const tabs: { key: TabKey; label: string; icon: IconName; count?: number }[] = [
    ...(hasParams ? [{ key: "adjust" as const, label: "Anpassen", icon: "sliders" as const }] : []),
    { key: "bom", label: "Material", icon: "list", count: result.bom.length },
    { key: "cuts", label: "Zuschnitt", icon: "scissors" },
    { key: "steps", label: "Bauanleitung", icon: "hammer", count: result.instructions.length },
    ...(notes.length
      ? [{ key: "notes" as const, label: "Warum so?", icon: "lightbulb" as const }]
      : []),
  ];
  const active = tab && tabs.some((t) => t.key === tab) ? tab : tabs[0]!.key;

  return (
    <div className="animate-fadein space-y-5" data-testid="project-panel">
      <Header project={project} canUndo={canUndo} version={version} />
      <Figures result={result} />
      <Stage key={project.id} project={project} version={version} />
      <Notices result={result} />
      <Variants project={project} />

      <section
        aria-label="Details"
        className="rounded-3xl border border-border bg-surface p-3 shadow-sm sm:p-4"
      >
        <Tabs tabs={tabs} active={active} onChange={setTab} />

        {hasParams && (
          <Panel tab="adjust" active={active}>
            <ParamEditor key={version} project={project} />
          </Panel>
        )}

        <Panel tab="bom" active={active}>
          <BomTable result={result} projectId={project.id} />
          <p className="mt-3 text-xs text-muted">
            {result.costs.note} Werkzeug, falls nicht vorhanden:{" "}
            {formatEur(result.costs.tools_optional.min)} –{" "}
            {formatEur(result.costs.tools_optional.max)}. Katalog{" "}
            {result.provenance.catalog_version}, Stand {result.provenance.catalog_as_of}.
          </p>
        </Panel>

        <Panel tab="cuts" active={active}>
          <CutList result={result} />
        </Panel>

        <Panel tab="steps" active={active}>
          <BuildSteps key={project.id} result={result} projectId={project.id} />
        </Panel>

        {notes.length > 0 && (
          <Panel tab="notes" active={active}>
            <Notes notes={notes} />
          </Panel>
        )}
      </section>

      <p className="flex gap-2 text-xs text-muted">
        <Icon name="shield" className="h-4 w-4" />
        <span>
          Planungshilfe – kein Standsicherheitsnachweis. Ob ein Vorhaben genehmigungspflichtig ist,
          regelt die Landesbauordnung; verbindlich ist die Auskunft des Bauamts. Engine{" "}
          {result.provenance.engine_version} · Pack {result.provenance.pack_id}{" "}
          {result.provenance.pack_version}
        </span>
      </p>
    </div>
  );
}
