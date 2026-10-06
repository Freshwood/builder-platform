import type { Money } from "@homeworking/api-client";

/** Retailer searches that open real product pages with current prices (no affiliation). */
export const SHOPS: { name: string; url: (query: string) => string }[] = [
  { name: "Hornbach", url: (q) => `https://www.hornbach.de/s/${encodeURIComponent(q)}` },
  { name: "OBI", url: (q) => `https://www.obi.de/search/${encodeURIComponent(q)}/` },
  {
    name: "Google Shopping",
    url: (q) => `https://www.google.com/search?tbm=shop&q=${encodeURIComponent(q)}`,
  },
];

const eur0 = new Intl.NumberFormat("de-DE", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});
const eur2 = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });

export function isExact(value: Money): boolean {
  return Number(value.min) === Number(value.max);
}

/** Typical value of a guide price range (its middle), or the exact value. */
export function typical(value: Money): number {
  return (Number(value.min) + Number(value.max)) / 2;
}

/** "ca. 63 €" for ranges, "39,90 €" for exact prices. */
export function formatCost(value: Money, { cents = false } = {}): string {
  const format = cents ? eur2 : eur0;
  return isExact(value) ? eur2.format(Number(value.min)) : `ca. ${format.format(typical(value))}`;
}

export function formatRange(value: Money, { cents = false } = {}): string {
  const format = cents ? eur2 : eur0;
  return `${format.format(Number(value.min))} – ${format.format(Number(value.max))}`;
}

/** Parse a German price input ("39,90", "39.90 €") into a decimal string, or null. */
export function parsePrice(input: string): string | null {
  const cleaned = input
    .replace(/[€\s]/g, "")
    .replace(/\.(?=\d{3}(\D|$))/g, "")
    .replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  return Number(cleaned).toFixed(2);
}
