import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function expectNoSeriousA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const serious = results.violations.filter((v) =>
    ["serious", "critical"].includes(v.impact ?? ""),
  );
  expect(
    serious.map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join(", ")})`),
  ).toEqual([]);
}

async function send(page: Page, text: string) {
  await page.getByLabel("Was möchtest du bauen oder reparieren?").fill(text);
  // The first request goes through the project brief, follow-ups through the chat.
  await page.getByRole("button", { name: /^(Planung starten|Senden)$/ }).click();
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
  await expect
    .poll(() => plan.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBeGreaterThan(0);

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

test("plan a shelf from a template with 3D model and cutting plan", async ({ page }) => {
  await page.goto("/");
  await send(page, "Regal 80 x 30 x 180 cm mit 5 Böden");
  const summary = page.getByTestId("project-summary");
  await expect(summary).toHaveText("Standregal mit 5 Böden – 800 × 300 × 1800 mm");
  await expect(page.getByTestId("trust-badge")).toHaveText("Vorlage");
  await expect(page.getByTestId("viewer-3d")).toBeVisible();
  await expect(page.getByRole("list", { name: "Positionen" })).toContainText("Fachboden");

  const iso = page.getByTestId("drawing-iso");
  await expect(iso).toHaveAttribute("alt", /Isometrie.*800 × 300 × 1800 mm/);
  await expect
    .poll(() => iso.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBeGreaterThan(0);

  await send(page, "Bitte 20 cm breiter");
  await expect(summary).toHaveText("Standregal mit 5 Böden – 1000 × 300 × 1800 mm");

  await page.getByRole("tab", { name: "Zuschnitt" }).click();
  await expect(page.getByRole("tabpanel")).toContainText("Einkauf und Schnittplan");
  // Parameters apply directly on Enter, no extra confirm button.
  await page.getByRole("tab", { name: "Anpassen" }).click();
  await page.getByLabel("Anzahl Böden").fill("6");
  await page.getByLabel("Anzahl Böden").press("Enter");
  await expect(summary).toHaveText("Standregal mit 6 Böden – 1000 × 300 × 1800 mm");

  await expectNoSeriousA11yViolations(page);
});

test("project brief collects details and sends them with the request", async ({ page }) => {
  await page.goto("/");
  const brief = page.getByTestId("project-brief");
  await page.getByRole("button", { name: /^Bücherregal/ }).click();
  await expect(page.getByLabel("Was möchtest du bauen oder reparieren?")).toHaveValue(
    /Bücherregal mit 5 Böden/,
  );
  // Details are pills that open a small panel (progressive disclosure).
  await brief.getByRole("button", { name: /^Oberfläche/ }).click();
  const finish = brief.getByRole("region", { name: "Oberfläche" });
  await finish.getByRole("button", { name: "Geölt" }).click();
  await expect(finish.getByRole("button", { name: "Geölt" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const details = brief.getByRole("list", { name: "Details (optional)" });
  await expect(details).toContainText("Geölt");
  await expect(details).toContainText("80 × 30 cm");
  await expectNoSeriousA11yViolations(page);
  await page.screenshot({ path: "test-results/brief.png", fullPage: true });

  await brief.getByRole("button", { name: "Planung starten" }).click();
  const messages = page.getByTestId("messages");
  await expect(messages).toContainText("Maße: 80 × 30 cm (Breite × Tiefe), Höhe 180 cm");
  await expect(messages).toContainText("Oberfläche: geölt");
  await expect(page.getByTestId("project-summary")).toHaveText(
    "Standregal mit 5 Böden – 800 × 300 × 1800 mm",
  );
  await expect(page.getByRole("list", { name: "Arbeitsschritte des Assistenten" })).toContainText(
    "Projekt berechnet",
  );
  await expect(page.getByLabel("Was möchtest du bauen oder reparieren?")).toBeVisible();
  await page.screenshot({ path: "test-results/after.png", fullPage: true });
});

test("clicking 'PDF herunterladen' downloads the complete PDF", async ({ page }) => {
  await page.goto("/");
  await send(page, "Regal 80 x 30 x 180 cm mit 5 Böden");
  await expect(page.getByTestId("project-summary")).toHaveText(
    "Standregal mit 5 Böden – 800 × 300 × 1800 mm",
  );
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "PDF herunterladen" }).click();
  const download = await downloadPromise;
  expect(await download.failure()).toBeNull();
  expect(download.suggestedFilename()).toMatch(/\.pdf$/);
  const path = await download.path();
  const { readFile } = await import("node:fs/promises");
  const bytes = await readFile(path);
  expect(bytes.subarray(0, 5).toString()).toBe("%PDF-");
  expect(bytes.length).toBeGreaterThan(20_000);
});

test("a failing PDF request shows an error instead of saving document.txt", async ({ page }) => {
  await page.goto("/");
  await send(page, "Regal 80 x 30 x 180 cm mit 5 Böden");
  await expect(page.getByTestId("project-summary")).toContainText("Standregal");
  // What the Next.js proxy answers when the API times out or is restarting.
  await page.route("**/document.pdf*", (route) =>
    route.fulfill({ status: 500, body: "Internal Server Error" }),
  );
  let downloaded = false;
  page.on("download", () => {
    downloaded = true;
  });
  await page.getByRole("link", { name: "PDF herunterladen" }).click();
  await expect(page.locator("#pdf-error")).toContainText("PDF konnte nicht erstellt werden");
  expect(downloaded).toBe(false);

  await page.unroute("**/document.pdf*");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "PDF herunterladen" }).click();
  expect((await downloadPromise).suggestedFilename()).toMatch(/^homeworking-.*\.pdf$/);
  await expect(page.locator("#pdf-error")).toHaveCount(0);
});

test("material list explains prices and accepts the user's real prices", async ({ page }) => {
  await page.goto("/");
  await send(page, "Regal 80 x 30 x 180 cm mit 5 Böden");
  await expect(page.getByTestId("project-summary")).toContainText("Standregal");
  await page.getByRole("tab", { name: "Material" }).click();
  await expect(page.getByText("Woher kommen die Preise?")).toBeVisible();
  await expect(page.getByTestId("price-status")).toHaveText(
    "Noch keine eigenen Preise eingetragen.",
  );
  const hornbach = page.getByRole("link", { name: /^Hornbach/ }).first();
  await expect(hornbach).toHaveAttribute("href", /^https:\/\/www\.hornbach\.de\/s\/Leimholzplatte/);
  const totalBefore = await page.getByTestId("bom-total").textContent();

  const input = page.getByLabel("Dein Preis je Platte für Leimholzplatte Fichte");
  await input.fill("39,90");
  await input.press("Enter");
  await expect(page.getByTestId("price-status")).toHaveText(
    /^1 von \d+ Positionen mit deinem Preis\.$/,
  );
  await expect(page.getByTestId("bom")).toContainText("dein Preis");
  await expect(page.getByTestId("bom-total")).not.toHaveText(totalBefore ?? "");
  await expect(page.getByTestId("material-cost")).toBeVisible();
  await expectNoSeriousA11yViolations(page);
  await page.getByTestId("bom").screenshot({ path: "test-results/bom.png" });
  await page.getByRole("list", { name: "Eckdaten" }).screenshot({ path: "test-results/kpi.png" });

  await page.getByRole("button", { name: "Rückgängig" }).click();
  await expect(page.getByTestId("price-status")).toHaveText(
    "Noch keine eigenen Preise eingetragen.",
  );
});
