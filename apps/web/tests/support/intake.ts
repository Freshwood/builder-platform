import { expect, type Page } from "@playwright/test";

/**
 * The brief asks the engine for open questions before the planning starts. Wait for the outcome
 * of that check: answer the questions with "Weiter mit Annahmen" when they appear, otherwise the
 * request went straight into the chat. In a running chat (follow-up message) nothing is asked.
 * Returns once the chat is shown, so the request has been sent.
 */
export async function continueWithAssumptions(page: Page) {
  const questions = page.getByTestId("intake-questions");
  const chat = page.getByTestId("messages");
  // The two are mutually exclusive: the questions live in the landing page's brief form, the
  // chat replaces that page once the first message is sent.
  const outcome = questions.or(chat).first();
  await expect(outcome).toBeVisible();
  // Reading the attribute of the element we just waited for avoids a second, racing visibility
  // check against a page that may already have moved on.
  if ((await outcome.getAttribute("data-testid")) === "intake-questions") {
    await outcome.getByRole("button", { name: /^Weiter/ }).click();
  }
  await expect(chat).toBeVisible();
}
