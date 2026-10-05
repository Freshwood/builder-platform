import type { UIMessage } from "ai";

import { asToolPart, type ToolPart } from "@/lib/assistant";

export type StepState = "running" | "done" | "warning" | "error";

export type ActivityStep = {
  key: string;
  label: string;
  detail?: string;
  state: StepState;
};

type Labels = { running: string; done: string };

const TOOL_LABELS: Record<string, Labels> = {
  list_construction_packs: { running: "Prüfe Vorlagen …", done: "Vorlagen geprüft" },
  list_materials: { running: "Lese Materialkatalog …", done: "Materialkatalog gelesen" },
  get_template_design: {
    running: "Sehe mir eine Beispielkonstruktion an …",
    done: "Beispielkonstruktion angesehen",
  },
  get_current_design: { running: "Lade aktuellen Entwurf …", done: "Aktuellen Entwurf geladen" },
  get_project: { running: "Lese das Projekt …", done: "Projekt gelesen" },
  create_project: { running: "Berechne das Projekt …", done: "Projekt berechnet" },
  create_from_template: { running: "Berechne die Vorlage …", done: "Projekt berechnet" },
  change_project: { running: "Berechne die Änderung …", done: "Änderung berechnet" },
  undo_last_change: { running: "Nehme die Änderung zurück …", done: "Änderung zurückgenommen" },
  add_explanation: { running: "Speichere die Erläuterung …", done: "Erläuterung gespeichert" },
};

const DESIGN_TOOLS = new Set(["design_project", "redesign_project"]);

type PartialDesign = {
  design?: { parts?: ({ name?: string } | undefined)[]; steps?: unknown[] };
};

/** Part names and step count of a design that is still being written by the model. */
export function designProgress(input: unknown): { parts: string[]; steps: number } {
  const design = (input as PartialDesign | undefined)?.design;
  const parts = (design?.parts ?? [])
    .map((part) => part?.name)
    .filter((name): name is string => typeof name === "string" && name.length > 0);
  return { parts, steps: design?.steps?.length ?? 0 };
}

function count(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

function designStep(part: ToolPart): ActivityStep {
  const { parts, steps } = designProgress(part.input);
  const sofar = [
    parts.length ? count(parts.length, "Bauteil", "Bauteile") : "",
    steps ? count(steps, "Bauschritt", "Bauschritte") : "",
  ]
    .filter(Boolean)
    .join(" · ");
  if (part.state === "input-streaming") {
    return {
      key: part.key,
      label: "Entwerfe die Konstruktion …",
      detail: sofar || "Die KI schreibt den Entwurf",
      state: "running",
    };
  }
  if (part.state === "input-available") {
    return {
      key: part.key,
      label: "Engine prüft und berechnet den Entwurf …",
      detail: "Maße, Kollisionen, Stückliste, Zuschnitt, Zeichnungen",
      state: "running",
    };
  }
  if (part.state === "output-error") {
    return {
      key: part.key,
      label: "Entwurf fehlgeschlagen",
      detail: part.errorText,
      state: "error",
    };
  }
  const errors = part.output?.errors ?? [];
  if (part.output?.error) {
    return {
      key: part.key,
      label: "Engine hat den Entwurf zurückgewiesen – die KI korrigiert ihn",
      detail: errors.length ? count(errors.length, "Punkt", "Punkte") : part.output.error,
      state: "warning",
    };
  }
  return {
    key: part.key,
    label: "Konstruktion berechnet",
    detail: sofar ? `${sofar} · Stückliste, Zuschnitt und Zeichnungen fertig` : undefined,
    state: "done",
  };
}

function toolStep(part: ToolPart): ActivityStep {
  if (DESIGN_TOOLS.has(part.name)) return designStep(part);
  const labels = TOOL_LABELS[part.name] ?? { running: "Arbeite …", done: "Erledigt" };
  if (part.state === "output-error") {
    return { key: part.key, label: labels.done, detail: part.errorText, state: "error" };
  }
  if (part.state !== "output-available") {
    return { key: part.key, label: labels.running, state: "running" };
  }
  if (part.output?.error) {
    return { key: part.key, label: labels.done, detail: part.output.error, state: "warning" };
  }
  return { key: part.key, label: labels.done, state: "done" };
}

export type MessageBlock =
  | { kind: "text"; key: string; text: string }
  | { kind: "activity"; key: string; steps: ActivityStep[]; reasoning: string };

/** Message parts in order: text paragraphs and groups of tool/reasoning activity. */
export function messageBlocks(message: UIMessage, live: boolean): MessageBlock[] {
  const blocks: MessageBlock[] = [];
  const activity = (): Extract<MessageBlock, { kind: "activity" }> => {
    const last = blocks.at(-1);
    if (last?.kind === "activity") return last;
    const block = {
      kind: "activity" as const,
      key: `a${blocks.length}`,
      steps: [] as ActivityStep[],
      reasoning: "",
    };
    blocks.push(block);
    return block;
  };
  message.parts.forEach((part, index) => {
    if (part.type === "text") {
      if (!part.text.trim()) return;
      const last = blocks.at(-1);
      if (last?.kind === "text") last.text += part.text;
      else blocks.push({ kind: "text", key: `t${index}`, text: part.text });
      return;
    }
    if (part.type === "reasoning") {
      const block = activity();
      block.reasoning += part.text;
      const thinking = live && part.state === "streaming";
      block.steps.push({
        key: String(index),
        label: thinking ? "Denke nach …" : "Nachgedacht",
        state: thinking ? "running" : "done",
      });
      return;
    }
    const tool = asToolPart(part, String(index));
    if (tool) activity().steps.push(toolStep(tool));
  });
  return blocks;
}

export type Stage = { label: string; state: "pending" | "running" | "done" };

/** Coarse progress of a planning turn for the progress panel. */
export function planningStages(message: UIMessage | null): Stage[] {
  const tools = (message?.parts ?? [])
    .map((part, index) => asToolPart(part, String(index)))
    .filter((part): part is ToolPart => part !== null);
  const builders = tools.filter(
    (t) =>
      DESIGN_TOOLS.has(t.name) || t.name === "create_project" || t.name === "create_from_template",
  );
  const last = builders.at(-1);
  const understood = Boolean(message?.parts.length);
  const drafting = last !== undefined;
  const computing = last !== undefined && last.state !== "input-streaming";
  const finished = last?.state === "output-available" && !last.output?.error;
  const stage = (done: boolean, running: boolean): Stage["state"] =>
    done ? "done" : running ? "running" : "pending";
  return [
    { label: "Angaben verstehen", state: stage(understood, !understood) },
    { label: "Konstruktion wählen und entwerfen", state: stage(computing, understood) },
    { label: "Prüfen und berechnen", state: stage(finished, drafting && computing) },
    { label: "Zeichnungen, Stückliste und Anleitung", state: stage(finished, false) },
  ];
}
