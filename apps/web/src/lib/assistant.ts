"use client";

import { projectChat } from "@/api";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, safeValidateUIMessages, type UIMessage } from "ai";
import { useCallback, useEffect, useRef, useState } from "react";

import { sessionReady } from "@/lib/session";

export type ToolProject = {
  project_id?: string;
  title?: string;
  summary?: string;
  material_cost_eur?: string;
};
export type ToolOutput = {
  action?: string;
  error?: string;
  errors?: string[];
  project?: ToolProject;
};

/** A tool call part of a message, independent of static or dynamic tool typing. */
export type ToolPart = {
  key: string;
  name: string;
  state: string;
  input?: unknown;
  output?: ToolOutput;
  errorText?: string;
};

export function toolName(part: UIMessage["parts"][number]): string | null {
  if (part.type === "dynamic-tool") return (part as { toolName: string }).toolName;
  if (part.type.startsWith("tool-")) return part.type.slice("tool-".length);
  return null;
}

export function asToolPart(part: UIMessage["parts"][number], key: string): ToolPart | null {
  const name = toolName(part);
  if (!name || !("state" in part)) return null;
  const raw = part as { state: string; input?: unknown; output?: unknown; errorText?: string };
  return {
    key,
    name,
    state: raw.state,
    input: raw.input,
    output: raw.state === "output-available" ? (raw.output as ToolOutput) : undefined,
    errorText: raw.errorText,
  };
}

export function toolOutputs(message: UIMessage): ToolOutput[] {
  return message.parts
    .map((part, index) => asToolPart(part, String(index)))
    .filter((part): part is ToolPart => Boolean(part?.output))
    .map((part) => part.output!);
}

export function messageText(message: UIMessage): string {
  return message.parts
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("")
    .trim();
}

/** User-facing text for a failed assistant turn: unreachable API vs. an aborted agent run. */
export function assistantErrorText(error: Error | undefined): string {
  const message = error?.message ?? "";
  if (
    /failed to fetch|networkerror|load failed|not found|econnrefused|bad gateway/i.test(message)
  ) {
    return "Die Verbindung zum Assistenten ist fehlgeschlagen.";
  }
  if (/retries|limit/i.test(message)) {
    return "Der Assistent konnte diesmal keinen gültigen Entwurf erstellen. Versuche es erneut oder formuliere die Anfrage etwas anders.";
  }
  return "Der Assistent ist mit einem Fehler abgebrochen.";
}

/** Chat state shared by the brief form, the chat column and the progress panel. */
export function useAssistant(projectId: string | null, onProjectChanged: (id: string) => void) {
  const [transport] = useState(
    () =>
      new DefaultChatTransport({
        api: "/api/chat",
        credentials: "include",
        // The server keeps the conversation (stored agent runs); send only the new message
        // instead of re-uploading the whole chat incl. designs and tool results every turn.
        prepareSendMessagesRequest: ({ id, messages, body, trigger, messageId }) => ({
          body: { ...body, id, trigger, messageId, messages: messages.slice(-1) },
        }),
        fetch: async (input, init) => {
          await sessionReady();
          return fetch(input, init);
        },
      }),
  );
  // Batch stream updates: re-rendering the chat per token costs more than it shows.
  const { messages, sendMessage, regenerate, setMessages, status, error } = useChat({
    transport,
    throttle: 50,
  });
  const handled = useRef(new Set<string>());
  const busy = status === "submitted" || status === "streaming";
  const [startedAt, setStartedAt] = useState<number | null>(null);

  // Only the streaming (last) message gains tool results; earlier ones were handled already.
  const latest = messages.at(-1);
  useEffect(() => {
    for (const message of latest ? [latest] : []) {
      toolOutputs(message).forEach((output, index) => {
        const key = `${message.id}:${index}`;
        const id = output.project?.project_id;
        if (id && !handled.current.has(key)) {
          handled.current.add(key);
          onProjectChanged(id);
        }
      });
    }
  }, [latest, onProjectChanged]);

  const submit = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return false;
      setStartedAt(Date.now());
      // The active project travels with each request so the agent edits the right model.
      void sendMessage({ text: trimmed }, { body: { projectId } });
      return true;
    },
    [busy, projectId, sendMessage],
  );

  /** Run the last turn again after a failed request. */
  const retry = useCallback(() => {
    if (busy) return;
    setStartedAt(Date.now());
    void regenerate({ body: { projectId } });
  }, [busy, projectId, regenerate]);

  /** Show a stored conversation; its project links must not switch the project again. */
  const restore = useCallback(
    (stored: UIMessage[]) => {
      for (const message of stored) {
        toolOutputs(message).forEach((_, index) => handled.current.add(`${message.id}:${index}`));
      }
      setMessages((current) => (current.length ? current : stored));
    },
    [setMessages],
  );

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const current = busy && messages.at(-1)?.role === "assistant" ? (lastAssistant ?? null) : null;

  return {
    messages,
    status,
    error,
    busy,
    submit,
    retry,
    restore,
    startedAt: busy ? startedAt : null,
    current,
  };
}

export type Assistant = ReturnType<typeof useAssistant>;

/** The stored conversation of a project; messages that are not valid UI messages fail the load. */
export async function loadStoredChat(projectId: string): Promise<UIMessage[]> {
  const { data } = await projectChat({ path: { project_id: projectId }, throwOnError: true });
  const result = await safeValidateUIMessages({ messages: data });
  if (!result.success) throw result.error;
  return result.data;
}

/**
 * Load the stored conversation of an opened project into the chat (it survives reloads).
 * ``error`` is set when that failed, so the chat can say so instead of looking empty.
 */
export function useStoredChat(
  projectId: string | null,
  restore: (messages: UIMessage[]) => void,
): { error: boolean; reload: () => void } {
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    loadStoredChat(projectId).then(
      (stored) => {
        if (cancelled) return;
        setError(false);
        if (stored.length) restore(stored);
      },
      () => {
        if (!cancelled) setError(true);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [projectId, attempt, restore]);

  return { error, reload: () => setAttempt((n) => n + 1) };
}

/** Seconds since ``since`` while it is set, refreshed every second. */
export function useElapsed(since: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (since === null) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [since]);
  return since === null ? 0 : Math.max(0, Math.floor((now - since) / 1000));
}

export function formatElapsed(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
