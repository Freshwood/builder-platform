"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, type UIMessage } from "ai";
import { useCallback, useEffect, useRef, useState } from "react";

export type ToolProject = {
  project_id?: string;
  title?: string;
  summary?: string;
  trust?: string;
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

/** Chat state shared by the brief form, the chat column and the progress panel. */
export function useAssistant(projectId: string | null, onProjectChanged: (id: string) => void) {
  const [transport] = useState(
    () => new DefaultChatTransport({ api: "/api/chat", credentials: "include" }),
  );
  const { messages, sendMessage, regenerate, status, error } = useChat({ transport });
  const handled = useRef(new Set<string>());
  const busy = status === "submitted" || status === "streaming";
  const [startedAt, setStartedAt] = useState<number | null>(null);

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

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const current = busy && messages.at(-1)?.role === "assistant" ? (lastAssistant ?? null) : null;

  return {
    messages,
    status,
    error,
    busy,
    submit,
    retry,
    startedAt: busy ? startedAt : null,
    current,
  };
}

export type Assistant = ReturnType<typeof useAssistant>;

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
