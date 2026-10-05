"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { Chat } from "@/components/Chat";
import { ProjectPanel } from "@/components/ProjectPanel";
import { projectKey } from "@/lib/api";

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

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(320px,420px)_minmax(0,1fr)]">
      <div className="flex min-w-0 flex-col lg:sticky lg:top-4 lg:h-[calc(100vh-8rem)]">
        {!projectId && (
          <h1 className="mb-4 text-3xl font-bold tracking-tight">
            Was möchtest du bauen oder reparieren?
          </h1>
        )}
        <Chat projectId={projectId} onProjectChanged={onProjectChanged} autoFocus={!projectId} />
      </div>
      <div className="min-w-0">
        {projectId ? (
          <ProjectPanel projectId={projectId} />
        ) : (
          <div className="rounded-xl border border-dashed border-border p-8 text-muted">
            <p className="text-lg font-medium text-text">So funktioniert&apos;s</p>
            <ol className="mt-3 list-inside list-decimal space-y-1">
              <li>Beschreibe dein Vorhaben in eigenen Worten.</li>
              <li>Der Assistent fragt nach, was noch fehlt.</li>
              <li>
                Du erhältst Varianten, Zeichnungen, Materialliste, Kosten und eine Bauanleitung.
              </li>
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
              Freie Entwürfe brauchen ein angebundenes Sprachmodell. Tragende Bauwerke (Carport,
              Dach, Balkon) plant Homeworking nicht.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
