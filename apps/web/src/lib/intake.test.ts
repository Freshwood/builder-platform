import type { Spec } from "@/api";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EMPTY_BRIEF, type Brief } from "./brief";

const { intake } = vi.hoisted(() => ({ intake: vi.fn() }));
vi.mock("@/api", () => ({ intake }));

import { ANSWER_FIELD, applySpec, askIntake, briefToSpec } from "./intake";

const brief = (changes: Partial<Brief>): Brief => ({ ...EMPTY_BRIEF, ...changes });
const spec = (changes: Partial<Spec>): Spec => ({ description: "Regal", ...changes });

beforeEach(() => {
  intake.mockReset();
});

describe("briefToSpec", () => {
  it("converts centimetres from the form into millimetres", () => {
    const result = briefToSpec(brief({ width: "80", depth: "1,5", height: " 180 " }));
    expect(result).toMatchObject({ width_mm: 800, depth_mm: 15, height_mm: 1800 });
  });

  it("drops sizes that are empty, zero, negative or not numbers", () => {
    const result = briefToSpec(brief({ width: "", depth: "0", height: "abc" }));
    expect(result.width_mm).toBeUndefined();
    expect(result.depth_mm).toBeUndefined();
    expect(result.height_mm).toBeUndefined();
    expect(briefToSpec(brief({ width: "-5" })).width_mm).toBeUndefined();
  });

  it("maps the location to indoor or outdoor", () => {
    expect(briefToSpec(brief({ location: "indoor" })).use).toBe("indoor");
    expect(briefToSpec(brief({ location: "covered" })).use).toBe("outdoor");
    expect(briefToSpec(brief({ location: "outdoor" })).use).toBe("outdoor");
    expect(briefToSpec(brief({ location: "" })).use).toBeUndefined();
  });

  it("only passes mountings the engine knows", () => {
    expect(briefToSpec(brief({ mounting: "floor" })).support).toBe("floor");
    expect(briefToSpec(brief({ mounting: "wall" })).support).toBe("wall");
    expect(briefToSpec(brief({ mounting: "hanging" })).support).toBeUndefined();
  });

  it("trims text, reads the budget with a decimal comma and turns empty fields into undefined", () => {
    const result = briefToSpec(
      brief({
        description: "  Regal \n",
        budget: "99,50",
        usage: "  ",
        wood: "",
        tools: ["driver"],
      }),
    );
    expect(result).toMatchObject({ description: "Regal", budget_eur: 99.5, tools: ["driver"] });
    expect(result.usage).toBeUndefined();
    expect(result.wood).toBeUndefined();
    expect(briefToSpec(brief({ budget: "0" })).budget_eur).toBeUndefined();
  });
});

describe("applySpec", () => {
  it("fills what the customer left empty with what the engine read from the text", () => {
    const result = applySpec(
      brief({ description: "Regal 80 x 30 x 180, innen" }),
      spec({
        use: "indoor",
        support: "floor",
        width_mm: 800,
        depth_mm: 300,
        height_mm: 1525,
        wood: "spruce",
      }),
    );
    expect(result).toMatchObject({
      location: "indoor",
      mounting: "floor",
      width: "80",
      depth: "30",
      height: "152,5",
      wood: "spruce",
    });
  });

  it("never overwrites what the customer filled in", () => {
    const given = brief({ location: "outdoor", width: "100", wood: "oak", usage: "Werkzeug" });
    const result = applySpec(
      given,
      spec({ use: "indoor", width_mm: 800, wood: "spruce", usage: "Bücher" }),
    );
    expect(result).toMatchObject({
      location: "outdoor",
      width: "100",
      wood: "oak",
      usage: "Werkzeug",
    });
  });

  it("takes over the size mode only while the customer kept the default", () => {
    expect(applySpec(brief({}), spec({ size_mode: "max" })).sizeMode).toBe("max");
    expect(applySpec(brief({ sizeMode: "exact" }), spec({ size_mode: "max" })).sizeMode).toBe(
      "exact",
    );
    expect(applySpec(brief({}), spec({})).sizeMode).toBe("approx");
  });

  it("keeps the description and leaves everything empty when the engine found nothing", () => {
    const given = brief({ description: "Etwas" });
    expect(applySpec(given, spec({}))).toEqual(given);
  });
});

describe("ANSWER_FIELD", () => {
  it("points each question to the brief field its answer is stored in", () => {
    expect(ANSWER_FIELD).toMatchObject({
      use: "location",
      support: "mounting",
      wood: "wood",
      finish: "finish",
      experience: "experience",
    });
  });
});

describe("askIntake", () => {
  it("returns the brief completed from the engine's reading together with the open questions", async () => {
    const question = { field: "size", text: "Welche Maße soll es haben?" };
    intake.mockResolvedValue({
      data: { spec: spec({ use: "indoor", height_mm: 1800 }), questions: [question], ready: false },
    });
    const result = await askIntake(brief({ description: "Regal drinnen, 180 hoch" }));
    expect(result.questions).toEqual([question]);
    expect(result.brief).toMatchObject({ location: "indoor", height: "180" });
    expect(intake).toHaveBeenCalledWith({
      body: {
        spec: expect.objectContaining({ description: "Regal drinnen, 180 hoch" }),
        extract: true,
      },
      throwOnError: true,
    });
  });

  it("can skip the text extraction", async () => {
    intake.mockResolvedValue({ data: { spec: spec({}), questions: [], ready: true } });
    await askIntake(brief({ description: "Regal" }), false);
    expect(intake).toHaveBeenCalledWith(
      expect.objectContaining({ body: expect.objectContaining({ extract: false }) }),
    );
  });

  it("never blocks the planning: a failing request leaves the brief as typed", async () => {
    intake.mockRejectedValue(new Error("Failed to fetch"));
    const typed = brief({ description: "Regal", width: "80" });
    await expect(askIntake(typed)).resolves.toEqual({ brief: typed, questions: [] });
  });
});
