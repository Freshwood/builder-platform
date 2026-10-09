"use client";

import { projectChat } from "@homeworking/api-client";
import { useQueryClient } from "@tanstack/react-query";
import type { UIMessage } from "ai";
import clsx from "clsx";
import { useCallback, useEffect, useState } from "react";

import { PlanningProgress, PlanningStopped } from "@/components/Activity";
import { Chat } from "@/components/Chat";
import { Landing } from "@/components/Landing";
import { ProjectPanel } from "@/components/ProjectPanel";
import { Icon, Spinner } from "@/components/ui";
import { projectKey } from "@/lib/api";
import { messageBlocks } from "@/lib/activity";
import { assistantErrorText, messageText, useAssistant } from "@/lib/assistant";
import { EMPTY_BRIEF, type Brief } from "@/lib/brief";

type MobileView = "chat" | "project";

export function Workspace({ initialProjectId = null }: { initialProjectId?: string | null }) {
  const [projectId, setProjectId] = useState<string | null>(initialProjectId);
  const [brief, setBrief] = useState<Brief>(EMPTY_BRIEF);
  const [mobileView, setMobileView] = useState<MobileView>("project");
  const queryClient = useQueryClient();

  const onProjectChanged = useCallback(
    (id: string) => {
      setProjectId(id);
      setMobileView("project");
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
  const { restore } = assistant;

  // An opened project brings its stored conversation along (it survives reloads).
  useEffect(() => {
    if (!initialProjectId) return;
    let cancelled = false;
    void projectChat({ path: { project_id: initialProjectId } }).then(({ data }) => {
      if (!cancelled && data?.length) restore(data as unknown as UIMessage[]);
    });
    return () => {
      cancelled = true;
    };
  }, [initialProjectId, restore]);
  const lastRequest = [...assistant.messages].reverse().find((m) => m.role === "user");
  const lastMessage = assistant.messages.at(-1);
  const lastReply = lastMessage?.role === "assistant" ? messageText(lastMessage) : "";
  const runningStep = assistant.current
    ? messageBlocks(assistant.current, true)
        .flatMap((block) => (block.kind === "activity" ? block.steps : []))
        .filter((step) => step.state === "running")
        .at(-1)
    : undefined;

  // "/" jumps into the chat from anywhere, like in most chat and search apps.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (event.key !== "/" || target?.closest("input, textarea, select, [contenteditable]"))
        return;
      const input =
        document.getElementById("chat-input") ?? document.getElementById("brief-description");
      if (!input) return;
      event.preventDefault();
      setMobileView("chat");
      input.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!projectId && assistant.messages.length === 0) {
    return (
      <Landing
        brief={brief}
        onBriefChange={setBrief}
        onSubmit={(message) => {
          const sent = assistant.submit(message);
          if (sent) setMobileView("project");
          return sent;
        }}
        busy={assistant.busy}
      />
    );
  }

  return (
    <div className="lg:grid lg:h-[calc(100dvh-3.5rem)] lg:grid-cols-[400px_minmax(0,1fr)]">
      <aside
        className={clsx(
          "h-[calc(100dvh-3.5rem-4rem)] border-border bg-surface lg:block lg:h-auto lg:min-h-0 lg:border-r",
          mobileView === "chat" ? "block" : "hidden",
        )}
      >
        <Chat assistant={assistant} projectId={projectId} />
      </aside>

      <div
        className={clsx(
          "min-w-0 lg:block lg:overflow-y-auto",
          mobileView === "project" ? "block" : "hidden",
        )}
      >
        <div className="mx-auto max-w-6xl px-4 pt-5 pb-24 sm:px-6 lg:pb-10">
          {projectId ? (
            <>
              {assistant.busy && (
                <p
                  role="status"
                  className="sticky top-3 z-20 mx-auto mb-4 flex w-fit items-center gap-2 rounded-full border border-ai/30 bg-ai-soft/95 px-4 py-2 text-sm font-medium text-ai shadow-lg backdrop-blur"
                >
                  <Spinner />
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
            // The turn ended without a project (follow-up question or failure): never leave a
            // frozen progress panel behind.
            <PlanningStopped
              request={lastRequest ? messageText(lastRequest) : ""}
              reply={lastReply}
              failed={assistant.error ? assistantErrorText(assistant.error) : null}
              onAnswer={() => {
                setMobileView("chat");
                // Focus after the chat column became visible on small screens.
                requestAnimationFrame(() => document.getElementById("chat-input")?.focus());
              }}
              onRetry={assistant.retry}
            />
          )}
        </div>
      </div>

      {/* Mobile switch between conversation and project */}
      <nav
        aria-label="Bereich"
        className="fixed inset-x-0 bottom-0 z-30 flex justify-center border-t border-border bg-surface/90 px-4 py-2.5 backdrop-blur lg:hidden"
      >
        <div className="inline-flex rounded-lg bg-surface-muted p-1">
          {(
            [
              { key: "chat", label: "Chat", icon: "message" },
              { key: "project", label: "Projekt", icon: "cube" },
            ] as const
          ).map((item) => (
            <button
              key={item.key}
              type="button"
              aria-pressed={mobileView === item.key}
              onClick={() => setMobileView(item.key)}
              className={clsx(
                "inline-flex items-center gap-1.5 rounded-md px-5 py-1.5 text-sm font-medium transition",
                mobileView === item.key ? "bg-surface shadow-sm" : "text-muted",
              )}
            >
              <Icon name={item.icon} className="h-4 w-4" />
              {item.label}
              {item.key === "chat" && assistant.busy && (
                <span className="h-2 w-2 animate-pulse rounded-full bg-ai" aria-hidden="true" />
              )}
            </button>
          ))}
        </div>
      </nav>
    </div>
  );
}
