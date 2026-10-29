"use client";

import clsx from "clsx";
import type { ReactNode } from "react";

import { Icon, type IconName } from "@/components/ui";

import type { TabKey } from "./types";

export type TabItem = { key: TabKey; label: string; icon: IconName; count?: number };

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: TabItem[];
  active: TabKey;
  onChange: (key: TabKey) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Projektdetails"
      className="scrollbar-thin flex gap-1 overflow-x-auto rounded-lg bg-surface-muted p-1"
    >
      {tabs.map((tab) => (
        <button
          key={tab.key}
          id={`tab-${tab.key}`}
          role="tab"
          type="button"
          aria-selected={active === tab.key}
          aria-controls={`panel-${tab.key}`}
          tabIndex={active === tab.key ? 0 : -1}
          onClick={() => onChange(tab.key)}
          onKeyDown={(event) => {
            const index = tabs.findIndex((t) => t.key === active);
            const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
            if (delta) {
              const next = tabs[(index + delta + tabs.length) % tabs.length]!;
              onChange(next.key);
              document.getElementById(`tab-${next.key}`)?.focus();
            }
          }}
          className={clsx(
            "inline-flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium whitespace-nowrap transition",
            active === tab.key ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text",
          )}
        >
          <Icon name={tab.icon} className="h-4 w-4" />
          {tab.label}
          {tab.count != null && (
            <span className="rounded-full bg-surface-muted px-1.5 text-xs text-muted">
              {tab.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

export function Panel({
  tab,
  active,
  children,
}: {
  tab: TabKey;
  active: TabKey;
  children: ReactNode;
}) {
  return (
    <div
      role="tabpanel"
      id={`panel-${tab}`}
      aria-labelledby={`tab-${tab}`}
      hidden={tab !== active}
      className="pt-5"
    >
      {/* Inactive tabs are not rendered (BOM rows, cut plan and steps are large). */}
      {tab === active ? children : null}
    </div>
  );
}
