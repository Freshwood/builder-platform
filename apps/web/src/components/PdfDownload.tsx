"use client";

import { useState, type MouseEvent } from "react";

function filenameFrom(disposition: string | null, fallback: string): string {
  const match = disposition?.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  return match?.[1] ? decodeURIComponent(match[1]) : fallback;
}

async function errorText(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Not JSON (e.g. a proxy error page): fall through to the generic message.
  }
  return response.status === 404
    ? "Das Projekt wurde nicht gefunden."
    : "Das PDF konnte nicht erstellt werden. Bitte versuche es erneut.";
}

/**
 * Downloads the project PDF via fetch instead of a bare link: a failed request would otherwise
 * make the browser save the error text as "document.txt". The link stays a real link (href) so
 * "open in new tab" and middle click keep working.
 */
export function PdfDownload({ projectId, version }: { projectId: string; version: string }) {
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState("");
  const href = `/api/projects/${projectId}/document.pdf`;

  async function onClick(event: MouseEvent<HTMLAnchorElement>) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
    event.preventDefault();
    if (state === "loading") return;
    setState("loading");
    try {
      // ``version`` is already URL-encoded and changes with every parameter change.
      const response = await fetch(`${href}?v=${version}`, {
        credentials: "include",
      });
      const type = response.headers.get("content-type") ?? "";
      if (!response.ok || !type.includes("application/pdf")) {
        setMessage(await errorText(response));
        setState("error");
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filenameFrom(
        response.headers.get("content-disposition"),
        `homeworking-${projectId.slice(0, 8)}.pdf`,
      );
      document.body.append(link);
      link.click();
      link.remove();
      // Give the browser time to start the download before releasing the blob.
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      setState("idle");
    } catch {
      setMessage("Keine Verbindung zum Server. Bitte versuche es erneut.");
      setState("error");
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <a
        href={href}
        onClick={onClick}
        aria-busy={state === "loading"}
        aria-describedby={state === "error" ? "pdf-error" : undefined}
        className="inline-flex items-center gap-2 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white aria-busy:opacity-80 dark:text-black"
        data-testid="pdf-download"
      >
        {state === "loading" && (
          <span
            aria-hidden="true"
            className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white dark:border-black/30 dark:border-t-black"
          />
        )}
        PDF herunterladen
      </a>
      <span className="sr-only" aria-live="polite">
        {state === "loading" ? "PDF wird erstellt" : ""}
      </span>
      {state === "loading" && <span className="text-xs text-muted">PDF wird erstellt …</span>}
      {state === "error" && (
        <span id="pdf-error" role="alert" className="max-w-56 text-right text-xs text-warning">
          {message}
        </span>
      )}
    </div>
  );
}
