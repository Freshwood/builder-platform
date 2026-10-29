import { createBdd, test as base } from "playwright-bdd";

/** UI scenario state that must survive between steps. */
export class UiWorld {
  rememberedCost: string | null = null;
  drawingRequests: string[] = [];
  downloaded = false;
  downloadBytes: Buffer | undefined;
  downloadName: string | undefined;
}

export const test = base.extend<{ ui: UiWorld }>({
  ui: async ({}, use) => {
    await use(new UiWorld());
  },
});

export const { Given, Then, When } = createBdd(test);
