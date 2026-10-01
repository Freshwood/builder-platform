"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, type UIMessage } from "ai";
import { useEffect, useRef, useState, type FormEvent } from "react";

type ToolOutput = { action?: string; error?: string; project?: { project_id?: string } };

const EXAMPLES = [
  "Hochbeet 2 × 1 m, 80 cm hoch, aus Lärche",
  "Hochbeet 1,2 × 0,8 m mit Sitzkante",
];

function toolOutputs(message: UIMessage): ToolOutput[] {
  const outputs: ToolOutput[] = [];
  for (const part of message.parts) {
    if (
      (part.type.startsWith("tool-") || part.type === "dynamic-tool") &&
      "state" in part &&
      part.state === "output-available" &&
      "output" in part
    ) {
      outputs.push(part.output as ToolOutput);
    }
  }
  return outputs;
}

function messageText(message: UIMessage): string {
  return message.parts
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("")
    .trim();
}

export function Chat({
  projectId,
  onProjectChanged,
  autoFocus = false,
}: {
  projectId: string | null;
  onProjectChanged: (projectId: string) => void;
  autoFocus?: boolean;
}) {
  const [transport] = useState(
    () => new DefaultChatTransport({ api: "/api/chat", credentials: "include" }),
  );
  const { messages, sendMessage, status, error } = useChat({ transport });
  const [input, setInput] = useState("");
  const handled = useRef(new Set<string>());
  const busy = status === "submitted" || status === "streaming";

  useEffect(() => {
    for (const message of messages) {
      toolOutputs(message).forEach((output, index) => {
        const key = `${message.id}:${index}`;
        const id = output.project?.project_id;
        if (id && !handled.current.has(key)) {
          handled.current.add(key);
          onProjectChanged(id);
        }
      });
    }
  }, [messages, onProjectChanged]);

  function submit(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    // The active project travels with each request so the agent edits the right model.
    void sendMessage({ text: trimmed }, { body: { projectId } });
    setInput("");
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    submit(input);
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
        {messages.map((message) => {
          const text = messageText(message);
          const errors = toolOutputs(message).filter((o) => o.error);
          if (!text && errors.length === 0) return null;
          const isUser = message.role === "user";
          return (
            <li key={message.id} className={isUser ? "flex justify-end" : "flex justify-start"}>
              <div
                className={
                  isUser
                    ? "max-w-[85%] rounded-2xl rounded-br-sm bg-accent px-4 py-2 text-white dark:text-black"
                    : "max-w-[85%] rounded-2xl rounded-bl-sm border border-border bg-surface px-4 py-2"
                }
              >
                {!isUser && (
                  <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-ai">
                    KI-Assistent
                  </span>
                )}
                {text && <p className="whitespace-pre-wrap">{text}</p>}
                {errors.map((e, i) => (
                  <p key={i} className="text-sm text-warning">
                    {e.error}
                  </p>
                ))}
              </div>
            </li>
          );
        })}
        {status === "submitted" && (
          <li className="text-sm text-muted" aria-live="polite">
            Der Assistent plant …
          </li>
        )}
      </ol>

      {error && (
        <p role="alert" className="mt-2 text-sm text-warning">
          Die Verbindung zum Assistenten ist fehlgeschlagen. Bitte versuche es erneut.
        </p>
      )}

      {messages.length === 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => submit(example)}
              className="rounded-full border border-border bg-surface px-3 py-1 text-sm hover:bg-surface-muted"
            >
              {example}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={onSubmit} className="mt-3 flex gap-2">
        <label htmlFor="chat-input" className="sr-only">
          Was möchtest du bauen oder reparieren?
        </label>
        <input
          id="chat-input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={projectId ? "z. B. „Mach es 50 cm breiter“" : "Beschreibe dein Vorhaben …"}
          autoFocus={autoFocus}
          autoComplete="off"
          className="flex-1 rounded-lg border border-border bg-surface px-3 py-2"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="rounded-lg bg-accent px-4 py-2 font-medium text-white disabled:opacity-50 dark:text-black"
        >
          Senden
        </button>
      </form>
    </section>
  );
}
