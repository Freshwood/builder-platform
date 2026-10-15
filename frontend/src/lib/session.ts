let ready: Promise<void> | null = null;

/**
 * Resolves once the browser holds a session cookie. The API creates a guest account for every
 * request without a cookie, so parallel first requests (project list and chat) would otherwise
 * end up with different guests and the new project would belong to the wrong one.
 */
export function sessionReady(): Promise<void> {
  ready ??= fetch("/api/me", { credentials: "include" }).then(
    () => undefined,
    () => {
      // Try again with the next request instead of blocking forever.
      ready = null;
    },
  );
  return ready;
}
