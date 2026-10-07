// Compiles every route of the dev server right after start-up.
//
// `next dev` compiles a route only on its first request. On slow file systems (WSL with the
// repository under /mnt/c, virus scanners) that takes from several seconds up to minutes, and
// the user sees nothing but the "Rendering …" badge. Requesting each route once in the
// background moves that wait to start-up, before anybody opens a project.

const origin = process.env.WARMUP_ORIGIN ?? "http://localhost:3000";
// Dynamic segments only need any value: the project page loads its data in the browser.
const routes = [
  "/",
  "/projects",
  "/projects/00000000-0000-0000-0000-000000000000",
  "/impressum",
  "/datenschutz",
];
const startupTimeoutMs = 5 * 60_000;

async function waitForServer() {
  const deadline = Date.now() + startupTimeoutMs;
  while (Date.now() < deadline) {
    try {
      await fetch(origin, { method: "HEAD", signal: AbortSignal.timeout(2_000) });
      return true;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 1_000));
    }
  }
  return false;
}

if (!(await waitForServer())) {
  console.warn(`warmup: ${origin} did not answer, skipped`);
  process.exit(0);
}
for (const route of routes) {
  const started = Date.now();
  try {
    const response = await fetch(origin + route, { signal: AbortSignal.timeout(10 * 60_000) });
    await response.arrayBuffer();
    console.log(`warmup: ${route} ${response.status} in ${Date.now() - started} ms`);
  } catch (error) {
    console.warn(`warmup: ${route} failed: ${error}`);
  }
}
