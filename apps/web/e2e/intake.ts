import type { Page } from "@playwright/test";

/**
 * The brief asks the engine for open questions before the planning starts. Answer them with
 * "Weiter mit Annahmen" when they appear; in the chat (or when nothing is open) just return.
 */
export async function continueWithAssumptions(page: Page) {
  const questions = page.getByTestId("intake-questions");
  await questions.or(page.getByTestId("messages")).first().waitFor();
  if (await questions.isVisible()) {
    await questions.getByRole("button", { name: /^Weiter/ }).click();
  }
}
