"use client";

import type { ProjectModel } from "@/api";
import clsx from "clsx";

import { Icon } from "@/components/ui";
import { useStoredSet } from "@/lib/storage";

type Result = ProjectModel["result"];

/** Build mode: the instructions as a checklist whose progress is remembered per project. */
export function BuildSteps({ result, projectId }: { result: Result; projectId: string }) {
  const [done, toggle] = useStoredSet(`homeworking:steps:${projectId}`);
  const steps = result.instructions;
  const count = steps.filter((s) => done.has(s.number)).length;
  const next = steps.find((s) => !done.has(s.number));
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-4 rounded-lg bg-surface-muted/70 p-4">
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
                "flex gap-3 rounded-lg border p-4 transition",
                current ? "border-text/40 bg-accent-soft/50" : "border-border",
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
                      ? "border-text text-text"
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
