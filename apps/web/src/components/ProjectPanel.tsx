"use client";

import type { ParamSpec, ProjectModel, Solid, StockPlan } from "@homeworking/api-client";
import clsx from "clsx";
import dynamic from "next/dynamic";
import { useId, useMemo, useState, type FormEvent, type ReactNode } from "react";

import { formatEur, useProject, useProjectCommand, useUndo } from "@/lib/api";
import { toneColor } from "@/lib/tones";

const Viewer3D = dynamic(() => import("@/components/Viewer3D"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-surface-muted" />,
});

type Result = ProjectModel["result"];
type ParamValue = string | number | boolean;

const TRUST: Record<string, { label: string; hint: string; className: string }> = {
  pack: {
    label: "Geprüftes Pack",
    hint: "Fachlich validierte Konstruktionsregeln",
    className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  },
  template: {
    label: "Vorlage",
    hint: "Konstruktion aus der Homeworking-Vorlagensammlung",
    className: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200",
  },
  ai_draft: {
    label: "KI-Entwurf",
    hint: "Konstruktion von der KI vorgeschlagen, nicht fachlich geprüft",
    className: "bg-ai-soft text-ai",
  },
};

function Icon({ path, className }: { path: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className={clsx("h-5 w-5 shrink-0", className)}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={path} />
    </svg>
  );
}

const ICONS = {
  info: "M12 8h.01M11 12h1v5h1M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z",
  warning:
    "M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z",
  euro: "M17 6.5A7 7 0 1 0 17 17.5M4 10h9M4 14h9",
  cube: "m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Zm0 0v18m8-13.5-8 4.5-8-4.5",
};

