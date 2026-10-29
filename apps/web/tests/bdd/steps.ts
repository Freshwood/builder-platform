import { readFile } from "node:fs/promises";

import { expect } from "@playwright/test";

import { expectNoSeriousA11yViolations } from "../support/a11y";
import { continueWithAssumptions } from "../support/intake";
import { Given, Then, When } from "./fixtures";

const PROMPT = "Was möchtest du bauen oder reparieren?";

// ---------------------------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------------------------

Given("ich öffne die Startseite", async ({ page }) => {
  await page.goto("/");
});

When("ich die Projektliste öffne", async ({ page }) => {
  await page.goto("/projects");
});

When("ich die Seite neu lade", async ({ page }) => {
  await page.reload();
});

Then("sehe ich die Überschrift {string}", async ({ page }, name: string) => {
  await expect(page.getByRole("heading", { name })).toBeVisible();
});

Then("ist die Adresse eine Projektseite", async ({ page }) => {
  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]{36}$/);
});

Then("ist die Seite barrierefrei", async ({ page }) => {
  await expectNoSeriousA11yViolations(page);
});

Then("ist der Bereich {string} barrierefrei", async ({ page }, testId: string) => {
  await expectNoSeriousA11yViolations(page, `[data-testid="${testId}"]`);
});

Then("weist die Seite auf den KI-Assistenten hin", async ({ page }) => {
  await expect(page.getByTestId("ai-disclosure")).toContainText("KI-Assistent");
});

Then("sehe ich ein Projekt {string} in der Liste", async ({ page }, name: string) => {
  await expect(page.getByRole("link", { name: new RegExp(name) }).first()).toBeVisible();
});

// ---------------------------------------------------------------------------------------------
// Chat and project brief
// ---------------------------------------------------------------------------------------------

When("ich im Planer schreibe {string}", async ({ page }, text: string) => {
  await page.getByLabel(PROMPT).fill(text);
  // The first request goes through the project brief, follow-ups through the chat.
  await page.getByRole("button", { name: /^(Planung starten|Senden)$/ }).click();
  await continueWithAssumptions(page);
});

Then("zeigen die Nachrichten {string}", async ({ page }, text: string) => {
  await expect(page.getByTestId("messages")).toContainText(text);
});

Then("wird kein Projekt angezeigt", async ({ page }) => {
  await expect(page.getByTestId("project-panel")).toHaveCount(0);
});

Then("zeigen die Arbeitsschritte des Assistenten {string}", async ({ page }, text: string) => {
  await expect(page.getByRole("list", { name: "Arbeitsschritte des Assistenten" })).toContainText(
    text,
  );
});

Then("ist das Eingabefeld wieder bereit", async ({ page }) => {
  await expect(page.getByLabel(PROMPT)).toBeVisible();
});

When("ich die Projektidee {string} wähle", async ({ page }, idea: string) => {
  await page.getByRole("button", { name: new RegExp(`^${idea}`) }).click();
});

Then("steht im Eingabefeld {string}", async ({ page }, text: string) => {
  await expect(page.getByLabel(PROMPT)).toHaveValue(new RegExp(text));
});

When("ich im Brief bei {string} die Option {string} wähle", async ({ page }, field, option) => {
  const brief = page.getByTestId("project-brief");
  await brief.getByRole("button", { name: new RegExp(`^${field}`) }).click();
  const panel = brief.getByRole("region", { name: field });
  await panel.getByRole("button", { name: option }).click();
  await expect(panel.getByRole("button", { name: option })).toHaveAttribute("aria-pressed", "true");
});

Then("zeigen die Details im Brief {string}", async ({ page }, text: string) => {
  const details = page
    .getByTestId("project-brief")
    .getByRole("list", { name: "Details (optional)" });
  await expect(details).toContainText(text);
});

When("ich die Planung starte", async ({ page }) => {
  await page.getByTestId("project-brief").getByRole("button", { name: "Planung starten" }).click();
  await continueWithAssumptions(page);
});

// ---------------------------------------------------------------------------------------------
// Keyboard
// ---------------------------------------------------------------------------------------------

When(
  "ich außerhalb eines Eingabefelds die Taste {string} drücke",
  async ({ page }, key: string) => {
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    await page.keyboard.press(key);
  },
);

Then("hat das Eingabefeld des Chats den Fokus", async ({ page }) => {
  await expect(page.locator("#chat-input")).toBeFocused();
});

