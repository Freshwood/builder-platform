// Material tones shared by the 3D viewer and legends; keep in sync with the SVG renderer
// (apps/api/src/homeworking/modules/drawings/svg.py).
export const TONES: Record<string, string> = {
  spruce: "#ecd3a2",
  douglas: "#dba06e",
  larch: "#e3b27a",
  pine: "#e8c48e",
  oak: "#c49a62",
  beech: "#e0b48a",
  robinia: "#c9a64f",
  plywood: "#efd9b0",
  glulam: "#f2d396",
  osb: "#d6b26f",
  mdf: "#b8a48a",
  hdf: "#d4cfc6",
  steel: "#9ca3af",
  rubber: "#4b5563",
  concrete: "#bdbab4",
};

export function toneColor(tone: string): string {
  return TONES[tone] ?? "#d1d5db";
}
