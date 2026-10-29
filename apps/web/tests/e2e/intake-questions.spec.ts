import { expect, test } from "@playwright/test";

test("the brief asks for missing size and material, and answers go into the request", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("Was möchtest du bauen oder reparieren?").fill("Ein Regal für Bücher");
  await page.getByRole("button", { name: "Planung starten" }).click();

  const questions = page.getByTestId("intake-questions");
  await expect(questions).toBeVisible();
  await expect(questions).toContainText("Welche Maße soll es haben");
  // Nothing was sent yet: the customer answers first.
  await expect(page.getByTestId("messages")).toHaveCount(0);

  await questions.getByLabel("Breite").fill("80");
  await questions.getByLabel("Tiefe").fill("30");
  await questions.getByLabel("Höhe").fill("180");
  await questions.getByRole("button", { name: "Innen" }).click();
  await questions.getByRole("button", { name: "Weiter", exact: true }).click();

  const messages = page.getByTestId("messages");
  await expect(messages).toContainText("Maße: 80 × 30 cm (Breite × Tiefe), Höhe 180 cm");
  await expect(messages).toContainText("Einsatzort: innen");
  await expect(page.getByTestId("project-summary")).toContainText("800 × 300 × 1800 mm");
});

test("a text that states everything starts without questions", async ({ page }) => {
  await page.goto("/");
  await page
    .getByLabel("Was möchtest du bauen oder reparieren?")
    .fill("Regal 80 x 30 x 180 cm, drinnen, freistehend, aus Fichte");
  await page.getByRole("button", { name: "Planung starten" }).click();
  await expect(page.getByTestId("messages")).toBeVisible();
  await expect(page.getByTestId("intake-questions")).toHaveCount(0);
});
