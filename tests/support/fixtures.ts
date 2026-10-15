import { createBdd, test as base } from "playwright-bdd";

import { ApiWorld } from "./world";

/** UI scenario state that must survive between steps. */
export class UiWorld {
  rememberedCost: string | null = null;
  drawingRequests: string[] = [];
  downloaded = false;
  downloadBytes: Buffer | undefined;
  downloadName: string | undefined;
}

export const test = base.extend<{ api: ApiWorld; ui: UiWorld }>({
  api: async ({ request }, use) => {
    await use(new ApiWorld(request));
  },
  ui: async ({}, use) => {
    await use(new UiWorld());
  },
});

export const { Given, When, Then } = createBdd(test);
