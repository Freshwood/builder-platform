"use client";

import type { ProjectModel } from "@/api";
import clsx from "clsx";

import { Icon, Pill } from "@/components/ui";
import { useProjectCommand } from "@/lib/api";
import { formatCost, formatEur, typical } from "@/lib/prices";

/** Alternative materials or constructions; picking one is a command like any other edit. */
export function Variants({ project }: { project: ProjectModel }) {
  const command = useProjectCommand(project.id);
  const variants = project.result.variants;
  if (variants.length === 0) return null;
  const selected = variants.find((v) => v.is_selected);
  const base = typical(selected?.material_cost ?? project.result.costs.material);
  const cheapest = Math.min(...variants.map((v) => Number(v.material_cost.min)));
  return (
    <section aria-labelledby="variants-heading">
      <h3 id="variants-heading" className="mb-2 text-xl font-bold">
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
                  "flex h-full w-full flex-col rounded-lg border p-3 text-left transition",
                  variant.is_selected
                    ? "border-text bg-accent-soft ring-1 ring-text"
                    : "border-border bg-surface hover:border-text/40",
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
