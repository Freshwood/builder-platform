import clsx from "clsx";
import type { ReactNode } from "react";

/** Stroke icons (24 × 24, Lucide-style paths) used across the app. */
export const ICONS = {
  info: "M12 8h.01M11 12h1v5h1M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z",
  warning:
    "M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z",
  euro: "M17 6.5A7 7 0 1 0 17 17.5M4 10h9M4 14h9",
  cube: "m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Zm0 0v18m8-13.5-8 4.5-8-4.5",
  send: "M5 12h14M13 6l6 6-6 6",
  undo: "M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11",
  download: "M12 4v12m0 0-5-5m5 5 5-5M5 20h14",
  sparkles:
    "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3ZM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z",
  plus: "M12 5v14M5 12h14",
  close: "M6 6l12 12M18 6 6 18",
  check: "M5 12.5l4.5 4.5L19 7.5",
  chevron: "m9 6 6 6-6 6",
  chevronDown: "m6 9 6 6 6-6",
  location:
    "M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21Zm0-9a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z",
  ruler: "M3 17 17 3l4 4L7 21l-4-4Zm4-4 2 2m1-5 2 2m1-5 2 2",
  tree: "M12 3 6 11h3l-4 6h14l-4-6h3l-6-8Zm0 14v4",
  brush:
    "M18.4 2.6a2 2 0 0 1 2.9 2.9L12 14.8 9.2 12l9.2-9.4ZM9 13.5c-2 0-3.5 1.6-3.5 3.5 0 1.5-1 2.5-2.5 3 4 1 9 0 9-3.5 0-1.7-1.3-3-3-3Z",
  wallet:
    "M4 7h15a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7Zm0 0V6a2 2 0 0 1 2-2h11M16 13.5h.01",
  toolbox:
    "M3 9h18v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9Zm5 0V6a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v3M3 13h18M10 13v2h4v-2",
  message: "M4 5h16v11H8l-4 4V5Z",
  layers: "m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5",
  sliders: "M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M14 4v4M8 10v4M16 16v4",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  scissors:
    "M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm0 12a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12",
  hammer:
    "m15 12-8.4 8.4a2 2 0 0 1-2.8-2.8L12.2 9.2M17.6 14.6 22 10.2l-4.2-4.2-1.4 1.4-2.8-2.8L15 3.2 11 2 9.6 3.4l2.8 2.8-1.4 1.4 4.2 4.2",
  lightbulb:
    "M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0 0 12 3Z",
  image: "M4 5h16v14H4V5Zm0 11 4.5-4.5L13 16m-2-2 2.5-2.5L20 18M15.5 9h.01",
  rotate: "M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5",
  folder: "M3 6a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6Z",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm9 2-4-4",
  shield: "M12 3 5 6v5c0 5 3 8.5 7 10 4-1.5 7-5 7-10V6l-7-3Z",
} as const;

export type IconName = keyof typeof ICONS;

export function Icon({ name, className }: { name: IconName; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className={clsx("h-5 w-5 shrink-0", className)}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={ICONS[name]} />
    </svg>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={clsx(
        "inline-block h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent",
        className,
      )}
    />
  );
}

export const TRUST: Record<string, { label: string; hint: string; className: string }> = {
  pack: {
    label: "Geprüftes Pack",
    hint: "Fachlich validierte Konstruktionsregeln",
    className: "bg-success-soft text-success",
  },
  template: {
    label: "Vorlage",
    hint: "Konstruktion aus der Homeworking-Vorlagensammlung",
    className: "bg-surface-muted text-text",
  },
  ai_draft: {
    label: "KI-Entwurf",
    hint: "Konstruktion von der KI vorgeschlagen, nicht fachlich geprüft",
    className: "bg-ai-soft text-ai",
  },
};

export function Pill({
  children,
  className,
  title,
  testId,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
  testId?: string;
}) {
  return (
    <span
      title={title}
      data-testid={testId}
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold",
        className,
      )}
    >
      {children}
    </span>
  );
}

export const buttonClass = {
  primary:
    "inline-flex items-center justify-center gap-2 rounded-md bg-accent px-4 py-2 font-semibold text-on-accent transition hover:brightness-105 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-40",
  secondary:
    "inline-flex items-center justify-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-sm font-medium transition hover:bg-surface-muted active:scale-[0.98] disabled:pointer-events-none disabled:opacity-40",
  ghost:
    "inline-flex items-center justify-center gap-2 rounded-lg px-2 py-1.5 text-sm font-medium text-muted transition hover:bg-surface-muted hover:text-text disabled:pointer-events-none disabled:opacity-40",
};

/** Accessible segmented control (radio group semantics with buttons). */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
  className,
}: {
  label: string;
  options: { value: T; label: ReactNode }[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className={clsx(
        "inline-flex rounded-md border border-border bg-surface/85 p-0.5 shadow-sm backdrop-blur",
        className,
      )}
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
          className={clsx(
            "inline-flex items-center gap-1.5 rounded-[4px] px-3 py-1.5 text-sm font-medium transition",
            option.value === value ? "bg-text text-bg shadow-sm" : "text-muted hover:text-text",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** Relative German time ("vor 5 Min.") for list entries. */
const RELATIVE = new Intl.RelativeTimeFormat("de-DE", { numeric: "auto", style: "short" });

export function relativeTime(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  const format = RELATIVE;
  if (seconds < 60) return "gerade eben";
  if (seconds < 3600) return format.format(-Math.round(seconds / 60), "minute");
  if (seconds < 86400) return format.format(-Math.round(seconds / 3600), "hour");
  if (seconds < 86400 * 30) return format.format(-Math.round(seconds / 86400), "day");
  return new Date(iso).toLocaleDateString("de-DE");
}
