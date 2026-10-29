"use client";

import type { ParamSpec, ProjectModel } from "@/api";
import clsx from "clsx";
import { useEffect, useId, useState } from "react";

import { Icon, Spinner } from "@/components/ui";
import { useProjectCommand } from "@/lib/api";

type ParamValue = string | number | boolean;

/** A flag that switches on when triggered and off again after ``ms`` milliseconds. */
function useFlash(ms: number): [boolean, () => void] {
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (!on) return;
    const timer = window.setTimeout(() => setOn(false), ms);
    return () => window.clearTimeout(timer);
  }, [on, ms]);
  return [on, () => setOn(true)];
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
  const [saved, flashSaved] = useFlash(2500);
  const prefix = useId();

  const original = initialValues(project, specs);

  function commit(next: Record<string, ParamValue>) {
    const changed = Object.keys(next).some((k) => next[k] !== original[k]);
    if (!changed || command.isPending) return;
    command.mutate({ type: "set_parameters", values: next }, { onSuccess: flashSaved });
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
                      dirty ? "border-accent-strong" : "border-border",
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
                      ? "border-text bg-accent-soft font-medium"
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
                className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2.5 text-left text-sm hover:bg-surface-muted"
              >
                {spec.label}
                <span
                  aria-hidden="true"
                  className={clsx(
                    "relative h-6 w-10 shrink-0 rounded-full transition",
                    on ? "bg-text" : "bg-border",
                  )}
                >
                  <span
                    className={clsx(
                      "absolute top-0.5 h-5 w-5 rounded-full bg-surface shadow transition-all",
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
