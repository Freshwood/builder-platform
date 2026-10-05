"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { PlanningProgress } from "@/components/Activity";
import { Chat } from "@/components/Chat";
import { ProjectBrief } from "@/components/ProjectBrief";
import { ProjectPanel } from "@/components/ProjectPanel";
import { projectKey } from "@/lib/api";
import { messageText, useAssistant } from "@/lib/assistant";
import { messageBlocks } from "@/lib/activity";

export function Workspace({ initialProjectId = null }: { initialProjectId?: string | null }) {
  const [projectId, setProjectId] = useState<string | null>(initialProjectId);
  const queryClient = useQueryClient();

  const onProjectChanged = useCallback(
    (id: string) => {
      setProjectId(id);
      void queryClient.invalidateQueries({ queryKey: projectKey(id) });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      // Keep the chat mounted but make the URL shareable/bookmarkable.
      if (window.location.pathname !== `/projects/${id}`) {
        window.history.replaceState(null, "", `/projects/${id}`);
      }
    },
    [queryClient],
  );

  const assistant = useAssistant(projectId, onProjectChanged);
  const lastRequest = [...assistant.messages].reverse().find((m) => m.role === "user");
  const runningStep = assistant.current
    ? messageBlocks(assistant.current, true)
        .flatMap((block) => (block.kind === "activity" ? block.steps : []))
        .filter((step) => step.state === "running")
        .at(-1)
    : undefined;

  if (!projectId && assistant.messages.length === 0) {
    return (
      <div className="mx-auto max-w-4xl">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Was möchtest du bauen oder reparieren?
        </h1>
        <p className="mt-2 text-muted">
          Beschreibe dein Vorhaben – du erhältst Varianten, Zeichnungen, Materialliste, Kosten und
          eine Schritt-für-Schritt-Bauanleitung.
        </p>
        <p
          role="note"
          className="mt-4 rounded-md border border-ai/30 bg-ai-soft px-3 py-2 text-sm text-ai"
          data-testid="ai-disclosure"
        >
          Du sprichst mit einem KI-Assistenten. Maße, Mengen, Kosten und Zeichnungen berechnet
          Homeworking regelbasiert; die KI formuliert Fragen und Erklärungen.
        </p>
        <div className="mt-4">
          <ProjectBrief onSubmit={assistant.submit} busy={assistant.busy} />
        </div>
        <HowItWorks />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(320px,420px)_minmax(0,1fr)]">
      <div className="flex min-w-0 flex-col lg:sticky lg:top-4 lg:h-[calc(100vh-8rem)]">
        <Chat assistant={assistant} projectId={projectId} />
      </div>
      <div className="min-w-0">
        {projectId ? (
          <>
            {assistant.busy && (
              <p
                role="status"
                className="mb-3 flex items-center gap-2 rounded-xl border border-ai/30 bg-ai-soft px-3 py-2 text-sm text-ai"
              >
                <span
                  aria-hidden="true"
                  className="h-3 w-3 animate-spin rounded-full border-2 border-ai/30 border-t-ai"
                />
                {runningStep?.label ?? "Der Assistent arbeitet am Projekt …"}
              </p>
            )}
            <ProjectPanel projectId={projectId} />
          </>
        ) : assistant.busy ? (
          <PlanningProgress
            request={lastRequest ? messageText(lastRequest) : ""}
            current={assistant.current}
            startedAt={assistant.startedAt}
          />
        ) : (
          <HowItWorks />
        )}
      </div>
    </div>
  );
}

function HowItWorks() {
  return (
    <div className="mt-6 rounded-xl border border-dashed border-border p-6 text-muted lg:mt-0">
      <p className="text-lg font-medium text-text">So funktioniert&apos;s</p>
      <ol className="mt-3 list-inside list-decimal space-y-1">
        <li>Beschreibe dein Vorhaben in eigenen Worten und ergänze die Details.</li>
        <li>Der Assistent fragt nach, was noch fehlt.</li>
        <li>Du erhältst Varianten, Zeichnungen, Materialliste, Kosten und eine Bauanleitung.</li>
        <li>Ändere alles per Chat („50 cm breiter“) oder direkt im Formular.</li>
      </ol>
      <ul className="mt-5 grid gap-3 sm:grid-cols-3">
        <li className="rounded-xl border border-border bg-surface p-3">
          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">
            Geprüftes Pack
          </span>
          <p className="mt-2 text-sm text-text">Hochbeet aus Holz</p>
        </li>
        <li className="rounded-xl border border-border bg-surface p-3">
          <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs font-semibold text-sky-800 dark:bg-sky-950 dark:text-sky-200">
            Vorlagen
          </span>
          <p className="mt-2 text-sm text-text">Regal, Gartenbank, Werkbank, Fensterladen</p>
        </li>
        <li className="rounded-xl border border-border bg-surface p-3">
          <span className="rounded-full bg-ai-soft px-2 py-0.5 text-xs font-semibold text-ai">
            KI-Entwurf
          </span>
          <p className="mt-2 text-sm text-text">
            Alles aus Holz, Platten und Beschlägen – frei beschrieben
          </p>
        </li>
      </ul>
      <p className="mt-3 text-xs">
        Freie Entwürfe brauchen ein angebundenes Sprachmodell. Tragende Bauwerke (Carport, Dach,
        Balkon) plant Homeworking nicht.
      </p>
    </div>
  );
}
