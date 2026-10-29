import type { UIMessage } from "ai";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { projectChat } = vi.hoisted(() => ({ projectChat: vi.fn() }));
vi.mock("@/api", () => ({ projectChat }));

import {
  asToolPart,
  assistantErrorText,
  formatElapsed,
  loadStoredChat,
  messageText,
  toolName,
  toolOutputs,
} from "./assistant";

const message = (...parts: unknown[]) =>
  ({ id: "m1", role: "assistant", parts }) as unknown as UIMessage;
const part = (value: unknown) => value as UIMessage["parts"][number];

describe("assistantErrorText", () => {
  it.each([
    "Failed to fetch",
    "NetworkError when attempting to fetch resource.",
    "Load failed",
    "Not Found",
    "connect ECONNREFUSED 127.0.0.1:8000",
    "Bad Gateway",
  ])("says the connection failed for %j", (raw) => {
    expect(assistantErrorText(new Error(raw))).toBe(
      "Die Verbindung zum Assistenten ist fehlgeschlagen.",
    );
  });

  it.each(["Exceeded maximum retries for output validation", "Usage limit exceeded"])(
    "suggests rephrasing when the agent ran out of attempts (%j)",
    (raw) => {
      expect(assistantErrorText(new Error(raw))).toMatch(/keinen gültigen Entwurf erstellen/);
    },
  );

  it("falls back to a generic text for anything else, including no error at all", () => {
    expect(assistantErrorText(new Error("kaputt"))).toBe(
      "Der Assistent ist mit einem Fehler abgebrochen.",
    );
    expect(assistantErrorText(undefined)).toBe("Der Assistent ist mit einem Fehler abgebrochen.");
  });
});

describe("tool parts", () => {
  it("reads the tool name of static and dynamic tool parts", () => {
    expect(toolName(part({ type: "tool-plan_design" }))).toBe("plan_design");
    expect(toolName(part({ type: "dynamic-tool", toolName: "legacy_tool" }))).toBe("legacy_tool");
    expect(toolName(part({ type: "text", text: "x" }))).toBeNull();
  });

  it("exposes the output only once the tool has finished", () => {
    const running = asToolPart(
      part({ type: "tool-a", state: "input-available", input: { x: 1 }, output: { stale: true } }),
      "0",
    );
    expect(running).toMatchObject({ name: "a", state: "input-available", input: { x: 1 } });
    expect(running?.output).toBeUndefined();

    const done = asToolPart(
      part({ type: "tool-a", state: "output-available", output: { action: "created" } }),
      "1",
    );
    expect(done?.output).toEqual({ action: "created" });
  });

  it("is no tool part without a state or without a tool name", () => {
    expect(asToolPart(part({ type: "text", text: "x" }), "0")).toBeNull();
    expect(asToolPart(part({ type: "tool-a" }), "0")).toBeNull();
  });

  it("collects the outputs of all finished tool calls of a message", () => {
    const outputs = toolOutputs(
      message(
        { type: "tool-a", state: "output-available", output: { action: "created" } },
        { type: "text", text: "Hallo" },
        { type: "tool-b", state: "input-streaming" },
        { type: "dynamic-tool", toolName: "c", state: "output-available", output: { error: "x" } },
      ),
    );
    expect(outputs).toEqual([{ action: "created" }, { error: "x" }]);
  });
});

describe("messageText", () => {
  it("joins the text parts and ignores everything else", () => {
    expect(
      messageText(
        message(
          { type: "text", text: " Hallo " },
          { type: "reasoning", text: "geheim" },
          { type: "tool-a", state: "input-available" },
          { type: "text", text: "Welt\n" },
        ),
      ),
    ).toBe("Hallo Welt");
  });
});

describe("formatElapsed", () => {
  it.each([
    [0, "0:00"],
    [9, "0:09"],
    [65, "1:05"],
    [600, "10:00"],
  ])("shows %i seconds as %s", (seconds, expected) => {
    expect(formatElapsed(seconds)).toBe(expected);
  });
});

describe("loadStoredChat", () => {
  beforeEach(() => {
    projectChat.mockReset();
  });

  it("returns the stored conversation as UI messages, tool results included", async () => {
    const stored = [
      { id: "u1", role: "user", parts: [{ type: "text", text: "Regal 80 x 30" }] },
      {
        id: "a1",
        role: "assistant",
        parts: [
          { type: "text", text: "Ich plane das." },
          {
            type: "tool-plan_design",
            toolCallId: "call-1",
            state: "output-available",
            input: { design: {} },
            output: { action: "created", project: { project_id: "p1" } },
          },
        ],
      },
    ];
    projectChat.mockResolvedValue({ data: stored });
    const messages = await loadStoredChat("p1");
    expect(projectChat).toHaveBeenCalledWith({ path: { project_id: "p1" }, throwOnError: true });
    expect(messages).toHaveLength(2);
    expect(messageText(messages[1]!)).toBe("Ich plane das.");
    expect(toolOutputs(messages[1]!)).toEqual([
      { action: "created", project: { project_id: "p1" } },
    ]);
  });

  it("rejects data that is no conversation instead of putting it into the chat", async () => {
    projectChat.mockResolvedValue({ data: [{ id: "x", role: "robot", parts: "nope" }] });
    await expect(loadStoredChat("p1")).rejects.toThrow();
  });

  it("passes request errors on to the caller", async () => {
    projectChat.mockRejectedValue(new Error("Failed to fetch"));
    await expect(loadStoredChat("p1")).rejects.toThrow("Failed to fetch");
  });
});
