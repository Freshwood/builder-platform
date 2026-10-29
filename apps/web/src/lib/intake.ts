/** Intake step: the brief goes to the engine's gap rules before the planning starts (ADR-0010). */

import { intake, type IntakeResponse, type Question, type Spec } from "@/api";

import type { Brief } from "@/lib/brief";

const mm = (cm: string): number | undefined => {
  const value = Number(cm.trim().replace(",", "."));
  return Number.isFinite(value) && value > 0 ? Math.round(value * 10) : undefined;
};

const cm = (millimetres: number | null | undefined): string =>
  millimetres ? String(millimetres / 10).replace(".", ",") : "";

/** The facts of the brief form as the structured brief (``Spec``) the engine reasons about. */
export function briefToSpec(brief: Brief): Spec {
  const use = brief.location === "indoor" ? "indoor" : brief.location ? "outdoor" : undefined;
  const support = brief.mounting === "floor" || brief.mounting === "wall" ? brief.mounting : undefined;
  const budget = Number(brief.budget.trim().replace(",", "."));
  return {
    description: brief.description.trim(),
    use,
    support,
    width_mm: mm(brief.width),
    depth_mm: mm(brief.depth),
    height_mm: mm(brief.height),
    size_mode: brief.sizeMode as Spec["size_mode"],
    wood: brief.wood || undefined,
    finish: brief.finish || undefined,
    experience: (brief.experience || undefined) as Spec["experience"],
    budget_eur: Number.isFinite(budget) && budget > 0 ? budget : undefined,
    tools: brief.tools,
    usage: brief.usage.trim() || undefined,
  };
}

/** Fill the brief fields the customer left empty with what the intake read from the text. */
export function applySpec(brief: Brief, spec: Spec): Brief {
  const location = spec.use ?? "";
  return {
    ...brief,
    location: brief.location || location,
    mounting: brief.mounting || spec.support || "",
    width: brief.width || cm(spec.width_mm),
    depth: brief.depth || cm(spec.depth_mm),
    height: brief.height || cm(spec.height_mm),
    sizeMode: brief.sizeMode === "approx" && spec.size_mode ? spec.size_mode : brief.sizeMode,
    wood: brief.wood || spec.wood || "",
    finish: brief.finish || spec.finish || "",
    experience: brief.experience || spec.experience || "",
    usage: brief.usage || spec.usage || "",
  };
}

/** The Brief field(s) a question's answer is stored in. */
export const ANSWER_FIELD: Record<string, keyof Brief | undefined> = {
  use: "location",
  support: "mounting",
  wood: "wood",
  finish: "finish",
  experience: "experience",
};

export type Intake = { brief: Brief; questions: Question[] };

/**
 * Ask the engine which questions are still open. Never blocks the planning: if the request fails
 * (offline, safety gate) the brief goes on as typed and the chat handles the rest.
 */
export async function askIntake(brief: Brief, extract = true): Promise<Intake> {
  try {
    const { data } = await intake({
      body: { spec: briefToSpec(brief), extract },
      throwOnError: true,
    });
    const response: IntakeResponse = data;
    return { brief: applySpec(brief, response.spec), questions: response.questions };
  } catch {
    return { brief, questions: [] };
  }
}
