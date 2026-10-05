"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";

import { ActivityList } from "@/components/Activity";
import { AutoTextarea } from "@/components/AutoTextarea";
import { messageBlocks } from "@/lib/activity";
import {
  formatElapsed,
  toolOutputs,
  useElapsed,
  type Assistant,
  type ToolOutput,
} from "@/lib/assistant";

const ACTION_LABEL: Record<string, string> = {
  created: "Projekt erstellt",
  changed: "Projekt geändert",
  undone: "Änderung zurückgenommen",
};

function ProjectCard({ output }: { output: ToolOutput }) {
  const project = output.project;
  if (!project?.summary) return null;
  return (
    <div className="mt-2 rounded-xl border border-border bg-surface-muted px-3 py-2 text-sm">
      <span className="block text-xs font-semibold uppercase tracking-wide text-accent-strong">
        {ACTION_LABEL[output.action ?? ""] ?? "Projekt"}
        {project.trust === "ai_draft" && " · KI-Entwurf"}
      </span>
      <span className="block font-medium">{project.summary}</span>
      {project.material_cost_eur && (
        <span className="mt-1 inline-block rounded-full bg-accent px-2 py-0.5 text-xs font-semibold text-white dark:text-black">
          {project.material_cost_eur}
        </span>
      )}
    </div>
  );
}

function WorkingIndicator({ startedAt, waiting }: { startedAt: number | null; waiting: boolean }) {
  const elapsed = useElapsed(startedAt);
  return (
    <li className="flex items-center gap-2 text-sm text-muted" aria-live="polite">
      <span
        aria-hidden="true"
        className="h-3 w-3 animate-spin rounded-full border-2 border-ai/30 border-t-ai"
      />
      {waiting ? "Der Assistent liest deine Angaben …" : "Der Assistent arbeitet …"}
      <span className="font-mono tabular-nums">{formatElapsed(elapsed)}</span>
    </li>
  );
}

export function Chat({ assistant, projectId }: { assistant: Assistant; projectId: string | null }) {
  const { messages, status, error, busy, submit, startedAt } = assistant;
  const [input, setInput] = useState("");

  function send() {
    if (submit(input)) setInput("");
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    send();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends, Shift+Enter starts a new line.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  }

  return (
    <section aria-labelledby="chat-heading" className="flex flex-col lg:h-full">
      <h2 id="chat-heading" className="sr-only">
        Planungsassistent
      </h2>
      <p
        role="note"
        className="mb-3 rounded-md border border-ai/30 bg-ai-soft px-3 py-2 text-sm text-ai"
        data-testid="ai-disclosure"
      >
        Du sprichst mit einem KI-Assistenten. Maße, Mengen, Kosten und Zeichnungen berechnet
        Homeworking regelbasiert; die KI formuliert Fragen und Erklärungen.
      </p>

      <ol
        aria-live="polite"
        aria-label="Chatverlauf"
        tabIndex={0}
        className="max-h-[60vh] space-y-3 overflow-y-auto lg:max-h-none lg:flex-1"
        data-testid="messages"
      >
        {messages.map((message, index) => {
          const isUser = message.role === "user";
          const live = busy && index === messages.length - 1;
          const blocks = isUser
            ? [
                {
                  kind: "text" as const,
                  key: "t",
                  text: message.parts.map((p) => (p.type === "text" ? p.text : "")).join(""),
                },
              ]
            : messageBlocks(message, live);
          const outputs = toolOutputs(message);
          const errors = outputs.filter((o) => o.error && !o.errors);
          const cards = outputs.filter((o) => o.project?.summary);
          if (!blocks.length && errors.length === 0 && cards.length === 0) return null;
          return (
            <li key={message.id} className={isUser ? "flex justify-end" : "flex justify-start"}>
              <div
                className={
                  isUser
                    ? "max-w-[85%] rounded-2xl rounded-br-sm bg-accent px-4 py-2 text-white dark:text-black"
                    : "w-full max-w-[92%] rounded-2xl rounded-bl-sm border border-border bg-surface px-4 py-2"
                }
              >
                {!isUser && (
                  <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-ai">
                    KI-Assistent
                  </span>
                )}
                {blocks.map((block) =>
                  block.kind === "text" ? (
                    <p key={block.key} className="whitespace-pre-wrap">
                      {block.text.trim()}
                    </p>
                  ) : (
                    <ActivityList key={block.key} steps={block.steps} reasoning={block.reasoning} />
                  ),
                )}
                {cards.map((output, i) => (
                  <ProjectCard key={i} output={output} />
                ))}
                {errors.map((e, i) => (
                  <p key={i} className="text-sm text-warning">
                    {e.error}
                  </p>
                ))}
              </div>
            </li>
          );
        })}
        {busy && <WorkingIndicator startedAt={startedAt} waiting={status === "submitted"} />}
      </ol>

      {error && (
        <p role="alert" className="mt-2 text-sm text-warning">
          Die Verbindung zum Assistenten ist fehlgeschlagen. Bitte versuche es erneut.
        </p>
      )}

      <form onSubmit={onSubmit} className="mt-3">
        <label htmlFor="chat-input" className="sr-only">
          Was möchtest du bauen oder reparieren?
        </label>
        <div className="flex items-end gap-2 rounded-2xl border border-border bg-surface p-2 shadow-sm focus-within:border-accent">
          <AutoTextarea
            id="chat-input"
            value={input}
            onChange={setInput}
            onKeyDown={onKeyDown}
            minRows={2}
            maxRows={8}
            placeholder={
              projectId
                ? "Was soll anders werden? z. B. „Mach es 50 cm breiter“ oder „Mit Rückwand“"
                : "Antworte dem Assistenten oder beschreibe weitere Wünsche …"
            }
            className="flex-1 resize-none bg-transparent px-2 py-1 outline-none"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-xl bg-accent px-4 py-2 font-medium text-white disabled:opacity-50 dark:text-black"
          >
            Senden
          </button>
        </div>
        <p className="mt-1 px-1 text-xs text-muted">
          Enter sendet, Umschalt + Enter für eine neue Zeile.
        </p>
      </form>
    </section>
  );
}
