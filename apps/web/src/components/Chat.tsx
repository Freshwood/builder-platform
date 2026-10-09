"use client";

import clsx from "clsx";
import type { UIMessage } from "ai";
import { memo, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { ActivityList } from "@/components/Activity";
import { AutoTextarea } from "@/components/AutoTextarea";
import { Icon, Spinner } from "@/components/ui";
import { messageBlocks } from "@/lib/activity";
import {
  assistantErrorText,
  formatElapsed,
  toolOutputs,
  useElapsed,
  type Assistant,
  type ToolOutput,
} from "@/lib/assistant";

const ACTION_LABEL: Record<string, string> = {
  created: "Projekt erstellt",
  changed: "Projekt geändert",
  replanned: "Neue Version",
  undone: "Änderung zurückgenommen",
};

/** One-tap follow-ups once a project exists; they are sent as normal chat messages. */
const QUICK_ACTIONS = [
  "Mach es günstiger",
  "Mach es stabiler",
  "Erklär mir die Konstruktion",
  "Welche Holzart passt besser?",
];

function ProjectCard({ output }: { output: ToolOutput }) {
  const project = output.project;
  if (!project?.summary) return null;
  return (
    <div className="mt-2 flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 text-sm shadow-sm">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent-soft text-accent-strong">
        <Icon name="cube" className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-xs font-semibold text-accent-strong">
          {ACTION_LABEL[output.action ?? ""] ?? "Projekt"}
          {project.trust === "ai_draft" && ", KI-Entwurf"}
        </span>
        <span className="block truncate font-medium">{project.summary}</span>
      </span>
      {project.material_cost_eur && (
        <span className="shrink-0 text-xs font-semibold tabular-nums text-muted">
          {project.material_cost_eur}
        </span>
      )}
    </div>
  );
}

function WorkingIndicator({ startedAt, waiting }: { startedAt: number | null; waiting: boolean }) {
  const elapsed = useElapsed(startedAt);
  return (
    <li className="flex items-center gap-2 pl-9 text-sm text-muted" aria-live="polite">
      <span className="flex gap-1" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 animate-bounce rounded-full bg-ai"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </span>
      {waiting ? "liest deine Angaben" : "arbeitet"}
      <span className="text-xs tabular-nums">{formatElapsed(elapsed)}</span>
    </li>
  );
}

function Avatar() {
  return (
    <span
      aria-hidden="true"
      className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-ai text-surface"
    >
      <Icon name="sparkles" className="h-4 w-4" />
    </span>
  );
}

/**
 * One chat message. Memoised: while the assistant streams, only the last message changes, so
 * earlier messages skip re-parsing their parts on every update.
 */
const MessageItem = memo(function MessageItem({
  message,
  live,
}: {
  message: UIMessage;
  live: boolean;
}) {
  const isUser = message.role === "user";
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
  if (isUser) {
    return (
      <li className="flex animate-fadein justify-end">
        <p className="max-w-[88%] rounded-xl rounded-br-sm bg-surface-muted px-4 py-2.5 whitespace-pre-wrap">
          {blocks[0]?.kind === "text" ? blocks[0].text.trim() : ""}
        </p>
      </li>
    );
  }
  return (
    <li className="flex animate-fadein gap-2">
      <Avatar />
      <div className="min-w-0 flex-1">
        <span className="sr-only">KI-Assistent: </span>
        {blocks.map((block) =>
          block.kind === "text" ? (
            <p key={block.key} className="leading-relaxed whitespace-pre-wrap">
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
          <p key={i} className="mt-1 text-sm text-warning">
            {e.error}
          </p>
        ))}
      </div>
    </li>
  );
});

export function Chat({ assistant, projectId }: { assistant: Assistant; projectId: string | null }) {
  const { messages, status, error, busy, submit, retry, startedAt } = assistant;
  const [input, setInput] = useState("");
  const listRef = useRef<HTMLOListElement>(null);

  const count = messages.length;
  const shownCount = useRef(0);

  // Follow the conversation while it grows: glide to a new message, but keep up with a
  // streaming answer instantly (a smooth scroll per update stutters) and only while the user
  // has not scrolled up to read.
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    if (count !== shownCount.current) {
      shownCount.current = count;
      list.scrollTo({ top: list.scrollHeight, behavior: "smooth" });
    } else if (list.scrollHeight - list.scrollTop - list.clientHeight < 160) {
      list.scrollTop = list.scrollHeight;
    }
  }, [messages, count, busy]);

  function send(text = input) {
    if (submit(text) && text === input) setInput("");
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
    <section aria-labelledby="chat-heading" className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Avatar />
        <div className="min-w-0">
          <h2 id="chat-heading" className="text-sm font-semibold">
            Planungsassistent
          </h2>
          <p role="note" className="text-xs text-muted" data-testid="ai-disclosure">
            KI-Assistent. Maße, Mengen, Kosten und Zeichnungen rechnet Homeworking regelbasiert.
          </p>
        </div>
      </div>

      <ol
        ref={listRef}
        aria-live="polite"
        aria-label="Chatverlauf"
        tabIndex={0}
        className="scrollbar-thin min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4"
        data-testid="messages"
      >
        {messages.map((message, index) => (
          <MessageItem
            key={message.id}
            message={message}
            live={busy && index === messages.length - 1}
          />
        ))}
        {busy && <WorkingIndicator startedAt={startedAt} waiting={status === "submitted"} />}
      </ol>

      <div className="border-t border-border bg-bg/60 px-3 pt-2 pb-3 backdrop-blur">
        {error && (
          <div
            role="alert"
            className="mb-2 flex items-center gap-2 rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-sm text-warning"
          >
            <Icon name="warning" className="h-4 w-4" />
            <span className="flex-1" title={error.message}>
              {assistantErrorText(error)}
            </span>
            <button
              type="button"
              onClick={retry}
              className="inline-flex items-center gap-1 rounded-lg px-2 py-0.5 font-medium hover:bg-warning/10"
            >
              <Icon name="rotate" className="h-4 w-4" /> Erneut versuchen
            </button>
          </div>
        )}

        {projectId && !busy && (
          <ul
            className="scrollbar-thin -mx-1 mb-2 flex gap-1.5 overflow-x-auto px-1 pb-0.5"
            aria-label="Vorschläge"
          >
            {QUICK_ACTIONS.map((action) => (
              <li key={action} className="shrink-0">
                <button
                  type="button"
                  onClick={() => send(action)}
                  className="rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium whitespace-nowrap text-muted transition hover:border-text/40 hover:text-text"
                >
                  {action}
                </button>
              </li>
            ))}
          </ul>
        )}

        <form onSubmit={onSubmit}>
          <label htmlFor="chat-input" className="sr-only">
            Was möchtest du bauen oder reparieren?
          </label>
          <div
            className={clsx(
              "flex items-end gap-2 rounded-xl border border-border bg-surface py-1.5 pr-1.5 pl-4 shadow-sm transition focus-within:border-text focus-within:ring-1 focus-within:ring-text",
            )}
          >
            <AutoTextarea
              id="chat-input"
              value={input}
              onChange={setInput}
              onKeyDown={onKeyDown}
              minRows={1}
              maxRows={8}
              placeholder={
                projectId
                  ? "Was soll anders werden? z. B. „50 cm breiter“"
                  : "Antworte dem Assistenten …"
              }
              className="flex-1 resize-none bg-transparent py-1.5 outline-none"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              aria-label="Senden"
              title="Senden (Enter)"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-on-accent transition hover:brightness-110 active:scale-95 disabled:opacity-30"
            >
              {busy ? <Spinner /> : <Icon name="send" className="h-4 w-4 -rotate-90" />}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
