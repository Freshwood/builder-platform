import { expect, test } from "@playwright/test";

import { continueWithAssumptions } from "../support/intake";

test("a new cabinet is planned in stages and comes with build steps and an explanation", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("Was möchtest du bauen oder reparieren?")
    .fill("Ich brauche einen Schrank 80 x 40 x 100 cm, drinnen");
  await page.getByRole("button", { name: "Planung starten" }).click();
  await continueWithAssumptions(page);

  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("project-summary")).toContainText("800 × 400 × 1000 mm");
  await expect(page.getByTestId("design-badge")).toHaveText("KI-Entwurf");

  // The documentation stage worded the build step and the explanation.
  await page.getByRole("tab", { name: /Bauanleitung/ }).click();
  await expect(page.getByTestId("project-panel")).toContainText("Montiere Korpus");
  await page.getByRole("tab", { name: /Warum so\?/ }).click();
  await expect(page.getByTestId("project-panel")).toContainText("Korpus besteht aus Platten");
});
