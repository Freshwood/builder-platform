"use client";

import { Icon, buttonClass } from "@/components/ui";
import { useRestoreVersion } from "@/lib/api";

/** Shown while an earlier version is displayed: restore it or go back to the current one. */
export function VersionBanner({
  projectId,
  seq,
  onClose,
}: {
  projectId: string;
  seq: number;
  onClose: () => void;
}) {
  const restore = useRestoreVersion(projectId);
  return (
    <div
      role="status"
      className="sticky top-3 z-20 flex flex-wrap items-center gap-3 rounded-lg border border-accent bg-accent-soft/95 px-4 py-3 text-sm shadow-lg backdrop-blur"
      data-testid="version-banner"
    >
      <Icon name="layers" className="h-4 w-4 text-accent-strong" />
      <span className="flex-1">
        Du siehst <strong>Version {seq}</strong> – nur zum Ansehen. Wiederherstellen legt sie als
        neue Version an; nichts geht verloren.
      </span>
      {restore.error && <span className="text-warning">{restore.error.message}</span>}
      <button
        type="button"
        className={buttonClass.primary}
        disabled={restore.isPending}
        onClick={() => restore.mutate(seq, { onSuccess: onClose })}
      >
        <Icon name="rotate" className="h-4 w-4" />
        Diese Version wiederherstellen
      </button>
      <button type="button" className={buttonClass.secondary} onClick={onClose}>
        Zur aktuellen Version
      </button>
    </div>
  );
}
