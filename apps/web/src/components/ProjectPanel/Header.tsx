"use client";

import type { ProjectModel } from "@/api";

import { PdfDownload } from "@/components/PdfDownload";
import { AI_DESIGN, Icon, Pill, buttonClass } from "@/components/ui";
import { useUndo } from "@/lib/api";
import { isTyping, useGlobalKey } from "@/lib/keys";
import { formatCost, formatRange, isExact } from "@/lib/prices";

import type { Result } from "./types";

function costLabel(result: Result): string {
  const priced = result.costs.user_priced ?? 0;
  if (priced === 0) return "Material, Richtpreis";
  return priced === result.bom.length ? "Material, deine Preise" : "Material, teils deine Preise";
}

function CostCard({ result }: { result: Result }) {
  const used = result.costs.material_used;
  const leftover = used ? Number(result.costs.material.min) - Number(used.min) : 0;
  return (
    <div className="overflow-hidden rounded-md bg-accent text-on-accent">
      <div aria-hidden="true" className="rule h-2" />
      <div className="px-4 pt-1 pb-2">
        <span className="block text-xs font-medium">{costLabel(result)}</span>
        <span
          className="block text-3xl leading-tight font-extrabold tabular-nums [font-stretch:78%]"
          data-testid="material-cost"
        >
          {formatCost(result.costs.material)}
        </span>
        <span className="block text-[11px]">
          {!isExact(result.costs.material) && formatRange(result.costs.material)}
          {used && leftover > 0.5 && <>, verbraucht {formatCost(used)}</>}
        </span>
      </div>
    </div>
  );
}

export function Header({
  project,
  canUndo,
  version,
  historyOpen,
  onToggleHistory,
}: {
  project: ProjectModel;
  canUndo: boolean;
  version: string;
  historyOpen: boolean;
  onToggleHistory: () => void;
}) {
  const undo = useUndo(project.id);
  const { mutate: undoNow, isPending: undoPending } = undo;
  const result = project.result;

  // Ctrl/Cmd+Z undoes the last change unless the user is typing.
  useGlobalKey((event) => {
    if (isTyping(event.target) || !(event.ctrlKey || event.metaKey)) return;
    if (event.key.toLowerCase() !== "z" || event.shiftKey || !canUndo || undoPending) return;
    event.preventDefault();
    undoNow();
  });

  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-3xl leading-tight font-extrabold sm:text-4xl">
            {project.inputs.title}
          </h2>
          <Pill className={AI_DESIGN.className} title={AI_DESIGN.hint} testId="design-badge">
            {AI_DESIGN.label}
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
          <button
            type="button"
            onClick={onToggleHistory}
            aria-expanded={historyOpen}
            aria-controls="version-history"
            className={buttonClass.secondary}
          >
            <Icon name="layers" className="h-4 w-4" />
            Verlauf
          </button>
        </div>
      </div>
    </header>
  );
}
