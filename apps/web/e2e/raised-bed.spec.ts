import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function expectNoSeriousA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const serious = results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
  expect(serious.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
}

async function send(page: Page, text: string) {
  await page.getByLabel("Was möchtest du bauen oder reparieren?").fill(text);
  await page.getByRole("button", { name: "Senden" }).click();
}

test("plan a raised bed, change it via chat and undo", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Was möchtest du bauen oder reparieren?" }),
  ).toBeVisible();
  await expect(page.getByTestId("ai-disclosure")).toContainText("KI-Assistent");
  await expectNoSeriousA11yViolations(page);

  await send(page, "Ich möchte ein Hochbeet 2 × 1 m, 80 cm hoch, aus Lärche bauen.");
  const summary = page.getByTestId("project-summary");
  await expect(summary).toHaveText("Hochbeet Lärche 2,00 m × 1,00 m, Höhe 0,87 m");
  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]{36}$/);
  const costBefore = await page.getByTestId("material-cost").textContent();

  const plan = page.getByTestId("drawing-plan");
  await expect(plan).toHaveAttribute("alt", /Draufsicht des Hochbeets, außen 2000 × 1000 mm/);
  await expect.poll(() => plan.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);

  await send(page, "Mach es 50 cm breiter");
  await expect(summary).toHaveText("Hochbeet Lärche 2,00 m × 1,50 m, Höhe 0,87 m");
  await expect(page.getByTestId("material-cost")).not.toHaveText(costBefore ?? "");
  await expect(plan).toHaveAttribute("alt", /außen 2000 × 1500 mm/);
  await expect(page.getByTestId("bom")).toContainText("Hochbeeterde");

  await page.getByRole("button", { name: "Rückgängig" }).click();
  await expect(summary).toHaveText("Hochbeet Lärche 2,00 m × 1,00 m, Höhe 0,87 m");

  await page.getByRole("button", { name: "Variante Komfort wählen" }).click();
  await expect(summary).toHaveText("Hochbeet Douglasie 2,00 m × 1,00 m, Höhe 0,90 m");

  await expectNoSeriousA11yViolations(page);

  const pdfUrl = await page.getByRole("link", { name: "PDF herunterladen" }).getAttribute("href");
  const pdf = await page.request.get(pdfUrl!);
  expect(pdf.headers()["content-type"]).toBe("application/pdf");
  expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");

  await page.goto("/projects");
  await expect(page.getByRole("link", { name: /Hochbeet/ }).first()).toBeVisible();
});

test("safety gate refers electrical work to professionals", async ({ page }) => {
  await page.goto("/");
  await send(page, "Wie verlege ich eine Steckdose mit 230 V am Hochbeet?");
  await expect(page.getByTestId("messages")).toContainText("Elektrofachkräfte");
  await expect(page.getByTestId("project-panel")).toHaveCount(0);
});
