"use client";

import clsx from "clsx";

import { Icon } from "@/components/ui";
import type { Option } from "@/lib/brief";

/** Inputs shared by the project brief and the intake questions. */

export function Chips({
  legend,
  options,
  value,
  onChange,
  multiple = false,
}: {
  legend: string;
  options: Option[];
  value: string | string[];
  onChange: (value: string | string[]) => void;
  multiple?: boolean;
}) {
  const selected = (v: string) => (Array.isArray(value) ? value.includes(v) : value === v);
  function toggle(v: string) {
    if (Array.isArray(value)) {
      onChange(selected(v) ? value.filter((x) => x !== v) : [...value, v]);
    } else {
      // Clicking the active chip again clears the choice ("egal").
      onChange(selected(v) ? "" : v);
    }
  }
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-medium">
        {legend}
        {multiple && <span className="ml-1 font-normal text-muted">(mehrere möglich)</span>}
      </legend>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected(option.value)}
            onClick={() => toggle(option.value)}
            className={clsx(
              "inline-flex items-center gap-1 rounded-full border px-3 py-1.5 text-sm transition",
              selected(option.value)
                ? "border-text bg-accent-soft font-medium"
                : "border-border bg-surface hover:border-muted/50 hover:bg-surface-muted",
            )}
          >
            {selected(option.value) && <Icon name="check" className="h-3.5 w-3.5" />}
            {option.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

export const inputClass =
  "w-full rounded-md border border-border bg-surface px-3 py-2 text-base placeholder:text-muted/70 focus:border-text focus:ring-1 focus:ring-text focus:outline-none";

export function NumberInput({
  label,
  value,
  onChange,
  unit,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  unit: string;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-muted">{label}</span>
      <span className="relative block">
        <input
          inputMode="decimal"
          value={value}
          onChange={(event) => onChange(event.target.value.replace(/[^\d.,]/g, ""))}
          className={clsx(inputClass, "pr-10 tabular-nums")}
        />
        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-muted">
          {unit}
        </span>
      </span>
    </label>
  );
}