Then("das Zeichen {string} wurde nicht eingegeben", async ({ page }, char: string) => {
  await expect(page.locator("#chat-input")).not.toHaveValue(new RegExp(escapeRegExp(char)));
});

// ---------------------------------------------------------------------------------------------
// Project panel
// ---------------------------------------------------------------------------------------------

Then("zeigt die Projektzusammenfassung {string}", async ({ page }, summary: string) => {
  await expect(page.getByTestId("project-summary")).toHaveText(summary);
});

Then("zeigt das Projekt das Kennzeichen {string}", async ({ page }, badge: string) => {
  await expect(page.getByTestId("design-badge")).toHaveText(badge);
});

Then("ist das 3D-Modell sichtbar", async ({ page }) => {
  await expect(page.getByTestId("viewer-3d")).toBeVisible();
});

Then("zeigt die Positionsliste {string}", async ({ page }, text: string) => {
  await expect(page.getByRole("list", { name: "Positionen" })).toContainText(text);
});

When("ich auf {string} klicke", async ({ page }, name: string) => {
  await page.getByRole("button", { name, exact: true }).click();
});

When("ich den Reiter {string} öffne", async ({ page }, name: string) => {
  await page.getByRole("tab", { name }).click();
});

Then("gibt es keinen Reiter {string}", async ({ page }, name: string) => {
  await expect(page.getByRole("tab", { name })).toHaveCount(0);
});

Then("zeigt der Reiterinhalt {string}", async ({ page }, text: string) => {
  await expect(page.getByRole("tabpanel")).toContainText(text);
});

Then("zeigt die Materialliste {string}", async ({ page }, text: string) => {
  await expect(page.getByTestId("bom")).toContainText(text);
});

When("ich das Feld {string} auf {string} setze und bestätige", async ({ page }, label, value) => {
  const field = page.getByLabel(label);
  await field.fill(value);
  await field.press("Enter");
});

Given("ich merke mir die angezeigten Materialkosten", async ({ page, ui }) => {
  ui.rememberedCost = await page.getByTestId("material-cost").textContent();
});

Then("haben sich die angezeigten Materialkosten geändert", async ({ page, ui }) => {
  await expect(page.getByTestId("material-cost")).not.toHaveText(ui.rememberedCost ?? "");
});

Then("zeigen die Materialkosten wieder den gemerkten Wert", async ({ page, ui }) => {
  await expect(page.getByTestId("material-cost")).toHaveText(ui.rememberedCost ?? "");
});

// ---------------------------------------------------------------------------------------------
// Drawings
// ---------------------------------------------------------------------------------------------

Given("ich zähle ab jetzt die geladenen Zeichnungen", async ({ page, ui }) => {
  page.on("request", (request) => {
    if (request.url().includes("/drawings/")) {
      ui.drawingRequests.push(new URL(request.url()).pathname.split("/").pop() ?? "");
    }
  });
});

When("ich in den Plänen die Ansicht {string} wähle", async ({ page }, name: string) => {
  await page.getByRole("button", { name: "Pläne" }).click();
  await page
    .getByRole("button", { name: new RegExp(`^${name}`) })
    .first()
    .click();
});

Then(
  "zeigt die Zeichnung {string} eine Beschreibung mit {string}",
  async ({ page }, view: string, text: string) => {
    const drawing = page.getByTestId(`drawing-${view}`);
    await expect(drawing).toHaveAttribute("alt", new RegExp(escapeRegExp(text)));
    await expect
      .poll(() => drawing.evaluate((img: HTMLImageElement) => img.naturalWidth))
      .toBeGreaterThan(0);
  },
);

Then("wurden nur die Zeichnungen {string} geladen", async ({ ui }, files: string) => {
  const expected = new Set(files.split(",").map((f) => f.trim()));
  expect(new Set(ui.drawingRequests)).toEqual(expected);
});

// ---------------------------------------------------------------------------------------------
// PDF
// ---------------------------------------------------------------------------------------------

Then("führt der Link {string} zu einem PDF", async ({ page }, name: string) => {
  const href = await page.getByRole("link", { name }).getAttribute("href");
  const pdf = await page.request.get(href!);
  expect(pdf.headers()["content-type"]).toBe("application/pdf");
  expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");
});

