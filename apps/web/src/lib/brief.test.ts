import { describe, expect, it } from "vitest";

import { EMPTY_BRIEF, briefFacts, briefMessage, sizeText, type Brief } from "./brief";

const brief = (changes: Partial<Brief>): Brief => ({ ...EMPTY_BRIEF, ...changes });

describe("sizeText", () => {
  it("phrases width, depth and height for the planner, with the way the sizes are meant", () => {
    expect(sizeText(brief({ width: "80", depth: "30", height: "180" }))).toBe(
      "80 × 30 cm (Breite × Tiefe), Höhe 180 cm – ungefähr",
    );
    expect(sizeText(brief({ width: "100", height: "120", sizeMode: "exact" }))).toBe(
      "Breite 100 cm, Höhe 120 cm – genau",
    );
    expect(sizeText(brief({ depth: "40", sizeMode: "max" }))).toBe(
      "Tiefe 40 cm – höchstens (muss in den Platz passen)",
    );
  });

  it("writes decimals the German way and accepts a dot as input", () => {
    expect(sizeText(brief({ width: "1.5", depth: "0,8" }))).toBe(
      "1,5 × 0,8 cm (Breite × Tiefe) – ungefähr",
    );
  });

  it("ignores values that are not plain numbers", () => {
    expect(sizeText(brief({ width: "abc", depth: "-3", height: "1,2,3" }))).toBeUndefined();
    expect(sizeText(brief({ width: "  ", height: "" }))).toBeUndefined();
    expect(sizeText(brief({ width: "80 cm", height: "90" }))).toBe("Höhe 90 cm – ungefähr");
  });

  it("leaves the mode out when it is unknown", () => {
    expect(sizeText(brief({ width: "50", sizeMode: "whatever" }))).toBe("Breite 50 cm");
  });
});

describe("briefFacts", () => {
  it("is empty for an empty brief", () => {
    expect(briefFacts(brief({ description: "Ein Regal" }))).toEqual([]);
  });

  it("lists the given facts in a fixed order", () => {
    const facts = briefFacts(
      brief({
        usage: "  Bücher  ",
        finish: "oil",
        location: "covered",
        wood: "larch",
        budget: "250",
        experience: "beginner",
        tools: ["driver", "jigsaw"],
        mounting: "wall",
      }),
    );
    expect(facts.map(([label]) => label)).toEqual([
      "Einsatzort",
      "Montage",
      "Material",
      "Oberfläche",
      "Budget",
      "Erfahrung",
      "Vorhandenes Werkzeug",
      "Nutzung und Wünsche",
    ]);
    expect(Object.fromEntries(facts)).toMatchObject({
      Einsatzort: "draußen, überdacht",
      Montage: "an der Wand montiert",
      Material: "Lärche",
      Oberfläche: "geölt",
      Budget: "bis 250 € Material",
      "Vorhandenes Werkzeug": "Akkuschrauber, Stichsäge",
      "Nutzung und Wünsche": "Bücher",
    });
  });

  it("drops unknown option values, bad budgets and unknown tools instead of printing them", () => {
    const facts = briefFacts(
      brief({ location: "moon", budget: "viel", tools: ["laser"], wood: "unobtainium" }),
    );
    expect(facts).toEqual([]);
  });
});

describe("briefMessage", () => {
  it("sends just the description when nothing else is filled in", () => {
    expect(briefMessage(brief({ description: "  Ein Regal für Bücher \n" }))).toBe(
      "Ein Regal für Bücher",
    );
  });

  it("appends one line per fact below the description", () => {
    const message = briefMessage(
      brief({
        description: "Bücherregal",
        location: "indoor",
        width: "80",
        depth: "30",
        height: "180",
      }),
    );
    expect(message).toBe(
      [
        "Bücherregal",
        "",
        "Angaben:",
        "- Einsatzort: innen",
        "- Maße: 80 × 30 cm (Breite × Tiefe), Höhe 180 cm – ungefähr",
      ].join("\n"),
    );
  });
});
