import type { UIMessage } from "ai";
import { describe, expect, it } from "vitest";

import { designProgress, messageBlocks, planningStages } from "./activity";

/** A message from raw parts: the streamed parts are looser than the SDK's strict part types. */
const message = (...parts: unknown[]) =>
  ({ id: "m1", role: "assistant", parts }) as unknown as UIMessage;

const text = (value: string) => ({ type: "text", text: value });
const tool = (name: string, state: string, extra: Record<string, unknown> = {}) => ({
  type: `tool-${name}`,
  toolCallId: `call-${name}`,
  state,
  ...extra,
});

describe("designProgress", () => {
  it("names the parts and counts the steps of a design the model is still writing", () => {
    const input = {
      design: {
        parts: [{ name: "Seitenwand" }, { name: "Fachboden" }, { name: "Fachboden" }],
        steps: [{}, {}],
      },
    };
    expect(designProgress(input)).toEqual({
      parts: ["Seitenwand", "Fachboden", "Fachboden"],
      steps: 2,
    });
  });

  it("skips half-streamed parts that have no usable name yet", () => {
    const input = {
      design: { parts: [undefined, {}, { name: "" }, { name: 7 }, { name: "Boden" }] },
    };
    expect(designProgress(input).parts).toEqual(["Boden"]);
  });

  it("copes with missing or foreign input", () => {
    expect(designProgress(undefined)).toEqual({ parts: [], steps: 0 });
    expect(designProgress({ design: {} })).toEqual({ parts: [], steps: 0 });
    expect(designProgress("text")).toEqual({ parts: [], steps: 0 });
  });
});

describe("messageBlocks", () => {
  it("joins neighbouring text parts and skips blank ones", () => {
    const blocks = messageBlocks(
      message(text("Hallo "), text(""), text("Welt"), text("  ")),
      false,
    );
    expect(blocks).toEqual([{ kind: "text", key: "t0", text: "Hallo Welt" }]);
  });

  it("groups tool calls and reasoning between texts into one activity block", () => {
    const blocks = messageBlocks(
      message(
        text("Ich plane das."),
        { type: "reasoning", text: "Erst die Maße.", state: "done" },
        tool("list_materials", "output-available", { output: {} }),
        text("Fertig."),
      ),
      false,
    );
    expect(blocks.map((b) => b.kind)).toEqual(["text", "activity", "text"]);
    const activity = blocks[1];
    expect(activity?.kind === "activity" && activity.reasoning).toBe("Erst die Maße.");
    expect(activity?.kind === "activity" && activity.steps.map((s) => [s.label, s.state])).toEqual([
      ["Nachgedacht", "done"],
      ["Materialkatalog gelesen", "done"],
    ]);
  });

  it("shows reasoning as running only while the message is live and still streaming", () => {
    const streaming = message({ type: "reasoning", text: "…", state: "streaming" });
    const step = (live: boolean) => {
      const block = messageBlocks(streaming, live)[0];
      return block?.kind === "activity" ? block.steps[0] : undefined;
    };
    expect(step(true)).toMatchObject({ label: "Denke nach …", state: "running" });
    expect(step(false)).toMatchObject({ label: "Nachgedacht", state: "done" });
  });

  it("labels tool calls by phase and falls back for tools it does not know", () => {
    const steps = (part: unknown) => {
      const block = messageBlocks(message(part), false)[0];
      return block?.kind === "activity" ? block.steps : [];
    };
    expect(steps(tool("change_project", "input-available"))).toMatchObject([
      { label: "Berechne die Änderung …", state: "running" },
    ]);
    expect(steps(tool("change_project", "output-available", { output: {} }))).toMatchObject([
      { label: "Änderung berechnet", state: "done" },
    ]);
    expect(
      steps(tool("change_project", "output-available", { output: { error: "Ungültig" } })),
    ).toMatchObject([{ label: "Änderung berechnet", state: "warning", detail: "Ungültig" }]);
    expect(steps(tool("change_project", "output-error", { errorText: "Abbruch" }))).toMatchObject([
      { state: "error", detail: "Abbruch" },
    ]);
    expect(steps(tool("future_tool", "input-available"))).toMatchObject([
      { label: "Arbeite …", state: "running" },
    ]);
  });

  it("reports the progress of a design tool from writing to computed", () => {
    const design = (state: string, extra: Record<string, unknown> = {}) => {
      const block = messageBlocks(message(tool("save_design", state, extra)), false)[0];
      return block?.kind === "activity" ? block.steps[0] : undefined;
    };
    const input = { design: { parts: [{ name: "A" }, { name: "B" }], steps: [{}] } };
    expect(design("input-streaming", { input })).toMatchObject({
      label: "Entwerfe die Konstruktion …",
      detail: "2 Bauteile · 1 Bauschritt",
      state: "running",
    });
    expect(design("input-streaming")).toMatchObject({ detail: "Die KI schreibt den Entwurf" });
    expect(design("input-available", { input })).toMatchObject({
      label: "Engine prüft und berechnet den Entwurf …",
      state: "running",
    });
    expect(design("output-available", { input, output: {} })).toMatchObject({
      label: "Konstruktion berechnet",
      state: "done",
    });
    expect(
      design("output-available", { input, output: { error: "Kollision", errors: ["a", "b"] } }),
    ).toMatchObject({ state: "warning", detail: "2 Punkte" });
    expect(design("output-error", { errorText: "Timeout" })).toMatchObject({
      label: "Entwurf fehlgeschlagen",
      detail: "Timeout",
      state: "error",
    });
  });

  it("still labels the tools of stored chats from older prompt versions", () => {
    const block = messageBlocks(message(tool("design_project", "input-available")), false)[0];
    expect(block?.kind === "activity" && block.steps[0]?.label).toBe(
      "Engine prüft und berechnet den Entwurf …",
    );
  });
});

describe("planningStages", () => {
  const states = (msg: UIMessage | null) => planningStages(msg).map((s) => s.state);

  it("waits for the model before anything has happened", () => {
    expect(states(null)).toEqual(["running", "pending", "pending", "pending"]);
    expect(states(message())).toEqual(["running", "pending", "pending", "pending"]);
  });

  it("moves on once the model answers and picks a construction", () => {
    expect(states(message(text("Ich plane ein Regal.")))).toEqual([
      "done",
      "running",
      "pending",
      "pending",
    ]);
    expect(states(message(tool("plan_design", "input-streaming")))).toEqual([
      "done",
      "running",
      "pending",
      "pending",
    ]);
  });

  it("checks and computes while the engine works on the design", () => {
    expect(states(message(tool("plan_design", "input-available")))).toEqual([
      "done",
      "done",
      "running",
      "pending",
    ]);
  });

  it("is finished only when the engine accepted the design", () => {
    expect(states(message(tool("plan_design", "output-available", { output: {} })))).toEqual([
      "done",
      "done",
      "done",
      "done",
    ]);
    // The engine rejected the design: the model corrects it, so the check is still running.
    expect(
      states(message(tool("plan_design", "output-available", { output: { error: "zu breit" } }))),
    ).toEqual(["done", "done", "running", "pending"]);
  });

  it("follows the latest design attempt", () => {
    const retried = message(
      tool("plan_design", "output-available", { output: { error: "zu breit" } }),
      { ...tool("plan_design", "input-streaming"), toolCallId: "call-2" },
    );
    expect(states(retried)).toEqual(["done", "running", "pending", "pending"]);
  });
});
