"use client";

import type { ParamSpec, ProjectModel, StockPlan } from "@homeworking/api-client";
import clsx from "clsx";
import { useEffect, useId, useState, type ReactNode } from "react";

import { Icon, Spinner } from "@/components/ui";
import { useProjectCommand } from "@/lib/api";
import { toneColor } from "@/lib/tones";

type Result = ProjectModel["result"];
type ParamValue = string | number | boolean;

export function PositionBadge({ number, tone }: { number: number; tone?: string }) {
  return (
    <span
      className="inline-flex h-6 min-w-6 items-center justify-center rounded-full border border-stone-600/60 px-1 text-xs font-bold text-stone-900"
      style={{ backgroundColor: tone ? toneColor(tone) : "#ffffff" }}
    >
      {number}
    </span>
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

function unitOf(spec: ParamSpec): string {
  if (spec.kind === "length") return "mm";
  if (spec.kind === "angle") return "°";
  return "";
}

/**
 * Live parameter editing: sliders and fields apply on release / Enter / leaving the field.
 * Every applied change is one command, so undo works step by step.
 */
export function ParamEditor({ project }: { project: ProjectModel }) {
  const specs = project.result.param_specs ?? [];
  const command = useProjectCommand(project.id);
  const [values, setValues] = useState(() => initialValues(project, specs));
  const [saved, setSaved] = useState(false);
  const prefix = useId();

  useEffect(() => {
    if (!saved) return;
    const timer = window.setTimeout(() => setSaved(false), 2500);
    return () => window.clearTimeout(timer);
  }, [saved]);

  const original = initialValues(project, specs);

  function commit(next: Record<string, ParamValue>) {
    const changed = Object.keys(next).some((k) => next[k] !== original[k]);
    if (!changed || command.isPending) return;
    command.mutate({ type: "set_parameters", values: next }, { onSuccess: () => setSaved(true) });
  }

  function set(name: string, value: ParamValue, apply = false) {
    const next = { ...values, [name]: value };
    setValues(next);
    if (apply) commit(next);
  }

  if (specs.length === 0) {
    return <p className="text-sm text-muted">Dieses Projekt hat keine einstellbaren Maße.</p>;
  }

  const ranges = specs.filter((s) => s.kind !== "bool" && s.kind !== "choice");
  const choices = specs.filter((s) => s.kind === "choice");
  const toggles = specs.filter((s) => s.kind === "bool");

  return (
    <div className="space-y-6" aria-label="Parameter bearbeiten" role="group">
      <div className="flex min-h-6 items-center gap-2 text-sm" aria-live="polite">
        {command.isPending ? (
          <span className="inline-flex items-center gap-2 text-muted">
            <Spinner /> Wird neu berechnet …
          </span>
        ) : command.error ? (
          <span role="alert" className="text-warning">
            {command.error.message}
          </span>
        ) : saved ? (
          <span className="inline-flex items-center gap-1.5 text-success">
            <Icon name="check" className="h-4 w-4" /> Übernommen – alles neu berechnet
          </span>
        ) : (
          <span className="text-muted">
            Regler loslassen oder Enter drücken – Modell, Kosten und Pläne passen sich sofort an.
          </span>
        )}
      </div>

      <div className="grid gap-x-8 gap-y-5 md:grid-cols-2">
        {ranges.map((spec) => {
          const id = `${prefix}-${spec.name}`;
          const value = Number(values[spec.name]);
          const min = spec.min ?? 0;
          const max = spec.max ?? Math.max(value * 2, 10);
          const step = spec.kind === "length" ? 10 : 1;
          const unit = unitOf(spec);
          const dirty = values[spec.name] !== original[spec.name];
          return (
            <div key={spec.name}>
              <div className="flex items-baseline justify-between gap-2">
                <label htmlFor={id} className="text-sm font-medium">
                  {spec.label}
                </label>
                <span className="relative">
                  <input
                    id={id}
                    type="number"
                    inputMode="numeric"
                    name={spec.name}
                    step={step}
                    min={spec.min ?? undefined}
                    max={spec.max ?? undefined}
                    value={value}
                    onChange={(e) => set(spec.name, Number(e.target.value))}
                    onBlur={() => commit(values)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        commit(values);
                      }
                    }}
                    className={clsx(
                      "w-28 rounded-lg border bg-surface py-1 pr-9 pl-2 text-right font-medium tabular-nums",
                      dirty ? "border-accent" : "border-border",
                    )}
                  />
                  {unit && (
                    <span className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-xs text-muted">
                      {unit}
                    </span>
                  )}
                </span>
              </div>
              <input
                type="range"
                aria-hidden="true"
                tabIndex={-1}
                min={min}
                max={max}
                step={step}
                value={value}
                onChange={(e) => set(spec.name, Number(e.target.value))}
                onPointerUp={(e) => set(spec.name, Number(e.currentTarget.value), true)}
                className="mt-2 w-full cursor-pointer"
              />
              <div className="flex justify-between text-[11px] text-muted tabular-nums">
                <span>
                  {min} {unit}
                </span>
                <span>
                  {max} {unit}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {choices.map((spec) => (
        <fieldset key={spec.name}>
          <legend className="mb-2 text-sm font-medium">{spec.label}</legend>
          <div className="flex flex-wrap gap-1.5">
            {(spec.options ?? []).map((o) => {
              const active = String(values[spec.name]) === o.value;
              return (
                <button
                  key={o.value}
                  type="button"
                  aria-pressed={active}
                  onClick={() => set(spec.name, o.value, true)}
                  className={clsx(
                    "rounded-full border px-3 py-1.5 text-sm transition",
                    active
                      ? "border-accent bg-accent-soft font-medium text-accent-strong"
                      : "border-border hover:bg-surface-muted",
                  )}
                >
                  {o.label}
                </button>
              );
            })}
          </div>
        </fieldset>
      ))}

      {toggles.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {toggles.map((spec) => {
            const on = Boolean(values[spec.name]);
            return (
              <button
                key={spec.name}
                type="button"
                role="switch"
                aria-checked={on}
                onClick={() => set(spec.name, !on, true)}
                className="flex items-center justify-between gap-3 rounded-xl border border-border px-3 py-2.5 text-left text-sm hover:bg-surface-muted"
              >
                {spec.label}
                <span
                  aria-hidden="true"
                  className={clsx(
                    "relative h-6 w-10 shrink-0 rounded-full transition",
                    on ? "bg-accent" : "bg-border",
                  )}
                >
                  <span
                    className={clsx(
                      "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all",
                      on ? "left-[18px]" : "left-0.5",
                    )}
                  />
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
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
      <ul className="mt-1.5 space-y-1">
        {bars.map((pieces, index) => {
          const used = pieces.reduce((a, b) => a + b, 0);
          return (
            <li
              key={index}
              className="flex h-7 overflow-hidden rounded-md border border-stone-400/70 bg-[repeating-linear-gradient(45deg,#e7e5e4,#e7e5e4_4px,#f5f5f4_4px,#f5f5f4_8px)]"
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

export function CutList({ result }: { result: Result }) {
  const toneByPosition = new Map((result.solids ?? []).map((s) => [s.position, s.tone]));
  return (
    <>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Zuschnittliste">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border text-xs tracking-wide text-muted uppercase">
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
              <tr key={`${cut.part}-${index}`} className="border-b border-border last:border-0">
                <td className="py-2">
                  {cut.position != null ? (
                    <PositionBadge number={cut.position} tone={toneByPosition.get(cut.position)} />
                  ) : (
                    "–"
                  )}
                </td>
                <td className="py-2">
                  <span className="font-medium">{cut.part}</span>
                  <span className="block text-xs text-muted">{cut.material}</span>
                </td>
                <td className="py-2">
                  {cut.cross_section}
                  {cut.width_mm ? "" : " mm"}
                </td>
                <td className="py-2 text-right whitespace-nowrap tabular-nums">
                  {cut.length_mm}
                  {cut.width_mm ? ` × ${cut.width_mm}` : ""} mm
                </td>
                <td className="py-2 text-right font-semibold tabular-nums">{cut.count}×</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.stock_plan.length > 0 && (
        <div className="mt-6 space-y-4">
          <h4 className="text-sm font-semibold">Einkauf und Schnittplan</h4>
          {result.stock_plan.map((plan) => (
            <StockBars key={plan.item_id} plan={plan} />
          ))}
        </div>
      )}
    </>
  );
}

function useStoredSet(key: string): [Set<number>, (n: number) => void] {
  // Only rendered client-side after the project query resolved, so storage is available here.
  const [done, setDone] = useState<Set<number>>(() => {
    try {
      const raw = window.localStorage.getItem(key);
      return new Set(raw ? (JSON.parse(raw) as number[]) : []);
    } catch {
      // Storage unavailable (private mode): progress just is not remembered.
      return new Set();
    }
  });
  function toggle(n: number) {
    setDone((current) => {
      const next = new Set(current);
      if (next.has(n)) next.delete(n);
      else next.add(n);
      try {
        window.localStorage.setItem(key, JSON.stringify([...next]));
      } catch {
        // See above.
      }
      return next;
    });
  }
  return [done, toggle];
}

/** Build mode: the instructions as a checklist whose progress is remembered per project. */
export function BuildSteps({ result, projectId }: { result: Result; projectId: string }) {
  const [done, toggle] = useStoredSet(`homeworking:steps:${projectId}`);
  const steps = result.instructions;
  const count = steps.filter((s) => done.has(s.number)).length;
  const next = steps.find((s) => !done.has(s.number));
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-4 rounded-2xl bg-surface-muted/70 p-4">
        <div className="min-w-48 flex-1">
          <p className="text-sm font-semibold">
            {count === steps.length && steps.length > 0
              ? "Geschafft – alle Schritte erledigt!"
              : `${count} von ${steps.length} Schritten erledigt`}
          </p>
          <div
            className="mt-2 h-2 overflow-hidden rounded-full bg-border"
            role="progressbar"
            aria-label="Baufortschritt"
            aria-valuemin={0}
            aria-valuemax={steps.length}
            aria-valuenow={count}
          >
            <div
              className="h-full rounded-full bg-success transition-all duration-500"
              style={{ width: `${steps.length ? (count / steps.length) * 100 : 0}%` }}
            />
          </div>
        </div>
        {result.tools.length > 0 && (
          <div className="min-w-0">
            <p className="text-xs font-medium text-muted">Du brauchst</p>
            <ul className="mt-1 flex flex-wrap gap-1.5 text-xs">
              {result.tools.map((tool) => (
                <li key={tool.name} className="rounded-full bg-surface px-2.5 py-1">
                  {tool.name}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <ol className="relative space-y-3">
        {steps.map((step) => {
          const checked = done.has(step.number);
          const current = next?.number === step.number;
          return (
            <li
              key={step.number}
              className={clsx(
                "flex gap-3 rounded-2xl border p-4 transition",
                current ? "border-accent/50 bg-accent-soft/40 shadow-sm" : "border-border",
                checked && "opacity-60",
              )}
            >
              <button
                type="button"
                role="checkbox"
                aria-checked={checked}
                aria-label={`Schritt ${step.number} erledigt`}
                onClick={() => toggle(step.number)}
                className={clsx(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 text-sm font-bold transition",
                  checked
                    ? "border-success bg-success text-white dark:text-black"
                    : current
                      ? "border-accent text-accent-strong"
                      : "border-border text-muted hover:border-muted",
                )}
              >
                {checked ? <Icon name="check" className="h-4 w-4" /> : step.number}
              </button>
              <div className="min-w-0">
                <p className={clsx("font-semibold", checked && "line-through")}>
                  {step.title}
                  {step.origin === "ai" && (
                    <span className="ml-2 rounded bg-ai-soft px-1.5 py-0.5 align-middle text-xs font-bold text-ai no-underline">
                      KI-generiert
                    </span>
                  )}
                </p>
                <p className="mt-0.5 text-sm text-muted">{step.text}</p>
                {step.details && step.details.length > 0 && (
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                    {step.details.map((detail, index) => (
                      <li key={index}>{detail}</li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function paragraphs(text: string): string[] {
  return text
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function Notes({ notes }: { notes: NonNullable<ProjectModel["inputs"]["notes"]> }) {
  return (
    <div className="space-y-3">
      {notes.map((note) => (
        <figure key={note.id} className="rounded-2xl border border-ai/25 bg-ai-soft/50 p-4 text-sm">
          {note.origin === "ai" && (
            <figcaption className="mb-1.5 inline-flex items-center gap-1 text-xs font-bold text-ai">
              <Icon name="sparkles" className="h-3.5 w-3.5" /> KI-generiert
            </figcaption>
          )}
          <div className="space-y-2 leading-relaxed">
            {/* Explanations come in paragraphs separated by blank lines. */}
            {paragraphs(note.text).map((text, i) => (
              <p key={i} className="whitespace-pre-line">
                {text}
              </p>
            ))}
          </div>
        </figure>
      ))}
    </div>
  );
}

export function EmptyHint({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-muted">{children}</p>;
}