function Card({
  id,
  title,
  actions,
  children,
  className,
}: {
  id?: string;
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-labelledby={id}
      className={clsx("rounded-2xl border border-border bg-surface p-4 shadow-sm", className)}
    >
      {title && (
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 id={id} className="text-base font-semibold">
            {title}
          </h3>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

function PositionBadge({ number, tone }: { number: number; tone?: string }) {
  return (
    <span
      className="inline-flex h-6 min-w-6 items-center justify-center rounded-full border border-stone-600 px-1 text-xs font-bold text-stone-900"
      style={{ backgroundColor: tone ? toneColor(tone) : "#ffffff" }}
    >
      {number}
    </span>
  );
}

function KpiTiles({ result }: { result: Result }) {
  const figures = Object.entries(result.key_figures).slice(0, 5);
  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3" aria-label="Eckdaten">
      <li className="col-span-2 rounded-2xl bg-accent px-4 py-3 text-white sm:col-span-1 dark:text-black">
        <span className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide">
          <Icon path={ICONS.euro} className="h-4 w-4" /> Material (Richtwert)
        </span>
        <span className="mt-1 block text-xl font-bold" data-testid="material-cost">
          {formatEur(result.costs.material.min)} – {formatEur(result.costs.material.max)}
        </span>
      </li>
      {figures.map(([key, value]) => (
        <li key={key} className="rounded-2xl border border-border bg-surface px-4 py-3">
          <span className="block text-xs font-medium uppercase tracking-wide text-muted">
            {key}
          </span>
          <span className="mt-1 block font-semibold">{value}</span>
        </li>
      ))}
    </ul>
  );
}

function Notices({ result }: { result: Result }) {
  return (
    <ul className="space-y-2">
      {result.notices.map((notice) => {
        const warning = notice.severity !== "info";
        return (
          <li
            key={notice.code}
            className={clsx(
              "flex gap-2 rounded-xl border px-3 py-2 text-sm",
              warning
                ? "border-warning/40 bg-warning-soft text-warning"
                : "border-border bg-surface-muted text-text",
            )}
          >
            <Icon path={warning ? ICONS.warning : ICONS.info} />
            <span>{notice.message}</span>
          </li>
        );
      })}
    </ul>
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

function ModelView({ result, title }: { result: Result; title: string }) {
  const solids = useMemo(() => result.solids ?? [], [result.solids]);
  const rows = useMemo(() => positions(solids), [solids]);
  const [highlight, setHighlight] = useState<number | null>(null);
  const active = rows.find((r) => r.number === highlight);
  return (
    <Card id="model" title="3D-Modell" className="overflow-hidden">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_240px]">
        <div className="relative h-80 overflow-hidden rounded-xl border border-border bg-gradient-to-b from-white to-stone-100 sm:h-96">
          <Viewer3D
            solids={solids}
            highlight={highlight}
            onHover={setHighlight}
            label={`3D-Modell: ${title}, ${rows.length} Positionen. Ziehen zum Drehen, Mausrad zum Zoomen.`}
          />
          <p className="pointer-events-none absolute bottom-2 left-3 rounded bg-white/80 px-2 py-0.5 text-xs text-stone-700">
            {active
              ? `Pos. ${active.number} · ${active.name} · ${active.material}`
              : "Ziehen zum Drehen · Scrollen zum Zoomen"}
          </p>
        </div>
        <ol className="max-h-96 space-y-1 overflow-y-auto pr-1" aria-label="Positionen">
          {rows.map((row) => (
            <li key={row.number}>
              <button
                type="button"
                onMouseEnter={() => setHighlight(row.number)}
                onMouseLeave={() => setHighlight(null)}
                onFocus={() => setHighlight(row.number)}
                onBlur={() => setHighlight(null)}
                className={clsx(
                  "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm",
                  highlight === row.number ? "bg-accent-soft" : "hover:bg-surface-muted",
                )}
              >
                <PositionBadge number={row.number} tone={row.tone} />
                <span className="flex-1">
                  <span className="block font-medium">{row.name}</span>
                  <span className="block text-xs text-muted">{row.material}</span>
                </span>
                <span className="text-xs font-semibold text-muted">{row.count}×</span>
              </button>
            </li>
          ))}
        </ol>
      </div>
    </Card>
  );
}

function initialValues(project: ProjectModel, specs: ParamSpec[]): Record<string, ParamValue> {
  const values: Record<string, ParamValue> = {};
  for (const spec of specs) {
    const raw = project.inputs.params[spec.name] ?? project.result.effective_params[spec.name];
    values[spec.name] = raw as ParamValue;
  }
  return values;
}

function ParamEditor({ project }: { project: ProjectModel }) {
  const specs = project.result.param_specs ?? [];
  const command = useProjectCommand(project.id);
  const [values, setValues] = useState(() => initialValues(project, specs));
  const prefix = useId();

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    command.mutate({ type: "set_parameters", values });
  }

  const set = (name: string, value: ParamValue) => setValues({ ...values, [name]: value });
  const numeric = specs.filter((s) => s.kind !== "bool");
  const toggles = specs.filter((s) => s.kind === "bool");

  return (
    <form onSubmit={onSubmit} className="space-y-4" aria-label="Parameter bearbeiten">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
        {numeric.map((spec) => {
          const id = `${prefix}-${spec.name}`;
          return (
            <div key={spec.name} className="flex flex-col text-sm">
              <label htmlFor={id} className="text-muted">
                {spec.label}
              </label>
              {spec.kind === "choice" ? (
                <select
                  id={id}
                  value={String(values[spec.name])}
                  onChange={(e) => set(spec.name, e.target.value)}
                  className="mt-1 rounded-lg border border-border bg-surface px-2 py-1.5"
                >
                  {(spec.options ?? []).map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id={id}
                  type="number"
                  inputMode="numeric"
                  name={spec.name}
                  step={spec.kind === "length" ? 10 : 1}
                  min={spec.min ?? undefined}
                  max={spec.max ?? undefined}
                  value={Number(values[spec.name])}
                  onChange={(e) => set(spec.name, Number(e.target.value))}
                  className="mt-1 rounded-lg border border-border bg-surface px-2 py-1.5"
                />
              )}
              {spec.min != null && spec.max != null && (
                <span className="mt-0.5 text-xs text-muted">
                  {spec.min}–{spec.max}
                </span>
              )}
            </div>
          );
        })}
      </div>
      {toggles.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {toggles.map((spec) => (
            <label
              key={spec.name}
              className={clsx(
                "flex cursor-pointer items-center gap-2 rounded-full border px-3 py-1 text-sm",
                values[spec.name] ? "border-accent bg-accent-soft" : "border-border",
              )}
            >
              <input
                type="checkbox"
                checked={Boolean(values[spec.name])}
                onChange={(e) => set(spec.name, e.target.checked)}
              />
              {spec.label}
            </label>
          ))}
        </div>
      )}
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={command.isPending}
          className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:text-black"
        >
          Übernehmen
        </button>
        {command.error && (
          <p role="alert" className="text-sm text-warning">
            {command.error.message}
          </p>
        )}
      </div>
    </form>
  );
}

function Variants({ project }: { project: ProjectModel }) {
  const command = useProjectCommand(project.id);
  const variants = project.result.variants;
  if (variants.length === 0) return null;
  const cheapest = Math.min(...variants.map((v) => Number(v.material_cost.min)));
  return (
    <Card id="variants" title="Varianten">
      <ul className="grid gap-3 sm:grid-cols-3">
        {variants.map((variant) => (
          <li
            key={variant.key}
            className={clsx(
              "flex flex-col rounded-xl border p-3 transition-colors",
              variant.is_selected ? "border-accent bg-accent-soft" : "border-border",
            )}
          >
            <span className="flex items-center justify-between gap-2">
              <span className="font-semibold">{variant.name}</span>
              {Number(variant.material_cost.min) === cheapest && (
                <span className="rounded-full bg-emerald-100 px-2 text-xs font-semibold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">
                  günstigste
                </span>
              )}
            </span>
            <span className="flex-1 text-sm text-muted">{variant.description}</span>
            <span className="mt-2 text-lg font-bold">
              {formatEur(variant.material_cost.min)} – {formatEur(variant.material_cost.max)}
            </span>
            <button
              type="button"
              disabled={variant.is_selected || command.isPending}
              onClick={() => command.mutate({ type: "select_variant", variant_key: variant.key })}
              className="mt-2 rounded-lg border border-border px-2 py-1 text-sm hover:bg-surface-muted disabled:opacity-50"
              aria-label={`Variante ${variant.name} wählen`}
            >
              {variant.is_selected ? "Gewählt" : "Wählen"}
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function StockBars({ plan }: { plan: StockPlan }) {
  const bars = plan.bars ?? [];
  if (bars.length === 0) {
    return (
      <div>
        <p className="text-sm font-medium">
          {plan.stock_count}× {plan.name ?? plan.item_id}
        </p>
        <div className="mt-1 h-3 overflow-hidden rounded-full bg-surface-muted" aria-hidden="true">
          <div className="h-full bg-accent" style={{ width: `${plan.utilization_pct ?? 0}%` }} />
        </div>
        <p className="mt-0.5 text-xs text-muted">Ausnutzung ca. {plan.utilization_pct ?? "–"} %</p>
      </div>
    );
  }
  return (
    <div>
      <p className="text-sm font-medium">
        {plan.stock_count}× {plan.name ?? plan.item_id}, {plan.stock_length_mm} mm
        <span className="ml-2 text-xs text-muted">Verschnitt {plan.waste_mm} mm</span>
      </p>
      <ul className="mt-1 space-y-1">
        {bars.map((pieces, index) => {
          const used = pieces.reduce((a, b) => a + b, 0);
          return (
            <li
              key={index}
              className="flex h-7 overflow-hidden rounded-md border border-stone-400 bg-[repeating-linear-gradient(45deg,#e7e5e4,#e7e5e4_4px,#f5f5f4_4px,#f5f5f4_8px)]"
              aria-label={`Stange ${index + 1}: ${pieces.join(" mm, ")} mm, Rest ${plan.stock_length_mm - used} mm`}
            >
              {pieces.map((piece, i) => (
                <span
                  key={i}
                  className="flex items-center justify-center border-r-2 border-white bg-amber-200 text-[11px] font-medium text-stone-900"
                  style={{ width: `${(piece / plan.stock_length_mm) * 100}%` }}
                >
                  {piece}
                </span>
              ))}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

const TABS = [
  { key: "drawings", label: "Zeichnungen" },
  { key: "bom", label: "Material" },
  { key: "cuts", label: "Zuschnitt" },
  { key: "steps", label: "Anleitung" },
  { key: "params", label: "Maße anpassen" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

function Tabs({ active, onChange }: { active: TabKey; onChange: (key: TabKey) => void }) {
  return (
    <div
      role="tablist"
      aria-label="Projektdetails"
      className="flex gap-1 overflow-x-auto border-b border-border"
    >
      {TABS.map((tab) => (
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
            const index = TABS.findIndex((t) => t.key === active);
            const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
            if (delta) {
              const next = TABS[(index + delta + TABS.length) % TABS.length]!;
              onChange(next.key);
              document.getElementById(`tab-${next.key}`)?.focus();
            }
          }}
          className={clsx(
            "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium",
            active === tab.key
              ? "border-accent text-text"
              : "border-transparent text-muted hover:text-text",
          )}
        >
          {tab.label}
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
      className="pt-4"
    >
      {children}
    </div>
  );
}

export function ProjectPanel({ projectId }: { projectId: string }) {
  const { data, isLoading, error } = useProject(projectId);
  const undo = useUndo(projectId);
  const [tab, setTab] = useState<TabKey>("drawings");

  if (isLoading) return <p className="text-muted">Projekt wird geladen …</p>;
  if (error || !data) return <p role="alert">Das Projekt konnte nicht geladen werden.</p>;

  const { project, can_undo: canUndo } = data;
  const result = project.result;
  const notes = project.inputs.notes ?? [];
  const version = encodeURIComponent(JSON.stringify(result.effective_params));
  const trust = TRUST[result.trust ?? "pack"] ?? TRUST.pack!;
  const toneByPosition = new Map((result.solids ?? []).map((s) => [s.position, s.tone]));
  const hasModel = (result.solids ?? []).length > 0;

  return (
    <div className="space-y-4" data-testid="project-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-2xl font-bold tracking-tight">{project.inputs.title}</h2>
            <span
              className={clsx("rounded-full px-2.5 py-0.5 text-xs font-semibold", trust.className)}
              title={trust.hint}
              data-testid="trust-badge"
            >
              {trust.label}
            </span>
          </div>
          <p className="text-muted" data-testid="project-summary">
            {result.summary}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => undo.mutate()}
            disabled={!canUndo || undo.isPending}
            className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm disabled:opacity-40"
          >
            Rückgängig
          </button>
          <a
            href={`/api/projects/${project.id}/document.pdf`}
            className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white dark:text-black"
            download
          >
            PDF herunterladen
          </a>
        </div>
      </div>

      <KpiTiles result={result} />
      <Notices result={result} />
      {hasModel && <ModelView key={version} result={result} title={project.inputs.title} />}
      <Variants project={project} />

      <Card>
        <Tabs active={tab} onChange={setTab} />

        <Panel tab="drawings" active={tab}>
          <div className="grid gap-4 xl:grid-cols-2">
            {result.drawings.map((d) => (
              <figure
                key={d.view}
                className="drawing-frame overflow-hidden rounded-xl border border-border"
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- dynamic SVG from the API */}
                <img
                  src={`/api/projects/${project.id}/drawings/${d.view}.svg?v=${version}`}
                  alt={d.description}
                  className="mx-auto h-auto max-h-[560px] w-auto max-w-full"
                  data-testid={`drawing-${d.view}`}
                />
                <figcaption className="border-t border-border bg-surface px-3 py-2 text-xs font-medium text-muted">
                  {d.title}
                </figcaption>
              </figure>
            ))}
          </div>
        </Panel>

        <Panel tab="bom" active={tab}>
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Materialliste">
            <table className="w-full text-left text-sm" data-testid="bom">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                  <th scope="col" className="py-2 pr-2">
                    Material
                  </th>
                  <th scope="col" className="py-2 pr-2">
                    Spezifikation
                  </th>
                  <th scope="col" className="py-2 pr-2 text-right">
                    Menge
                  </th>
                  <th scope="col" className="py-2 text-right">
                    Richtpreis
                  </th>
                </tr>
              </thead>
              <tbody>
                {result.bom.map((line) => (
                  <tr
                    key={line.item_id}
                    className="border-b border-border align-top odd:bg-surface-muted/50"
                  >
                    <td className="py-1.5 pr-2">
                      {line.name}
                      {line.note && <span className="block text-xs text-muted">{line.note}</span>}
                    </td>
                    <td className="py-1.5 pr-2">{line.spec}</td>
                    <td className="py-1.5 pr-2 text-right whitespace-nowrap">
                      {Number(line.quantity)} {line.unit}
                    </td>
                    <td className="py-1.5 text-right whitespace-nowrap">
                      {formatEur(line.total.min)} – {formatEur(line.total.max)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="font-semibold">
                  <td className="py-2" colSpan={3}>
                    Summe Material
                  </td>
                  <td className="py-2 text-right whitespace-nowrap">
                    {formatEur(result.costs.material.min)} – {formatEur(result.costs.material.max)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="mt-2 text-xs text-muted">
            {result.costs.note} Werkzeug, falls nicht vorhanden:{" "}
            {formatEur(result.costs.tools_optional.min)} –{" "}
            {formatEur(result.costs.tools_optional.max)}. Katalog{" "}
            {result.provenance.catalog_version}, Stand {result.provenance.catalog_as_of}.
          </p>
        </Panel>

        <Panel tab="cuts" active={tab}>
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Zuschnittliste">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                  <th scope="col" className="py-2">
                    Pos.
                  </th>
                  <th scope="col" className="py-2">
                    Bauteil
                  </th>
                  <th scope="col" className="py-2">
                    Querschnitt
                  </th>
                  <th scope="col" className="py-2 text-right">
                    Zuschnitt
                  </th>
                  <th scope="col" className="py-2 text-right">
                    Anzahl
                  </th>
                </tr>
              </thead>
              <tbody>
                {result.cut_list.map((cut, index) => (
                  <tr key={`${cut.part}-${index}`} className="border-b border-border">
                    <td className="py-1.5">
                      {cut.position != null ? (
                        <PositionBadge
                          number={cut.position}
                          tone={toneByPosition.get(cut.position)}
                        />
                      ) : (
                        "–"
                      )}
                    </td>
                    <td className="py-1.5">
                      {cut.part}
                      <span className="block text-xs text-muted">{cut.material}</span>
                    </td>
                    <td className="py-1.5">
                      {cut.cross_section}
                      {cut.width_mm ? "" : " mm"}
                    </td>
                    <td className="py-1.5 text-right whitespace-nowrap">
                      {cut.length_mm}
                      {cut.width_mm ? ` × ${cut.width_mm}` : ""} mm
                    </td>
                    <td className="py-1.5 text-right">{cut.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result.stock_plan.length > 0 && (
            <div className="mt-5 space-y-4">
              <h4 className="text-sm font-semibold">Einkauf und Schnittplan</h4>
              {result.stock_plan.map((plan) => (
                <StockBars key={plan.item_id} plan={plan} />
              ))}
            </div>
          )}
        </Panel>

        <Panel tab="steps" active={tab}>
          <ol className="space-y-4">
            {result.instructions.map((step) => (
              <li key={step.number} className="flex gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-sm font-bold text-white dark:text-black">
                  {step.number}
                </span>
                <div>
                  <p className="font-semibold">
                    {step.title}
                    {step.origin === "ai" && (
                      <span className="ml-2 rounded bg-ai-soft px-1.5 py-0.5 align-middle text-xs font-bold text-ai">
                        KI-generiert
                      </span>
                    )}
                  </p>
                  <p className="text-sm text-muted">{step.text}</p>
                  {step.details && step.details.length > 0 && (
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                      {step.details.map((detail, index) => (
                        <li key={index}>{detail}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </li>
            ))}
          </ol>
          <h4 className="mt-5 text-sm font-semibold">Werkzeug</h4>
          <ul className="mt-2 flex flex-wrap gap-2 text-sm">
            {result.tools.map((tool) => (
              <li
                key={tool.name}
                className="rounded-full border border-border bg-surface-muted px-3 py-1"
              >
                {tool.name}
              </li>
            ))}
          </ul>
        </Panel>

        <Panel tab="params" active={tab}>
          <ParamEditor key={version} project={project} />
        </Panel>
      </Card>

      {notes.length > 0 && (
        <Card id="notes" title="Erläuterungen">
          {notes.map((note) => (
            <div
              key={note.id}
              className="mb-2 rounded-xl border border-dashed border-ai/50 p-3 text-sm"
            >
              {note.origin === "ai" && (
                <span className="mb-1 inline-block rounded bg-ai-soft px-1.5 text-xs font-bold text-ai">
                  KI-generiert
                </span>
              )}
              <p>{note.text}</p>
            </div>
          ))}
        </Card>
      )}

      <p className="text-xs text-muted">
        Planungshilfe – kein Standsicherheitsnachweis. Ob ein Vorhaben genehmigungspflichtig ist,
        regelt die Landesbauordnung; verbindlich ist die Auskunft des Bauamts. Engine{" "}
        {result.provenance.engine_version} · Pack {result.provenance.pack_id}{" "}
        {result.provenance.pack_version}
      </p>
    </div>
  );
}
