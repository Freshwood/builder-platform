"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { ProjectBrief } from "@/components/ProjectBrief";
import { ProjectThumb } from "@/components/ProjectList";
import { Icon, relativeTime, type IconName } from "@/components/ui";
import { useProjects } from "@/lib/api";
import { EMPTY_BRIEF, type Brief } from "@/lib/brief";

/** Small line illustrations (64 × 48) for the idea cards. */
const ART: Record<string, ReactNode> = {
  bed: (
    <>
      <path d="M8 22 32 12l24 10v14L32 46 8 36V22Z" />
      <path d="M8 22l24 10 24-10M32 32v14" />
      <path d="M18 18c2-6 6-8 8-6M28 15c0-6 4-9 7-7M38 15c2-5 6-6 8-3" className="text-success" />
    </>
  ),
  shelf: (
    <>
      <path d="M20 4h24v42H20z" />
      <path d="M20 14h24M20 24h24M20 34h24" />
      <path d="M24 8v6M27 9v5M36 18v6M39 18v6M25 28v6" className="text-accent" />
    </>
  ),
  bench: (
    <>
      <path d="M6 26h52M8 31h48M12 26v16M52 26v16M10 8h44v12H10z" />
      <path d="M10 14h44" />
    </>
  ),
  shutter: (
    <>
      <path d="M12 6h18v38H12zM34 6h18v38H34z" />
      <path d="M16 6v38M21 6v38M26 6v38M38 6v38M43 6v38M48 6v38" className="opacity-50" />
      <path d="M12 14h18M34 14h18M12 36h18M34 36h18" className="text-accent" />
    </>
  ),
  workbench: (
    <>
      <path d="M4 14h56v6H4zM8 20v24M56 20v24M8 34h48" />
      <path d="M40 8h12v6H40z" className="text-accent" />
    </>
  ),
  herbs: (
    <>
      <path d="M14 44 22 8M50 44 42 8M18 30h28M14 42h36M20 18h24" />
      <path
        d="M24 14c1-4 3-5 5-4M34 14c1-4 4-5 6-3M24 26c1-4 3-5 5-4M36 26c1-4 4-5 6-3"
        className="text-success"
      />
    </>
  ),
};

export const IDEAS: { key: string; title: string; hint: string; brief: Partial<Brief> }[] = [
  {
    key: "bed",
    title: "Hochbeet",
    hint: "Lärche · 2 × 1 m",
    brief: {
      description: "Ein Hochbeet für Gemüse an der Terrasse.",
      location: "outdoor",
      mounting: "floor",
      width: "200",
      depth: "100",
      height: "80",
      wood: "larch",
    },
  },
  {
    key: "shelf",
    title: "Bücherregal",
    hint: "5 Böden · innen",
    brief: {
      description: "Ein Bücherregal mit 5 Böden für das Arbeitszimmer.",
      location: "indoor",
      mounting: "floor",
      width: "80",
      depth: "30",
      height: "180",
      usage: "Bücher, ca. 25 kg pro Boden",
    },
  },
  {
    key: "bench",
    title: "Gartenbank",
    hint: "1,6 m · mit Lehne",
    brief: {
      description: "Eine Gartenbank 1,6 m lang mit Rückenlehne.",
      location: "outdoor",
      wood: "larch",
      finish: "oil",
    },
  },
  {
    key: "shutter",
    title: "Fensterläden",
    hint: "zweiflügelig · Douglasie",
    brief: {
      description: "Zwei Fensterläden aus Brettern für ein Fenster, zweiflügelig.",
      location: "outdoor",
      mounting: "wall",
      width: "100",
      height: "120",
      sizeMode: "exact",
      wood: "douglas",
      finish: "glaze",
    },
  },
  {
    key: "workbench",
    title: "Werkbank",
    hint: "stabil · mit Ablage",
    brief: {
      description: "Eine stabile Werkbank für die Garage mit Ablageboden.",
      location: "indoor",
      mounting: "floor",
      width: "150",
      depth: "70",
      height: "90",
    },
  },
  {
    key: "herbs",
    title: "Kräuterregal",
    hint: "Balkon · 3 Ebenen",
    brief: {
      description: "Ein Kräuterregal für den Balkon mit drei schrägen Ebenen.",
      location: "covered",
      mounting: "floor",
      width: "90",
      sizeMode: "max",
    },
  },
];

function IdeaCard({ idea, onPick }: { idea: (typeof IDEAS)[number]; onPick: () => void }) {
  return (
    <button
      type="button"
      onClick={onPick}
      className="group flex flex-col items-start rounded-2xl border border-border bg-surface p-3 text-left transition hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-lg active:translate-y-0"
    >
      <svg
        viewBox="0 0 64 48"
        aria-hidden="true"
        className="mb-2 h-12 w-16 text-muted transition group-hover:text-text"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {ART[idea.key]}
      </svg>
      <span className="font-semibold">{idea.title}</span>
      <span className="text-xs text-muted">{idea.hint}</span>
    </button>
  );
}

