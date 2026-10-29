import { describe, expect, it } from "vitest";

import { SHOPS, formatCost, formatEur, formatRange, isExact, parsePrice, typical } from "./prices";

// Intl puts a no-break space before the currency sign; compare with a plain one.
const plain = (text: string) => text.replace(/[  ]/g, " ");

const range = (min: string, max: string) => ({ min, max });

describe("parsePrice", () => {
  it.each([
    ["39,90", "39.90"],
    ["39.90", "39.90"],
    ["39,90 €", "39.90"],
    ["€ 39,9", "39.90"],
    ["12", "12.00"],
    ["0,5", "0.50"],
    ["  7,00  ", "7.00"],
  ])("reads %j as %j", (input, expected) => {
    expect(parsePrice(input)).toBe(expected);
  });

  it("treats a dot before exactly three digits as a thousands separator", () => {
    expect(parsePrice("1.234")).toBe("1234.00");
    expect(parsePrice("1.234,50")).toBe("1234.50");
    expect(parsePrice("12.345.678,9")).toBe("12345678.90");
  });

  it.each(["", "   ", "abc", "-5", "1,234", "12,345.67", "1,2,3", "3 €uro", "NaN"])(
    "rejects %j",
    (input) => {
      expect(parsePrice(input)).toBeNull();
    },
  );
});

describe("formatEur", () => {
  it("formats whole euros in German notation from numbers and API decimal strings", () => {
    expect(plain(formatEur(63))).toBe("63 €");
    expect(plain(formatEur("62.5"))).toBe("63 €");
    expect(plain(formatEur("1234.4"))).toBe("1.234 €");
    expect(plain(formatEur(0))).toBe("0 €");
  });

  it("rounds instead of showing cents", () => {
    expect(plain(formatEur("39.90"))).toBe("40 €");
  });
});

describe("price ranges", () => {
  it("tells exact prices from ranges", () => {
    expect(isExact(range("39.90", "39.90"))).toBe(true);
    expect(isExact(range("39.9", "39.90"))).toBe(true);
    expect(isExact(range("30", "40"))).toBe(false);
  });

  it("uses the middle of a range as the typical value", () => {
    expect(typical(range("30", "40"))).toBe(35);
    expect(typical(range("12.50", "12.50"))).toBe(12.5);
  });

  it("shows exact prices with cents and ranges as a rounded guide value", () => {
    expect(plain(formatCost(range("39.90", "39.90")))).toBe("39,90 €");
    expect(plain(formatCost(range("30", "40")))).toBe("ca. 35 €");
    expect(plain(formatCost(range("30.20", "40.40"), { cents: true }))).toBe("ca. 35,30 €");
  });

  it("formats both ends of a range", () => {
    expect(plain(formatRange(range("30", "40.60")))).toBe("30 € – 41 €");
    expect(plain(formatRange(range("30", "40.60"), { cents: true }))).toBe("30,00 € – 40,60 €");
  });
});

describe("SHOPS", () => {
  it("encode the search text into real retailer URLs", () => {
    const query = "Leimholzplatte Fichte 18 mm & Kante/Rand";
    const urls = Object.fromEntries(SHOPS.map((shop) => [shop.name, shop.url(query)]));
    const encoded = encodeURIComponent(query);
    expect(urls["Hornbach"]).toBe(`https://www.hornbach.de/s/${encoded}`);
    expect(urls["OBI"]).toBe(`https://www.obi.de/search/${encoded}/`);
    expect(urls["Google Shopping"]).toBe(`https://www.google.com/search?tbm=shop&q=${encoded}`);
    for (const url of Object.values(urls)) expect(url).not.toMatch(/ |&(?!tbm|q=)/);
  });
});
