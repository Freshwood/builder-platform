"use client";

import type { UIMessage } from "ai";
import clsx from "clsx";

import { Icon } from "@/components/ui";
import { designProgress, planningStages, type ActivityStep, type StepState } from "@/lib/activity";
import { asToolPart, formatElapsed, messageText, useElapsed } from "@/lib/assistant";

function StatusIcon({ state, className }: { state: StepState | "pending"; className?: string }) {
  const common = clsx(
    "flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
    className,
  );
  if (state === "running") {
    return (
      <span
        aria-hidden="true"
        className={clsx(common, "animate-spin border-2 border-ai/25 border-t-ai")}
      />
    );
  }
  if (state === "done") {
    return (
      <span aria-hidden="true" className={clsx(common, "bg-success text-white dark:text-black")}>
        <Icon name="check" className="h-3 w-3" />
      </span>
    );
  }
  if (state === "pending") {
    return (
      <span aria-hidden="true" className={clsx(common, "border-2 border-current opacity-30")} />
    );
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

/** Long technical details (validation dumps) are folded away behind a toggle. */
function StepDetail({ text }: { text: string }) {
  if (text.length <= 140) {
    return <span className="block break-words text-xs text-muted">{text}</span>;
  }
  return (
    <details className="text-xs text-muted">
      <summary className="cursor-pointer select-none">{text.slice(0, 110)}… Details</summary>
      <span className="mt-1 block max-h-40 overflow-y-auto font-mono break-words whitespace-pre-wrap">
        {text}
      </span>
    </details>
  );
}

/** Tool and reasoning steps of an assistant message: compact chips once all is well. */
export function ActivityList({ steps, reasoning }: { steps: ActivityStep[]; reasoning: string }) {
  if (!steps.length) return null;
  const calm = steps.every((s) => s.state === "done");
  return (
    <div className="my-1.5">
      <ul
        className={clsx(calm ? "flex flex-wrap gap-1.5" : "space-y-1.5", "text-sm")}
        aria-label="Arbeitsschritte des Assistenten"
      >
        {steps.map((step) =>
          calm ? (
            <li
              key={step.key}
              title={step.detail}
              className="inline-flex items-center gap-1.5 rounded-full bg-surface-muted px-2 py-0.5 text-xs text-muted"
            >
              <StatusIcon state={step.state} className="h-3.5 w-3.5" />
              {step.label}
            </li>
          ) : (
            <li key={step.key} className="flex gap-2">
              <StatusIcon state={step.state} className="mt-0.5" />
              <span className="min-w-0">
                <span className={clsx(step.state === "running" && "font-medium")}>
                  {step.label}
                </span>
                <span className="sr-only"> ({STATE_TEXT[step.state]})</span>
                {step.detail && <StepDetail text={step.detail} />}
              </span>
            </li>
          ),
        )}
      </ul>
      {reasoning.trim() && (
        <details className="mt-1.5 text-xs text-muted">
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

/** Main area while a first project is being planned: a blueprint that fills up live. */
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
  const done = stages.filter((s) => s.state === "done").length;
  return (
    <section
      aria-labelledby="progress-heading"
      className="blueprint relative flex h-full min-h-[28rem] flex-col overflow-hidden rounded-3xl p-6 text-white sm:p-8"
      data-testid="planning-progress"
    >
      {/* Scanning line over the blueprint */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-1/4 animate-[scan_3.5s_linear_infinite] bg-gradient-to-b from-transparent via-sky-300/10 to-transparent"
      />
      <div className="relative flex items-baseline justify-between gap-3">
        <h2 id="progress-heading" className="text-2xl font-semibold tracking-tight">
          Dein Projekt entsteht
        </h2>
        <span className="font-mono text-sm tabular-nums text-sky-200" aria-label="Laufzeit">
          {formatElapsed(elapsed)}
        </span>
      </div>
      <div
        className="relative mt-4 h-1 overflow-hidden rounded-full bg-white/10"
        role="progressbar"
        aria-label="Fortschritt"
        aria-valuemin={0}
        aria-valuemax={stages.length}
        aria-valuenow={done}
      >
        <div
          className="h-full rounded-full bg-sky-300 transition-all duration-700"
          style={{ width: `${Math.max(6, (done / stages.length) * 100)}%` }}
        />
      </div>

      <ol className="relative mt-6 grid gap-3 sm:grid-cols-2" aria-live="polite">
        {stages.map((stage, index) => (
          <li
            key={stage.label}
            className={clsx(
              "flex items-center gap-3 rounded-2xl border px-4 py-3 transition",
              stage.state === "running"
                ? "border-sky-300/60 bg-white/10"
                : stage.state === "done"
                  ? "border-white/15 bg-white/5"
                  : "border-white/10 text-white/75",
            )}
          >
            <span className="font-mono text-xs text-sky-200">0{index + 1}</span>
            <span className="flex-1 text-sm font-medium">{stage.label}</span>
            <StatusIcon
              state={stage.state}
              className={stage.state === "running" ? "border-white/25 border-t-white" : ""}
            />
          </li>
        ))}
      </ol>

      {counts.size > 0 && (
        <div className="relative mt-6">
          <h3 className="text-xs font-semibold tracking-wide text-sky-200 uppercase">
            Bauteile im Entwurf
          </h3>
          <ul className="mt-2 flex flex-wrap gap-1.5 text-sm">
            {[...counts].map(([name, n]) => (
              <li
                key={name}
                className="animate-pop rounded-lg border border-sky-200/30 bg-sky-200/10 px-2.5 py-1 font-mono text-xs"
              >
                {n > 1 ? `${n}× ` : ""}
                {name}
              </li>
            ))}
          </ul>
        </div>
      )}

      {said && (
        <p className="relative mt-6 max-w-2xl rounded-2xl bg-white/10 px-4 py-3 text-sm leading-relaxed">
          <span className="mb-1 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-sky-200 uppercase">
            <Icon name="sparkles" className="h-3.5 w-3.5" /> KI-Assistent
          </span>
          {said}
        </p>
      )}

      <div className="relative mt-auto pt-8">
        <h3 className="text-xs font-semibold tracking-wide text-sky-200 uppercase">
          Deine Anfrage
        </h3>
        <p className="mt-1 line-clamp-4 text-sm whitespace-pre-wrap text-white/80">{request}</p>
        <p className="mt-4 text-xs text-white/75">
          Vorlagen sind in Sekunden fertig. Freie Entwürfe schreibt die KI Bauteil für Bauteil;
          danach prüft und berechnet die Engine Stückliste, Zuschnitt und Zeichnungen.
        </p>
      </div>
    </section>
  );
}

/** Main area when a planning turn ended without a project: a follow-up question or an error. */
export function PlanningStopped({
  request,
  reply,
  failed,
  onAnswer,
  onRetry,
}: {
  request: string;
  reply: string;
  failed: boolean;
  onAnswer: () => void;
  onRetry: () => void;
}) {
  const asked = !failed && reply.length > 0;
  return (
    <section
      aria-labelledby="stopped-heading"
      className="blueprint relative flex h-full min-h-[28rem] flex-col overflow-hidden rounded-3xl p-6 text-white sm:p-8"
      data-testid="planning-stopped"
    >
      <h2 id="stopped-heading" className="text-2xl font-semibold tracking-tight">
        {asked ? "Der Assistent hat eine Rückfrage" : "Noch kein Projekt erstellt"}
      </h2>
      <p role={failed ? "alert" : undefined} className="mt-2 max-w-2xl text-sm text-white/80">
        {failed
          ? "Die Verbindung zum Assistenten ist fehlgeschlagen."
          : asked
            ? "Beantworte sie im Chat, dann geht es weiter."
            : "Der Assistent hat diesmal kein Projekt berechnet. Versuche es noch einmal."}
      </p>

      {asked && (
        <p className="relative mt-6 max-h-[24rem] max-w-2xl overflow-y-auto rounded-2xl bg-white/10 px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap">
          <span className="mb-1 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-sky-200 uppercase">
            <Icon name="sparkles" className="h-3.5 w-3.5" /> KI-Assistent
          </span>
          {reply}
        </p>
      )}

      <div className="mt-6 flex flex-wrap gap-2">
        {asked && (
          <button
            type="button"
            onClick={onAnswer}
            className="inline-flex items-center gap-1.5 rounded-xl bg-white px-4 py-2 text-sm font-medium text-slate-900 transition hover:bg-sky-100"
          >
            <Icon name="message" className="h-4 w-4" /> Im Chat antworten
          </button>
        )}
        <button
          type="button"
          onClick={onRetry}
          className={clsx(
            "inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium transition",
            asked
              ? "border border-white/30 hover:bg-white/10"
              : "bg-white text-slate-900 hover:bg-sky-100",
          )}
        >
          <Icon name="rotate" className="h-4 w-4" /> {asked ? "Nochmal planen" : "Erneut versuchen"}
        </button>
      </div>

      <div className="relative mt-auto pt-8">
        <h3 className="text-xs font-semibold tracking-wide text-sky-200 uppercase">
          Deine Anfrage
        </h3>
        <p className="mt-1 line-clamp-4 text-sm whitespace-pre-wrap text-white/80">{request}</p>
      </div>
    </section>
  );
}