const STEPS: { icon: IconName; title: string; text: string }[] = [
  {
    icon: "message",
    title: "Beschreiben",
    text: "In eigenen Worten – Details nur, wenn du magst.",
  },
  {
    icon: "cube",
    title: "Planen lassen",
    text: "Die KI entwirft, die Engine rechnet Maße, Material und Kosten exakt.",
  },
  {
    icon: "hammer",
    title: "Bauen",
    text: "3D-Modell, Zuschnitt, Einkaufsliste und Anleitung zum Abhaken.",
  },
];

function RecentProjects() {
  const { data } = useProjects();
  const recent = (data ?? [])
    .slice()
    .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""))
    .slice(0, 3);
  if (!recent.length) return null;
  return (
    <section aria-labelledby="recent-heading" className="mt-12">
      <div className="mb-3 flex items-baseline justify-between">
        <h2
          id="recent-heading"
          className="text-sm font-semibold uppercase tracking-wide text-muted"
        >
          Weiter planen
        </h2>
        <Link href="/projects" className="text-sm font-medium text-accent-strong hover:underline">
          Alle Projekte
        </Link>
      </div>
      <ul className="grid gap-3 sm:grid-cols-3">
        {recent.map((project) => (
          <li key={project.id}>
            <Link
              href={`/projects/${project.id}`}
              className="flex items-center gap-3 rounded-2xl border border-border bg-surface p-2 pr-3 transition hover:border-accent/40 hover:shadow-md"
            >
              <ProjectThumb id={project.id} className="h-14 w-14 shrink-0 rounded-xl" />
              <span className="min-w-0">
                <span className="block truncate font-semibold">{project.title}</span>
                {project.updated_at && (
                  <span className="block text-xs text-muted">
                    {relativeTime(project.updated_at)}
                  </span>
                )}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Landing({
  brief,
  onBriefChange,
  onSubmit,
  busy,
}: {
  brief: Brief;
  onBriefChange: (brief: Brief) => void;
  onSubmit: (message: string) => boolean;
  busy: boolean;
}) {
  return (
    <div className="relative mx-auto max-w-3xl px-4 pt-10 pb-16 sm:pt-20">
      {/* Soft warm glow behind the prompt */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 mx-auto h-80 max-w-2xl rounded-full bg-[radial-gradient(closest-side,var(--accent-soft),transparent)] opacity-90 blur-2xl"
      />
      <p className="mb-4 flex justify-center">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface/80 px-3 py-1 text-xs font-medium text-muted backdrop-blur">
          <Icon name="sparkles" className="h-3.5 w-3.5 text-ai" />
          KI-Planung · exakt gerechnet
        </span>
      </p>
      <h1 className="text-center text-4xl font-bold tracking-tight text-balance sm:text-5xl">
        Was möchtest du bauen oder reparieren?
      </h1>
      <p className="mx-auto mt-3 max-w-xl text-center text-lg text-muted text-balance">
        Beschreib es in einem Satz. Du bekommst 3D-Modell, Zeichnungen, Materialliste, Kosten und
        eine Bauanleitung.
      </p>

      <div className="mt-8">
        <ProjectBrief brief={brief} onChange={onBriefChange} onSubmit={onSubmit} busy={busy} />
        <p
          role="note"
          className="mt-3 flex items-start justify-center gap-1.5 text-center text-xs text-muted"
          data-testid="ai-disclosure"
        >
          <Icon name="sparkles" className="mt-px h-3.5 w-3.5 text-ai" />
          <span>
            Du sprichst mit einem KI-Assistenten. Maße, Mengen, Kosten und Zeichnungen berechnet
            Homeworking regelbasiert; die KI formuliert Fragen und Erklärungen.
          </span>
        </p>
      </div>

      <section aria-labelledby="ideas-heading" className="mt-10">
        <h2
          id="ideas-heading"
          className="mb-3 text-center text-sm font-semibold uppercase tracking-wide text-muted"
        >
          Oder starte mit einer Idee
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {IDEAS.map((idea) => (
            <IdeaCard
              key={idea.key}
              idea={idea}
              onPick={() => {
                onBriefChange({ ...EMPTY_BRIEF, ...idea.brief });
                document.getElementById("brief-description")?.focus();
              }}
            />
          ))}
        </div>
      </section>

      <RecentProjects />

      <section aria-labelledby="how-heading" className="mt-14">
        <h2 id="how-heading" className="sr-only">
          So funktioniert&apos;s
        </h2>
        <ol className="grid gap-4 sm:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step.title} className="flex gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-surface-muted text-accent-strong">
                <Icon name={step.icon} />
              </span>
              <span>
                <span className="block font-semibold">
                  <span className="text-muted">{index + 1}. </span>
                  {step.title}
                </span>
                <span className="block text-sm text-muted">{step.text}</span>
              </span>
            </li>
          ))}
        </ol>
        <p className="mt-6 text-center text-xs text-muted">
          Tragende Bauwerke (Carport, Dach, Balkon) plant Homeworking nicht. Freie Entwürfe brauchen
          ein angebundenes Sprachmodell.
        </p>
      </section>
    </div>
  );
}
