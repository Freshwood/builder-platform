import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function send(page: Page, text: string) {
  await page.getByLabel("Was möchtest du bauen oder reparieren?").fill(text);
  await page.getByRole("button", { name: /^(Planung starten|Senden)$/ }).click();
}

test("chat and versions survive a reload; an old version can be viewed and restored", async ({
  page,
}) => {
  await page.goto("/");
  await send(page, "Regal 80 x 30 x 180 cm mit 5 Böden");
  const summary = page.getByTestId("project-summary");
  await expect(summary).toHaveText("Standregal mit 5 Böden – 800 × 300 × 1800 mm");
  await send(page, "Bitte 20 cm breiter");
  await expect(summary).toHaveText("Standregal mit 5 Böden – 1000 × 300 × 1800 mm");

  // The conversation is stored with the project
  await page.reload();
  const messages = page.getByTestId("messages");
  await expect(messages).toContainText("Regal 80 x 30 x 180 cm mit 5 Böden");
  await expect(messages).toContainText("Bitte 20 cm breiter");

  await page.getByRole("button", { name: "Verlauf" }).click();
  const history = page.getByTestId("version-history");
  await expect(history).toContainText("Geändert: Breite (mm) 800 → 1000");
  await expect(history).toContainText("aktuell");
  const accessibility = await new AxeBuilder({ page })
    .include('[data-testid="version-history"]')
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(accessibility.violations.filter((v) => v.impact === "serious")).toEqual([]);

  // Viewing V1 is read-only
  await history.getByRole("button", { name: /^V1 / }).click();
  await expect(page.getByTestId("version-banner")).toContainText("Version 1");
  await expect(summary).toHaveText("Standregal mit 5 Böden – 800 × 300 × 1800 mm");
  await expect(page.getByRole("tab", { name: "Anpassen" })).toHaveCount(0);

  await page.getByRole("button", { name: "Diese Version wiederherstellen" }).click();
  await expect(page.getByTestId("version-banner")).toHaveCount(0);
  await expect(summary).toHaveText("Standregal mit 5 Böden – 800 × 300 × 1800 mm");
  await expect(history).toContainText("Version 1 wiederhergestellt");
  // Nothing was lost: the 1000 mm version is still in the history
  await expect(history).toContainText("Geändert: Breite (mm) 800 → 1000");
});
