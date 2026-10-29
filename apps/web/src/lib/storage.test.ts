import { describe, expect, it } from "vitest";

import { parseStoredSet } from "./storage";

describe("parseStoredSet", () => {
  it("restores the saved numbers", () => {
    expect(parseStoredSet("[1,3,2,3]")).toEqual(new Set([1, 2, 3]));
  });

  it("starts empty when nothing is saved", () => {
    expect(parseStoredSet(null)).toEqual(new Set());
    expect(parseStoredSet("")).toEqual(new Set());
  });

  it("survives corrupt or foreign data instead of breaking the build steps", () => {
    expect(parseStoredSet("{oops")).toEqual(new Set());
    expect(parseStoredSet('{"a":1}')).toEqual(new Set());
    expect(parseStoredSet('"text"')).toEqual(new Set());
    expect(parseStoredSet('[1,"2",null,2.5,{"x":1},4]')).toEqual(new Set([1, 4]));
  });
});