When("ich das PDF herunterlade", async ({ page, ui }) => {
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "PDF herunterladen" }).click();
  const download = await downloadPromise;
  expect(await download.failure()).toBeNull();
  ui.downloaded = true;
  ui.downloadName = download.suggestedFilename();
  ui.downloadBytes = await readFile((await download.path())!);
});

Then("ist die Datei ein PDF mit mehr als {int} Bytes", async ({ ui }, size: number) => {
  expect(ui.downloadName).toMatch(/^homeworking-.*\.pdf$/);
  expect(ui.downloadBytes?.subarray(0, 5).toString()).toBe("%PDF-");
  expect(ui.downloadBytes?.length ?? 0).toBeGreaterThan(size);
});

Given("die PDF-Erstellung ist gestört", async ({ page, ui }) => {
  await page.route("**/document.pdf*", (route) =>
    route.fulfill({ status: 500, body: "Internal Server Error" }),
  );
  page.on("download", () => {
    ui.downloaded = true;
  });
});

Given("die PDF-Erstellung funktioniert wieder", async ({ page, ui }) => {
  await page.unroute("**/document.pdf*");
  ui.downloaded = false;
});

When("ich auf den Link {string} klicke", async ({ page }, name: string) => {
  await page.getByRole("link", { name }).click();
});

Then("sehe ich die PDF-Fehlermeldung {string}", async ({ page }, text: string) => {
  await expect(page.locator("#pdf-error")).toContainText(text);
});

Then("sehe ich keine PDF-Fehlermeldung", async ({ page }) => {
  await expect(page.locator("#pdf-error")).toHaveCount(0);
});

Then("wurde nichts heruntergeladen", async ({ ui }) => {
  expect(ui.downloaded).toBe(false);
});

// ---------------------------------------------------------------------------------------------
// Prices
// ---------------------------------------------------------------------------------------------

Then("sehe ich den Text {string}", async ({ page }, text: string) => {
  await expect(page.getByText(text)).toBeVisible();
});

Then("sehe ich den Text {string} nicht", async ({ page }, text: string) => {
  await expect(page.getByText(text)).toHaveCount(0);
});

Then("zeigt der Preisstatus {string}", async ({ page }, text: string) => {
  await expect(page.getByTestId("price-status")).toHaveText(new RegExp(`^${escapeRegExp(text)}$`));
});

Then("zeigt der Preisstatus eigene Preise für {int} Position", async ({ page }, count: number) => {
  await expect(page.getByTestId("price-status")).toHaveText(
    new RegExp(`^${count} von \\d+ Positionen? mit deinem Preis\\.$`),
  );
});

Then(
  "verweist der erste Link {string} auf {string}",
  async ({ page }, name: string, prefix: string) => {
    const link = page.getByRole("link", { name: new RegExp(`^${name}`) }).first();
    await expect(link).toHaveAttribute("href", new RegExp(`^${escapeRegExp(prefix)}`));
  },
);

Given("ich merke mir die Summe der Materialliste", async ({ page, ui }) => {
  ui.rememberedCost = await page.getByTestId("bom-total").textContent();
});

Then("hat sich die Summe der Materialliste geändert", async ({ page, ui }) => {
  await expect(page.getByTestId("bom-total")).not.toHaveText(ui.rememberedCost ?? "");
});

// ---------------------------------------------------------------------------------------------
// Versions and stored chat
// ---------------------------------------------------------------------------------------------

const CHAT_HISTORY_URL = "**/api/projects/*/chat";

Given("das Laden des Chatverlaufs ist gestört", async ({ page }) => {
  await page.route(CHAT_HISTORY_URL, (route) =>
    route.fulfill({ status: 500, body: "Internal Server Error" }),
  );
});

Given("das Laden des Chatverlaufs funktioniert wieder", async ({ page }) => {
  await page.unroute(CHAT_HISTORY_URL);
});

Then("zeigt der Versionsverlauf {string}", async ({ page }, text: string) => {
  await expect(page.getByTestId("version-history")).toContainText(text);
});

When("ich im Versionsverlauf die Version {int} öffne", async ({ page }, seq: number) => {
  await page
    .getByTestId("version-history")
    .getByRole("button", { name: new RegExp(`^V${seq} `) })
    .click();
});

Then("zeigt das Versionsbanner {string}", async ({ page }, text: string) => {
  await expect(page.getByTestId("version-banner")).toContainText(text);
});

Then("ist kein Versionsbanner zu sehen", async ({ page }) => {
  await expect(page.getByTestId("version-banner")).toHaveCount(0);
});

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
