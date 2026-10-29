"use client";

import { memo, useState } from "react";

import { BomTable } from "@/components/BomTable";
import { BuildSteps } from "@/components/BuildSteps";
import { CutList, Notes } from "@/components/ProjectDetails";
import { ParamEditor } from "@/components/ParamEditor";
import { VersionHistory } from "@/components/VersionHistory";
import { Icon } from "@/components/ui";
import { useProject, useProjectVersion } from "@/lib/api";
import { formatEur } from "@/lib/prices";

import { Header } from "./Header";
import { Figures, Notices } from "./Notices";
import { Stage } from "./Stage";
import { Panel, Tabs, type TabItem } from "./Tabs";
import type { TabKey } from "./types";
import { VersionBanner } from "./VersionBanner";
import { Variants } from "./Variants";

/** Memoised: the chat streams many updates per second into the workspace around it. */
export const ProjectPanel = memo(function ProjectPanel({ projectId }: { projectId: string }) {
  const current = useProject(projectId);
  const [viewSeq, setViewSeq] = useState<number | null>(null);
  // The project moved on (the assistant changed it, or a version was restored) while an old
  // version was shown: leave the read-only view and show the new state instead of silently
  // staying on stale data. Derived state, adjusted while rendering.
  const currentSeq = current.data?.seq;
  const [knownSeq, setKnownSeq] = useState(currentSeq);
  if (currentSeq !== knownSeq) {
    setKnownSeq(currentSeq);
    if (knownSeq !== undefined) setViewSeq(null);
  }
  const [historyOpen, setHistoryOpen] = useState(false);
  const old = useProjectVersion(projectId, viewSeq);
  const { data, isLoading, error } = viewSeq === null ? current : old;
  const [tab, setTab] = useState<TabKey | null>(null);
  const readOnly = viewSeq !== null;

  if (isLoading) {
    return (
      <div className="space-y-4" aria-busy="true">
        <div className="h-16 animate-pulse rounded-lg bg-surface-muted" />
        <div className="h-[30rem] animate-pulse rounded-xl bg-surface-muted" />
        <p className="sr-only">Projekt wird geladen …</p>
      </div>
    );
  }
  if (error || !data) return <p role="alert">Das Projekt konnte nicht geladen werden.</p>;

  const { project, can_undo: canUndo, seq } = data;
  const result = project.result;
  const notes = project.inputs.notes ?? [];
  // Query string of drawing and PDF URLs: the log position changes with every edit, also with
  // a redesign that keeps the parameters (cache busting); seq= selects an earlier version,
  // which the API may cache for good.
  const version = viewSeq === null ? String(seq) : `${viewSeq}&seq=${viewSeq}`;
  const hasParams = (result.param_specs ?? []).length > 0;

  const tabs: TabItem[] = [
    ...(hasParams && !readOnly
      ? [{ key: "adjust" as const, label: "Anpassen", icon: "sliders" as const }]
      : []),
    { key: "bom", label: "Material", icon: "list", count: result.bom.length },
    { key: "cuts", label: "Zuschnitt", icon: "scissors" },
    { key: "steps", label: "Bauanleitung", icon: "hammer", count: result.instructions.length },
    ...(notes.length
      ? [{ key: "notes" as const, label: "Warum so?", icon: "lightbulb" as const }]
      : []),
  ];
  const active = tab && tabs.some((t) => t.key === tab) ? tab : tabs[0]!.key;

  return (
    <div className="animate-fadein space-y-5" data-testid="project-panel">
      {viewSeq !== null && (
        <VersionBanner projectId={projectId} seq={viewSeq} onClose={() => setViewSeq(null)} />
      )}
      <Header
        project={project}
        canUndo={canUndo && !readOnly}
        version={version}
        historyOpen={historyOpen}
        onToggleHistory={() => setHistoryOpen((open) => !open)}
      />
      {historyOpen && (
        <div id="version-history">
          <VersionHistory projectId={projectId} selected={viewSeq} onSelect={setViewSeq} />
        </div>
      )}
      <Figures result={result} />
      <Stage key={`${project.id}:${viewSeq}`} project={project} version={version} />
      <Notices result={result} />
      {!readOnly && <Variants project={project} />}

      <section
        aria-label="Details"
        className="rounded-xl border border-border bg-surface p-3 shadow-sm sm:p-4"
      >
        <Tabs tabs={tabs} active={active} onChange={setTab} />

        {hasParams && !readOnly && (
          <Panel tab="adjust" active={active}>
            <ParamEditor key={version} project={project} />
          </Panel>
        )}

        <Panel tab="bom" active={active}>
          <BomTable result={result} projectId={project.id} readOnly={readOnly} />
          <p className="mt-3 text-xs text-muted">
            {result.costs.note} Werkzeug, falls nicht vorhanden:{" "}
            {formatEur(result.costs.tools_optional.min)} –{" "}
            {formatEur(result.costs.tools_optional.max)}. Katalog{" "}
            {result.provenance.catalog_version}, Stand {result.provenance.catalog_as_of}.
          </p>
        </Panel>

        <Panel tab="cuts" active={active}>
          <CutList result={result} />
        </Panel>

        <Panel tab="steps" active={active}>
          <BuildSteps key={project.id} result={result} projectId={project.id} />
        </Panel>

        {notes.length > 0 && (
          <Panel tab="notes" active={active}>
            <Notes notes={notes} />
          </Panel>
        )}
      </section>

      <p className="flex gap-2 text-xs text-muted">
        <Icon name="shield" className="h-4 w-4" />
        <span>
          Planungshilfe – kein Standsicherheitsnachweis. Ob ein Vorhaben genehmigungspflichtig ist,
          regelt die Landesbauordnung; verbindlich ist die Auskunft des Bauamts. Engine{" "}
          {result.provenance.engine_version}, Entwurfsformat {result.provenance.design_version}
        </span>
      </p>
    </div>
  );
});
