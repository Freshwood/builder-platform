import { expect, test, type Page } from "@playwright/test";

const PROMPT = "Was möchtest du bauen oder reparieren?";

// Two animation frames: React has committed whatever the last network answer scheduled.
const settle = (page: Page) =>
  page.evaluate(
    () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
  );

test("edits made while the engine reads the brief are kept; the outdated answer is dropped", async ({
  page,
}) => {
  // Hold the intake answer back until the test lets it go.
  let release!: () => void;
  const gate = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/pipeline/intake", async (route) => {
    await gate;
    await route.continue();
  });

  await page.goto("/");
  const field = page.getByLabel(PROMPT);
  const start = page.getByRole("button", { name: "Planung starten" });
  await field.fill("Ein Regal für Bücher");
  await start.click();
  await expect(start).toBeDisabled();

  // The customer keeps typing while the check is still running: the check is obsolete.
  await field.fill("Ein Regal für Bücher aus Kiefer");
  await expect(start).toBeEnabled();

  const answered = page.waitForResponse("**/api/pipeline/intake");
  release();
  await answered;
  await settle(page);

  // Neither were the questions of the old text shown, nor was the old text sent or restored.
  await expect(page.getByTestId("intake-questions")).toHaveCount(0);
  await expect(page.getByTestId("messages")).toHaveCount(0);
  await expect(field).toHaveValue("Ein Regal für Bücher aus Kiefer");

  // The form stays usable: a new check runs for the current text.
  await start.click();
  await expect(page.getByTestId("intake-questions")).toBeVisible();
  await expect(field).toHaveValue("Ein Regal für Bücher aus Kiefer");
});
