import { describe, expect, it } from "vitest";

import { isTyping } from "./keys";

/** A stand-in for a DOM element: ``closest`` answers like the browser for one tag name. */
const element = (tag: string, contentEditable = false) => ({
  closest: (selector: string) =>
    selector.split(",").some((part) => {
      const wanted = part.trim();
      return wanted === tag || (contentEditable && wanted === "[contenteditable]");
    })
      ? {}
      : null,
});

describe("isTyping", () => {
  it("is true for fields the user types into", () => {
    expect(isTyping(element("input") as unknown as EventTarget)).toBe(true);
    expect(isTyping(element("textarea") as unknown as EventTarget)).toBe(true);
    expect(isTyping(element("select") as unknown as EventTarget)).toBe(true);
    expect(isTyping(element("div", true) as unknown as EventTarget)).toBe(true);
  });

  it("is false for other elements and for targets that are no elements", () => {
    expect(isTyping(element("button") as unknown as EventTarget)).toBe(false);
    expect(isTyping({} as EventTarget)).toBe(false);
    expect(isTyping(null)).toBe(false);
  });
});
