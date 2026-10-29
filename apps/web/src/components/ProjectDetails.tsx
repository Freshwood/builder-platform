"use client";

import type { ProjectModel, StockPlan } from "@/api";

import { Icon } from "@/components/ui";
import { toneColor } from "@/lib/tones";

type Result = ProjectModel["result"];

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
            <tr className="border-b border-border text-xs font-medium text-muted">
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
        <figure key={note.id} className="rounded-lg border border-ai/25 bg-ai-soft/50 p-4 text-sm">
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
