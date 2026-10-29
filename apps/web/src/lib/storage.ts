import { useEffect, useState } from "react";

/** Numbers stored as a JSON array; anything else (missing, corrupt, foreign data) is empty. */
export function parseStoredSet(raw: string | null): Set<number> {
  if (!raw) return new Set();
  try {
    const value: unknown = JSON.parse(raw);
    if (!Array.isArray(value)) return new Set();
    return new Set(value.filter((item): item is number => Number.isInteger(item)));
  } catch {
    return new Set();
  }
}

function readSet(key: string): Set<number> {
  try {
    return parseStoredSet(window.localStorage.getItem(key));
  } catch {
    // Storage unavailable (private mode): progress just is not remembered.
    return new Set();
  }
}

function writeSet(key: string, items: Set<number>) {
  try {
    window.localStorage.setItem(key, JSON.stringify([...items]));
  } catch {
    // See readSet.
  }
}

type Stored = { key: string; items: Set<number>; changed: boolean };

/**
 * A set of numbers remembered in localStorage under ``key``, e.g. the build steps ticked off.
 * Only used client-side after data has loaded, so storage is available on first render. When
 * ``key`` changes, the set of the new key is loaded instead of showing the old one.
 */
export function useStoredSet(key: string): [Set<number>, (n: number) => void] {
  const [stored, setStored] = useState<Stored>(() => ({
    key,
    items: readSet(key),
    changed: false,
  }));
  // Derived state: React re-renders at once with the new key before anything is committed.
  if (stored.key !== key) setStored({ key, items: readSet(key), changed: false });

  // Persist after a toggle, not inside the state updater (which has to stay free of effects).
  useEffect(() => {
    if (stored.changed) writeSet(stored.key, stored.items);
  }, [stored]);

  function toggle(n: number) {
    setStored((current) => {
      const items = new Set(current.items);
      if (!items.delete(n)) items.add(n);
      return { key: current.key, items, changed: true };
    });
  }
  return [stored.items, toggle];
}
