import { useEffect, useEffectEvent } from "react";

/** True while the user types into a field; global shortcuts must leave those keystrokes alone. */
export function isTyping(target: EventTarget | null): boolean {
  const element = target as { closest?: (selector: string) => unknown } | null;
  return Boolean(element?.closest?.("input, textarea, select, [contenteditable]"));
}

/**
 * Listen for key presses anywhere on the page. The handler always sees the latest props and
 * state without the listener being re-attached on every render.
 */
export function useGlobalKey(handler: (event: KeyboardEvent) => void) {
  const onKeyDown = useEffectEvent(handler);
  useEffect(() => {
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
