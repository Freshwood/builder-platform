"use client";

import type { BomLine, ProjectModel } from "@homeworking/api-client";
import clsx from "clsx";
import { useState, type FormEvent } from "react";

import { useProjectCommand } from "@/lib/api";
import { SHOPS, formatCost, formatRange, isExact, parsePrice } from "@/lib/prices";

type Result = ProjectModel["result"];

function PriceEditor({ line, projectId }: { line: BomLine; projectId: string }) {
  const command = useProjectCommand(projectId);
  const own = line.price_source === "user";
  const [value, setValue] = useState(
    own ? Number(line.unit_price.min).toFixed(2).replace(".", ",") : "",
  );
  const [error, setError] = useState(false);
  const label = `Dein Preis je ${line.unit} für ${line.name}`;

  function save(event: FormEvent) {
    event.preventDefault();
    const price = value.trim() ? parsePrice(value) : null;
    if (value.trim() && price === null) {
      setError(true);
      return;
    }
    setError(false);
    if (price === null && !own) return;
    if (own && price === Number(line.unit_price.min).toFixed(2)) return;
    command.mutate({ type: "set_price", item_id: line.item_id, unit_price: price });
  }

  return (
    <form onSubmit={save} className="flex items-center justify-end gap-1">
      <label className="sr-only" htmlFor={`price-${line.item_id}`}>
        {label}
      </label>
      <input
        id={`price-${line.item_id}`}
        inputMode="decimal"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onBlur={save}
        placeholder={formatCost(line.unit_price, { cents: true }).replace("ca. ", "")}
        aria-invalid={error}
        className={clsx(
          "w-24 rounded-md border bg-surface px-2 py-1 text-right tabular-nums",
          error ? "border-warning" : own ? "border-accent-strong" : "border-border",
        )}
      />
      {own && (
        <button
          type="button"
          onClick={() => {
            setValue("");
            command.mutate({ type: "set_price", item_id: line.item_id, unit_price: null });
          }}
          className="rounded px-1 text-xs text-muted hover:text-text"
          title="Zurück zum Richtpreis"
          aria-label={`Eigenen Preis für ${line.name} entfernen`}
        >
          ↺
        </button>
      )}
    </form>
  );
}

function SourceBadge({ line }: { line: BomLine }) {
  return line.price_source === "user" ? (
    <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent-strong">
      dein Preis
    </span>
  ) : (
    <span
      className="rounded-full bg-surface-muted px-2 py-0.5 text-xs text-muted"
      title={`Spanne typischer Ladenpreise: ${formatRange(line.unit_price, { cents: true })} je ${line.unit}`}
    >
      Richtpreis
    </span>
  );
}

export function BomTable({
  result,
  projectId,
  readOnly = false,
}: {
  result: Result;
  projectId: string;
  readOnly?: boolean;
}) {
  const costs = result.costs;
  const used = costs.material_used;
  const userPriced = costs.user_priced ?? 0;
  const savings = used ? Number(costs.material.min) - Number(used.min) : 0;
  return (
    <>
      <div className="mb-3 rounded-md border border-border bg-surface-muted/60 px-3 py-2 text-sm">
        <p className="font-medium">Woher kommen die Preise?</p>
        <p className="mt-1 text-muted">
          Ohne deine Angabe ist jeder Preis ein <strong>Richtpreis</strong>: die Spanne typischer
          Ladenpreise deutscher Baumärkte und Holzhändler aus dem Homeworking-Katalog (Stand{" "}
          {result.provenance.catalog_as_of}) – kein Angebot. Prüfe Preise über die Links bei jeder
          Position und trage deinen echten Preis ein; die Summen werden dann exakt.
        </p>
        <p className="mt-1 text-muted" data-testid="price-status">
          {userPriced === 0
            ? "Noch keine eigenen Preise eingetragen."
            : `${userPriced} von ${result.bom.length} Positionen mit deinem Preis.`}
        </p>
      </div>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Materialliste">
        <table className="w-full text-left text-sm" data-testid="bom">
          <thead>
            <tr className="border-b border-border text-xs font-medium text-muted">
              <th scope="col" className="py-2 pr-2">
                Material
              </th>
              <th scope="col" className="py-2 pr-2 text-right">
                Menge
              </th>
              <th scope="col" className="py-2 pr-2 text-right">
                Preis je Einheit
              </th>
              <th scope="col" className="py-2 pr-2 text-right">
                Summe
              </th>
            </tr>
          </thead>
          <tbody>
            {result.bom.map((line) => {
              const share = line.used_share != null ? Number(line.used_share) : null;
              return (
                <tr
                  key={line.item_id}
                  className="border-b border-border align-top odd:bg-surface-muted/50"
                >
                  <td className="py-2 pr-2">
                    <span className="font-medium">{line.name}</span>
                    <span className="block text-xs text-muted">{line.spec}</span>
                    {line.note && <span className="block text-xs text-muted">{line.note}</span>}
                    {line.search_query && (
                      <span className="mt-1 flex flex-wrap gap-x-2 text-xs">
                        <span className="text-muted">Preis prüfen:</span>
                        {SHOPS.map((shop) => (
                          <a
                            key={shop.name}
                            href={shop.url(line.search_query!)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-accent-strong underline underline-offset-2"
                          >
                            {shop.name}
                            <span className="sr-only"> (öffnet neues Fenster)</span>
                          </a>
                        ))}
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-2 text-right whitespace-nowrap">
                    {Number(line.quantity)} {line.unit}
                    {share !== null && share < 1 && (
                      <span className="block text-xs text-muted">
                        davon verbraucht {Math.max(1, Math.round(share * 100))} %
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-2">
                    {readOnly ? (
                      <span className="block text-right tabular-nums">
                        {formatCost(line.unit_price, { cents: true })}
                      </span>
                    ) : (
                      <PriceEditor
                        key={`${line.item_id}:${line.price_source}:${line.unit_price.min}`}
                        line={line}
                        projectId={projectId}
                      />
                    )}
                    <span className="mt-1 flex justify-end">
                      <SourceBadge line={line} />
                    </span>
                  </td>
                  <td className="py-2 pr-2 text-right whitespace-nowrap tabular-nums">
                    {formatCost(line.total, { cents: isExact(line.total) })}
                    {!isExact(line.total) && (
                      <span className="block text-xs text-muted">{formatRange(line.total)}</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="font-semibold">
              <td className="py-2" colSpan={3}>
                Summe Einkauf
              </td>
              <td className="py-2 text-right whitespace-nowrap" data-testid="bom-total">
                {formatCost(costs.material)}
                {!isExact(costs.material) && (
                  <span className="block text-xs font-normal text-muted">
                    {formatRange(costs.material)}
                  </span>
                )}
              </td>
            </tr>
            {used && savings > 0.5 && (
              <tr className="text-muted">
                <td className="pb-2" colSpan={3}>
                  davon für dieses Projekt verbraucht (Rest der Packungen bleibt übrig)
                </td>
                <td className="pb-2 text-right whitespace-nowrap">{formatCost(used)}</td>
              </tr>
            )}
          </tfoot>
        </table>
      </div>
    </>
  );
}
