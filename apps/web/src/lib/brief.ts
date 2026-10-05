/** Project brief: structured customer input that becomes the first chat message. */

export type Option = { value: string; label: string; text: string };

export const LOCATIONS: Option[] = [
  { value: "indoor", label: "Innen", text: "innen" },
  { value: "covered", label: "Außen, überdacht", text: "draußen, überdacht" },
  { value: "outdoor", label: "Außen, Wetter", text: "draußen, Regen und Sonne ausgesetzt" },
];

export const MOUNTINGS: Option[] = [
  { value: "floor", label: "Freistehend", text: "freistehend auf dem Boden" },
  { value: "wall", label: "An der Wand", text: "an der Wand montiert" },
  { value: "hanging", label: "Hängend", text: "hängend (z. B. an der Decke oder am Geländer)" },
];

export const SIZE_MODES: Option[] = [
  { value: "exact", label: "genau", text: "genau" },
  { value: "approx", label: "ungefähr", text: "ungefähr" },
  { value: "max", label: "höchstens", text: "höchstens (muss in den Platz passen)" },
];

export const WOODS: Option[] = [
  { value: "spruce", label: "Fichte", text: "Fichte" },
  { value: "pine", label: "Kiefer", text: "Kiefer" },
  { value: "douglas", label: "Douglasie", text: "Douglasie" },
  { value: "larch", label: "Lärche", text: "Lärche" },
  { value: "oak", label: "Eiche", text: "Eiche" },
  { value: "beech", label: "Buche", text: "Buche" },
  { value: "robinia", label: "Robinie", text: "Robinie" },
  {
    value: "panel",
    label: "Platten (Multiplex, Leimholz)",
    text: "Plattenwerkstoff (Multiplex/Leimholz)",
  },
];

export const FINISHES: Option[] = [
  { value: "natural", label: "Unbehandelt", text: "unbehandelt" },
  { value: "oil", label: "Geölt", text: "geölt" },
  { value: "glaze", label: "Lasiert", text: "lasiert" },
  { value: "paint", label: "Lackiert / deckend", text: "deckend lackiert" },
];

export const EXPERIENCE: Option[] = [
  { value: "beginner", label: "Einsteiger", text: "Einsteiger (einfache Verbindungen bevorzugt)" },
  { value: "advanced", label: "Geübt", text: "geübt" },
  { value: "pro", label: "Profi", text: "sehr erfahren" },
];

export const TOOLS: Option[] = [
  { value: "driver", label: "Akkuschrauber", text: "Akkuschrauber" },
  { value: "jigsaw", label: "Stichsäge", text: "Stichsäge" },
  { value: "circular", label: "Handkreissäge", text: "Handkreissäge" },
  { value: "mitre", label: "Kapp-/Gehrungssäge", text: "Kapp-/Gehrungssäge" },
  { value: "table", label: "Tischkreissäge", text: "Tischkreissäge" },
  { value: "sander", label: "Schleifmaschine", text: "Schleifmaschine" },
  { value: "router", label: "Oberfräse", text: "Oberfräse" },
];

export type Brief = {
  description: string;
  location: string;
  mounting: string;
  width: string;
  depth: string;
  height: string;
  sizeMode: string;
  wood: string;
  finish: string;
  budget: string;
  experience: string;
  tools: string[];
  usage: string;
};

export const EMPTY_BRIEF: Brief = {
  description: "",
  location: "",
  mounting: "",
  width: "",
  depth: "",
  height: "",
  sizeMode: "approx",
  wood: "",
  finish: "",
  budget: "",
  experience: "",
  tools: [],
  usage: "",
};

function text(options: Option[], value: string): string | undefined {
  return options.find((o) => o.value === value)?.text;
}

function number(value: string): string | undefined {
  const trimmed = value.trim().replace(".", ",");
  return trimmed && /^\d+(,\d+)?$/.test(trimmed) ? trimmed : undefined;
}

/** Dimensions phrased so that both the LLM and the offline planner read them. */
export function sizeText(brief: Brief): string | undefined {
  const [w, d, h] = [number(brief.width), number(brief.depth), number(brief.height)];
  const parts: string[] = [];
  if (w && d) parts.push(`${w} × ${d} cm (Breite × Tiefe)`);
  else if (w) parts.push(`Breite ${w} cm`);
  else if (d) parts.push(`Tiefe ${d} cm`);
  if (h) parts.push(`Höhe ${h} cm`);
  if (!parts.length) return undefined;
  const mode = text(SIZE_MODES, brief.sizeMode);
  return parts.join(", ") + (mode ? ` – ${mode}` : "");
}

export function briefFacts(brief: Brief): [string, string][] {
  const facts: [string, string | undefined][] = [
    ["Einsatzort", text(LOCATIONS, brief.location)],
    ["Montage", text(MOUNTINGS, brief.mounting)],
    ["Maße", sizeText(brief)],
    ["Material", text(WOODS, brief.wood)],
    ["Oberfläche", text(FINISHES, brief.finish)],
    ["Budget", number(brief.budget) ? `bis ${number(brief.budget)} € Material` : undefined],
    ["Erfahrung", text(EXPERIENCE, brief.experience)],
    [
      "Vorhandenes Werkzeug",
      brief.tools.length
        ? brief.tools
            .map((t) => text(TOOLS, t))
            .filter(Boolean)
            .join(", ")
        : undefined,
    ],
    ["Nutzung und Wünsche", brief.usage.trim() || undefined],
  ];
  return facts.filter((f): f is [string, string] => Boolean(f[1]));
}

/** The chat message for a brief: free description first, then one line per given fact. */
export function briefMessage(brief: Brief): string {
  const facts = briefFacts(brief);
  const description = brief.description.trim();
  if (!facts.length) return description;
  const lines = facts.map(([label, value]) => `- ${label}: ${value}`);
  return `${description}\n\nAngaben:\n${lines.join("\n")}`;
}

export const BRIEF_FIELDS = 9;

export function briefCompleteness(brief: Brief): number {
  return briefFacts(brief).length;
}
