"use client";

import type { ProjectModel } from "@homeworking/api-client";
import { useState, type FormEvent } from "react";

import { formatEur, useProject, useProjectCommand, useUndo } from "@/lib/api";

const WOODS: Record<string, string> = { spruce: "Fichte", douglas: "Douglasie", larch: "Lärche" };

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className="rounded-xl border border-border bg-surface p-4">
      <h3 id={id} className="mb-3 text-base font-semibold">
        {title}
      </h3>
      {children}
    </section>
  );
}

function ParamEditor({ project }: { project: ProjectModel }) {
  const params = project.result.effective_params;
  const command = useProjectCommand(project.id);
  const [values, setValues] = useState({
    length_mm: Number(params.length_mm),
    width_mm: Number(params.width_mm),
    height_mm: Number(project.inputs.params.height_mm ?? params.height_mm),
    wood: String(params.wood),
    liner: Boolean(params.liner),
    vole_mesh: Boolean(params.vole_mesh),
    top_cap: Boolean(params.top_cap),
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    command.mutate({ type: "set_parameters", values });
  }

  const numberField = (name: "length_mm" | "width_mm" | "height_mm", label: string) => (
    <label className="flex flex-col text-sm">
      <span className="text-muted">{label}</span>
      <input
        type="number"
        inputMode="numeric"
        step={10}
        name={name}
        value={values[name]}
        onChange={(e) => setValues({ ...values, [name]: Number(e.target.value) })}
        className="mt-1 rounded-md border border-border bg-surface px-2 py-1"
      />
    </label>
  );

  const toggle = (name: "liner" | "vole_mesh" | "top_cap", label: string) => (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={values[name]}
        onChange={(e) => setValues({ ...values, [name]: e.target.checked })}
      />
      {label}
    </label>
  );

  return (
    <form onSubmit={onSubmit} className="space-y-3" aria-label="Parameter bearbeiten">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {numberField("length_mm", "Länge (mm)")}
        {numberField("width_mm", "Breite (mm)")}
        {numberField("height_mm", "Höhe (mm)")}
        <label className="flex flex-col text-sm">
          <span className="text-muted">Holzart</span>
          <select
            value={values.wood}
            onChange={(e) => setValues({ ...values, wood: e.target.value })}
            className="mt-1 rounded-md border border-border bg-surface px-2 py-1"
          >
            {Object.entries(WOODS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="flex flex-wrap gap-4">
        {toggle("liner", "Noppenbahn")}
        {toggle("vole_mesh", "Wühlmausgitter")}
        {toggle("top_cap", "Sitzkante")}
      </div>
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={command.isPending}
          className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:text-black"
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

export function ProjectPanel({ projectId }: { projectId: string }) {
  const { data, isLoading, error } = useProject(projectId);
  const command = useProjectCommand(projectId);
  const undo = useUndo(projectId);

  if (isLoading) return <p className="text-muted">Projekt wird geladen …</p>;
  if (error || !data) return <p role="alert">Das Projekt konnte nicht geladen werden.</p>;

  const { project, can_undo: canUndo } = data;
  const result = project.result;
  const notes = project.inputs.notes ?? [];
  const version = encodeURIComponent(JSON.stringify(result.effective_params));

  return (
    <div className="space-y-4" data-testid="project-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">{project.inputs.title}</h2>
          <p className="text-muted" data-testid="project-summary">
            {result.summary}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => undo.mutate()}
            disabled={!canUndo || undo.isPending}
            className="rounded-lg border border-border px-3 py-1.5 text-sm disabled:opacity-40"
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

      <Section id="figures" title="Eckdaten">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          {Object.entries(result.key_figures).map(([key, value]) => (
            <div key={key} className="flex justify-between gap-3 border-b border-border py-1">
              <dt className="text-muted">{key}</dt>
              <dd className="text-right font-medium">{value}</dd>
            </div>
          ))}
          <div className="flex justify-between gap-3 border-b border-border py-1">
            <dt className="text-muted">Materialkosten (Richtwert)</dt>
            <dd className="text-right font-semibold" data-testid="material-cost">
              {formatEur(result.costs.material.min)} – {formatEur(result.costs.material.max)}
            </dd>
          </div>
        </dl>
        <ul className="mt-3 space-y-2">
          {result.notices.map((notice) => (
            <li
              key={notice.code}
              className={
                notice.severity === "info"
                  ? "rounded-md bg-surface-muted px-3 py-2 text-sm"
                  : "rounded-md bg-warning-soft px-3 py-2 text-sm text-warning"
              }
            >
              {notice.message}
            </li>
          ))}
        </ul>
      </Section>

      <Section id="params" title="Maße und Ausstattung">
        <ParamEditor key={version} project={project} />
      </Section>

      <Section id="variants" title="Varianten">
        <ul className="grid gap-3 sm:grid-cols-3">
          {result.variants.map((variant) => (
            <li
              key={variant.key}
              className={`flex flex-col rounded-lg border p-3 ${
                variant.is_selected ? "border-accent bg-accent-soft" : "border-border"
              }`}
            >
              <span className="font-semibold">{variant.name}</span>
              <span className="flex-1 text-sm text-muted">{variant.description}</span>
              <span className="mt-2 text-sm font-medium">
                {formatEur(variant.material_cost.min)} – {formatEur(variant.material_cost.max)}
              </span>
              <button
                type="button"
                disabled={variant.is_selected || command.isPending}
                onClick={() => command.mutate({ type: "select_variant", variant_key: variant.key })}
                className="mt-2 rounded-md border border-border px-2 py-1 text-sm disabled:opacity-50"
                aria-label={`Variante ${variant.name} wählen`}
              >
                {variant.is_selected ? "Gewählt" : "Wählen"}
              </button>
            </li>
          ))}
        </ul>
      </Section>

      <Section id="drawings" title="Zeichnungen">
        <div className="grid gap-4 lg:grid-cols-2">
          {result.drawings.map((d) => (
            <figure key={d.view} className="drawing-frame overflow-hidden rounded-lg border border-border">
              {/* eslint-disable-next-line @next/next/no-img-element -- dynamic SVG from the API */}
              <img
                src={`/api/projects/${project.id}/drawings/${d.view}.svg?v=${version}`}
                alt={d.description}
                className="h-auto w-full"
                data-testid={`drawing-${d.view}`}
              />
              <figcaption className="px-3 py-2 text-xs text-muted">{d.title}</figcaption>
            </figure>
          ))}
        </div>
      </Section>

      <Section id="bom" title="Materialliste">
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Materialliste">
          <table className="w-full text-left text-sm" data-testid="bom">
            <thead>
              <tr className="border-b border-border text-muted">
                <th scope="col" className="py-1 pr-2">Material</th>
                <th scope="col" className="py-1 pr-2">Spezifikation</th>
                <th scope="col" className="py-1 pr-2 text-right">Menge</th>
                <th scope="col" className="py-1 text-right">Richtpreis</th>
              </tr>
            </thead>
            <tbody>
              {result.bom.map((line) => (
                <tr key={line.item_id} className="border-b border-border align-top">
                  <td className="py-1 pr-2">
                    {line.name}
                    {line.note && <span className="block text-xs text-muted">{line.note}</span>}
                  </td>
                  <td className="py-1 pr-2">{line.spec}</td>
                  <td className="py-1 pr-2 text-right whitespace-nowrap">
                    {Number(line.quantity)} {line.unit}
                  </td>
                  <td className="py-1 text-right whitespace-nowrap">
                    {formatEur(line.total.min)} – {formatEur(line.total.max)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted">
          {result.costs.note} Katalog {result.provenance.catalog_version}, Stand{" "}
          {result.provenance.catalog_as_of}.
        </p>
      </Section>

      <Section id="cuts" title="Zuschnittliste">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border text-muted">
              <th scope="col" className="py-1">Bauteil</th>
              <th scope="col" className="py-1">Querschnitt</th>
              <th scope="col" className="py-1 text-right">Länge</th>
              <th scope="col" className="py-1 text-right">Anzahl</th>
            </tr>
          </thead>
          <tbody>
            {result.cut_list.map((cut) => (
              <tr key={cut.part} className="border-b border-border">
                <td className="py-1">{cut.part}</td>
                <td className="py-1">{cut.cross_section} mm</td>
                <td className="py-1 text-right">{cut.length_mm} mm</td>
                <td className="py-1 text-right">{cut.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section id="steps" title="Bauanleitung">
        <ol className="space-y-3">
          {result.instructions.map((step) => (
            <li key={step.number}>
              <p className="font-medium">
                {step.number}. {step.title}
              </p>
              <p className="text-sm text-muted">{step.text}</p>
            </li>
          ))}
        </ol>
        <h4 className="mt-4 text-sm font-semibold">Werkzeug</h4>
        <ul className="list-inside list-disc text-sm text-muted">
          {result.tools.map((tool) => (
            <li key={tool.name}>{tool.name}</li>
          ))}
        </ul>
      </Section>

      {notes.length > 0 && (
        <Section id="notes" title="Erläuterungen">
          {notes.map((note) => (
            <div key={note.id} className="mb-2 rounded-md border border-dashed border-ai/50 p-3 text-sm">
              {note.origin === "ai" && (
                <span className="mb-1 inline-block rounded bg-ai-soft px-1.5 text-xs font-bold text-ai">
                  KI-generiert
                </span>
              )}
              <p>{note.text}</p>
            </div>
          ))}
        </Section>
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
