"use client";

import { useLayoutEffect, useRef, type KeyboardEvent } from "react";

/** Multi-line text input that grows with its content (up to ``maxRows``). */
export function AutoTextarea({
  value,
  onChange,
  minRows = 1,
  maxRows = 12,
  className,
  ...rest
}: {
  value: string;
  onChange: (value: string) => void;
  minRows?: number;
  maxRows?: number;
  className?: string;
  id?: string;
  placeholder?: string;
  autoFocus?: boolean;
  disabled?: boolean;
  onKeyDown?: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const style = window.getComputedStyle(el);
    const line = parseFloat(style.lineHeight) || 24;
    const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    const border = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
    el.style.height = "auto";
    const min = minRows * line + padding + border;
    const max = maxRows * line + padding + border;
    const height = Math.min(max, Math.max(min, el.scrollHeight + border));
    el.style.height = `${height}px`;
    el.style.overflowY = el.scrollHeight + border > max ? "auto" : "hidden";
  }, [value, minRows, maxRows]);

  return (
    <textarea
      ref={ref}
      rows={minRows}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className={className}
      {...rest}
    />
  );
}
