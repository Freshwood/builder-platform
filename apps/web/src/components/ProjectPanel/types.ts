import type { ProjectModel } from "@/api";

/** The derived state of a project: everything the engine computed. */
export type Result = ProjectModel["result"];

export type TabKey = "adjust" | "bom" | "cuts" | "steps" | "notes";
