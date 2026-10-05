"use client";

import type { UIMessage } from "ai";
import clsx from "clsx";

import { designProgress, planningStages, type ActivityStep, type StepState } from "@/lib/activity";
import { asToolPart, formatElapsed, messageText, useElapsed } from "@/lib/assistant";

function StatusIcon({ state }: { state: StepState | "pending" }) {
  if (state === "running") {
    return (
      <span
        aria-hidden="true"
        className="mt-0.5 h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-ai/30 border-t-ai"
      />
    );
  }
  const common =
    "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold";
  if (state === "done") {
    return (
      <span aria-hidden="true" className={clsx(common, "bg-emerald-600 text-white")}>
        ✓
      </span>
    );
  }
  if (state === "pending") {
    return <span aria-hidden="true" className={clsx(common, "border-2 border-border")} />;
  }
  return (
    <span
      aria-hidden="true"
      className={clsx(
        common,
        state === "error" ? "bg-red-600 text-white" : "bg-warning text-white",
      )}
    >
      !
    </span>
  );
}

const STATE_TEXT: Record<StepState, string> = {
  running: "läuft",
  done: "erledigt",
  warning: "Hinweis",
  error: "Fehler",
};

export function ActivityList({ steps, reasoning }: { steps: ActivityStep[]; reasoning: string }) {
  if (!steps.length) return null;
  return (
    <div className="my-1 rounded-xl border border-border bg-surface-muted/60 px-3 py-2">
      <ul className="space-y-1.5 text-sm" aria-label="Arbeitsschritte des Assistenten">
        {steps.map((step) => (
          <li key={step.key} className="flex gap-2">
            <StatusIcon state={step.state} />
            <span className="min-w-0">
              <span className={clsx(step.state === "running" && "font-medium")}>{step.label}</span>
              <span className="sr-only"> ({STATE_TEXT[step.state]})</span>
              {step.detail && (
                <span className="block break-words text-xs text-muted">{step.detail}</span>
              )}
            </span>
          </li>
        ))}
      </ul>
      {reasoning.trim() && (
        <details className="mt-2 text-xs text-muted">
          <summary className="cursor-pointer select-none">Gedankengang anzeigen</summary>
          <p className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap">{reasoning}</p>
        </details>
      )}
    </div>
  );
}

/** Latest design part names while the model is still writing the design. */
function draftedParts(message: UIMessage | null): string[] {
  for (const [index, part] of (message?.parts ?? []).entries()) {
    const tool = asToolPart(part, String(index));
    if (tool && (tool.name === "design_project" || tool.name === "redesign_project")) {
      const names = designProgress(tool.input).parts;
      if (names.length) return names;
    }
  }
  return [];
}

/** Right-hand panel while a first project is being planned. */
export function PlanningProgress({
  request,
  current,
  startedAt,
}: {
  request: string;
  current: UIMessage | null;
  startedAt: number | null;
}) {
  const elapsed = useElapsed(startedAt);
  const stages = planningStages(current);
  const parts = draftedParts(current);
  const counts = new Map<string, number>();
  for (const name of parts) counts.set(name, (counts.get(name) ?? 0) + 1);
  const said = current ? messageText(current) : "";
  return (
    <section
      aria-labelledby="progress-heading"
      className="rounded-2xl border border-border bg-surface p-5 shadow-sm"
      data-testid="planning-progress"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="progress-heading" className="text-lg font-semibold">
          Dein Projekt entsteht
        </h2>
        <span className="font-mono text-sm tabular-nums text-muted" aria-label="Laufzeit">
          {formatElapsed(elapsed)}
        </span>
      </div>
      <ol className="mt-4 space-y-3" aria-live="polite">
        {stages.map((stage) => (
          <li key={stage.label} className="flex gap-3">
            <StatusIcon state={stage.state} />
            <span
              className={clsx(
                stage.state === "pending" && "text-muted",
                stage.state === "running" && "font-medium",
              )}
            >
              {stage.label}
            </span>
          </li>
        ))}
      </ol>

      {said && (
        <p className="mt-5 rounded-xl bg-ai-soft px-3 py-2 text-sm text-ai">
          <span className="block text-xs font-semibold uppercase tracking-wide">KI-Assistent</span>
          {said}
        </p>
      )}

      {counts.size > 0 && (
        <div className="mt-5">
          <h3 className="text-sm font-semibold">Bisher entworfene Bauteile</h3>
          <ul className="mt-2 flex flex-wrap gap-1.5 text-sm">
            {[...counts].map(([name, n]) => (
              <li
                key={name}
                className="animate-[fadein_0.3s_ease-out] rounded-full border border-border bg-surface-muted px-2.5 py-0.5"
              >
                {n > 1 ? `${n}× ` : ""}
                {name}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-5 border-t border-border pt-4">
        <h3 className="text-sm font-semibold">Deine Anfrage</h3>
        <p className="mt-1 whitespace-pre-wrap text-sm text-muted">{request}</p>
      </div>
      <p className="mt-4 text-xs text-muted">
        Vorlagen sind in Sekunden fertig. Freie Entwürfe schreibt die KI Bauteil für Bauteil; danach
        prüft und berechnet die Engine Stückliste, Zuschnitt und Zeichnungen. Das Ergebnis erscheint
        hier automatisch.
      </p>
    </section>
  );
}
