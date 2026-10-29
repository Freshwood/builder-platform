"use client";

import clsx from "clsx";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import { AutoTextarea } from "@/components/AutoTextarea";
import { Chips, NumberInput, inputClass } from "@/components/BriefControls";
import { IntakeQuestions } from "@/components/IntakeQuestions";
import { Icon, type IconName } from "@/components/ui";
import {
  EMPTY_BRIEF,
  EXPERIENCE,
  FINISHES,
  LOCATIONS,
  MOUNTINGS,
  SIZE_MODES,
  TOOLS,
  WOODS,
  briefMessage,
  sizeText,
  type Brief,
  type Option,
} from "@/lib/brief";
import { askIntake, type Intake } from "@/lib/intake";
import type { Question } from "@/api";

/** Optional details as pills; each one opens a small panel below the prompt. */
type DetailKey = "place" | "size" | "wood" | "finish" | "budget" | "skills" | "usage";

const DETAILS: { key: DetailKey; label: string; icon: IconName }[] = [
  { key: "place", label: "Ort & Montage", icon: "location" },
  { key: "size", label: "Maße", icon: "ruler" },
  { key: "wood", label: "Holzart", icon: "tree" },
  { key: "finish", label: "Oberfläche", icon: "brush" },
  { key: "budget", label: "Budget", icon: "wallet" },
  { key: "skills", label: "Erfahrung & Werkzeug", icon: "toolbox" },
  { key: "usage", label: "Wünsche", icon: "lightbulb" },
];

function label(options: Option[], value: string): string | undefined {
  return options.find((o) => o.value === value)?.label;
}

/** Short summary of a detail for its pill, or undefined when nothing is set. */
function detailValue(brief: Brief, key: DetailKey): string | undefined {
  switch (key) {
    case "place":
      return (
        [label(LOCATIONS, brief.location), label(MOUNTINGS, brief.mounting)]
          .filter(Boolean)
          .join(", ") || undefined
      );
    case "size":
      return sizeText(brief)?.replace(" (Breite × Tiefe)", "");
    case "wood":
      return label(WOODS, brief.wood);
    case "finish":
      return label(FINISHES, brief.finish);
    case "budget":
      return brief.budget.trim() ? `bis ${brief.budget.trim()} €` : undefined;
    case "skills": {
      const parts = [label(EXPERIENCE, brief.experience)];
      if (brief.tools.length) parts.push(`${brief.tools.length} Werkzeuge`);
      return parts.filter(Boolean).join(", ") || undefined;
    }
    case "usage":
      return brief.usage.trim() ? brief.usage.trim().slice(0, 28) + "…" : undefined;
  }
}

function clearDetail(brief: Brief, key: DetailKey): Brief {
  const reset: Record<DetailKey, Partial<Brief>> = {
    place: { location: "", mounting: "" },
    size: { width: "", depth: "", height: "", sizeMode: "approx" },
    wood: { wood: "" },
    finish: { finish: "" },
    budget: { budget: "" },
    skills: { experience: "", tools: [] },
    usage: { usage: "" },
  };
  return { ...brief, ...reset[key] };
}

function DetailPanel({
  detail,
  brief,
  set,
  onKeyDown,
}: {
  detail: DetailKey;
  brief: Brief;
  set: <K extends keyof Brief>(key: K, value: Brief[K]) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
}) {
  const panels: Record<DetailKey, ReactNode> = {
    place: (
      <div className="grid gap-4 sm:grid-cols-2">
        <Chips
          legend="Wo wird es genutzt?"
          options={LOCATIONS}
          value={brief.location}
          onChange={(v) => set("location", v as string)}
        />
        <Chips
          legend="Wie wird es aufgestellt?"
          options={MOUNTINGS}
          value={brief.mounting}
          onChange={(v) => set("mounting", v as string)}
        />
      </div>
    ),
    size: (
      <div className="space-y-3">
        <div className="grid grid-cols-3 gap-2 sm:max-w-md">
          <NumberInput
            label="Breite / Länge"
            unit="cm"
            value={brief.width}
            onChange={(v) => set("width", v)}
          />
          <NumberInput
            label="Tiefe"
            unit="cm"
            value={brief.depth}
            onChange={(v) => set("depth", v)}
          />
          <NumberInput
            label="Höhe"
            unit="cm"
            value={brief.height}
            onChange={(v) => set("height", v)}
          />
        </div>
        <Chips
          legend="Die Maße sind …"
          options={SIZE_MODES}
          value={brief.sizeMode}
          onChange={(v) => set("sizeMode", (v as string) || "approx")}
        />
      </div>
    ),
    wood: (
      <Chips
        legend="Material / Holzart"
        options={WOODS}
        value={brief.wood}
        onChange={(v) => set("wood", v as string)}
      />
    ),
    finish: (
      <Chips
        legend="Oberfläche"
        options={FINISHES}
        value={brief.finish}
        onChange={(v) => set("finish", v as string)}
      />
    ),
    budget: (
      <div className="sm:max-w-48">
        <NumberInput
          label="Budget für Material"
          unit="€"
          value={brief.budget}
          onChange={(v) => set("budget", v)}
        />
      </div>
    ),
    skills: (
      <div className="space-y-4">
        <Chips
          legend="Deine Erfahrung"
          options={EXPERIENCE}
          value={brief.experience}
          onChange={(v) => set("experience", v as string)}
        />
        <Chips
          legend="Welches Werkzeug hast du?"
          options={TOOLS}
          value={brief.tools}
          onChange={(v) => set("tools", v as string[])}
          multiple
        />
      </div>
    ),
    usage: (
      <label className="block text-sm">
        <span className="mb-1 block font-medium">Nutzung, Belastung und besondere Wünsche</span>
        <AutoTextarea
          value={brief.usage}
          onChange={(value) => set("usage", value)}
          onKeyDown={onKeyDown}
          minRows={2}
          placeholder="z. B. für Werkzeugkisten bis 40 kg, mit abschließbarer Tür"
          className={clsx(inputClass, "resize-none")}
        />
      </label>
    ),
  };
  return <>{panels[detail]}</>;
}

/** The landing prompt: one big text box, optional details as pills (progressive disclosure). */
export function ProjectBrief({
  brief,
  onChange,
  onSubmit,
  busy,
}: {
  brief: Brief;
  onChange: (brief: Brief) => void;
  onSubmit: (message: string) => boolean;
  busy: boolean;
}) {
  const [open, setOpen] = useState<DetailKey | null>(null);
  // Open questions of the intake step; null = not asked (yet).
  const [asking, setAsking] = useState<Question[] | null>(null);
  const [checking, setChecking] = useState(false);
  // Number of the latest intake check. An edit (or leaving the form) bumps it, which makes the
  // answer of a check still in flight obsolete: it belongs to a brief that no longer exists.
  const latestCheck = useRef(0);
  const canSend = brief.description.trim().length > 0 && !busy && !checking;

  useEffect(
    () => () => {
      latestCheck.current += 1;
    },
    [],
  );

  /** Every edit of the brief goes through here so that it cancels a pending intake check. */
  function change(next: Brief) {
    latestCheck.current += 1;
    setChecking(false);
    onChange(next);
  }

  function set<K extends keyof Brief>(key: K, value: Brief[K]) {
    // A new description invalidates the questions asked about the old one.
    if (key === "description") setAsking(null);
    change({ ...brief, [key]: value });
  }

  function send(final: Brief) {
    if (onSubmit(briefMessage(final))) {
      onChange(EMPTY_BRIEF);
      setOpen(null);
      setAsking(null);
    }
  }

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!canSend) return;
    // Second round (questions shown): the start button continues with what is filled in.
    if (asking) return send(brief);
    const check = ++latestCheck.current;
    setChecking(true);
    let result: Intake;
    try {
      result = await askIntake(brief);
    } finally {
      if (check === latestCheck.current) setChecking(false);
    }
    // Edited in the meantime: the questions and the filled-in facts would overwrite newer input.
    if (check !== latestCheck.current) return;
    if (!result.questions.length) return send(result.brief);
    onChange(result.brief);
    setAsking(result.questions);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends like in every chat; Shift+Enter starts a new line.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  const openDetail = DETAILS.find((d) => d.key === open);

  return (
    <form
      onSubmit={submit}
      className="group rounded-xl border border-border bg-surface p-2 transition focus-within:border-text focus-within:ring-1 focus-within:ring-text"
      data-testid="project-brief"
    >
      <label htmlFor="brief-description" className="sr-only">
        Was möchtest du bauen oder reparieren?
      </label>
      <AutoTextarea
        id="brief-description"
        value={brief.description}
        onChange={(value) => set("description", value)}
        onKeyDown={onKeyDown}
        minRows={3}
        maxRows={10}
        autoFocus
        placeholder="z. B. „Ein Kräuterregal für den Balkon mit drei schrägen Ebenen, passend in eine Nische von 90 cm.“"
        className="w-full resize-none bg-transparent px-4 pt-3 text-lg leading-relaxed placeholder:text-muted/70 focus:outline-none"
      />

      <div className="px-2">
        <ul className="flex flex-wrap gap-1.5" aria-label="Details (optional)">
          {DETAILS.map((detail) => {
            const value = detailValue(brief, detail.key);
            const active = open === detail.key;
            return (
              <li
                key={detail.key}
                className={clsx(
                  "inline-flex items-center rounded-full border text-sm transition",
                  value
                    ? "border-text/50 bg-accent-soft"
                    : active
                      ? "border-text/30 bg-surface-muted"
                      : "border-dashed border-border text-muted hover:border-muted/60 hover:text-text",
                )}
              >
                <button
                  type="button"
                  aria-expanded={active}
                  aria-controls="brief-detail"
                  onClick={() => setOpen(active ? null : detail.key)}
                  className={clsx(
                    "inline-flex items-center gap-1.5 rounded-full py-1 pl-2.5",
                    value ? "pr-1" : "pr-3",
                  )}
                >
                  <Icon name={detail.icon} className="h-4 w-4" />
                  <span>{value ?? detail.label}</span>
                  {!value && <span className="sr-only"> hinzufügen</span>}
                </button>
                {value && (
                  <button
                    type="button"
                    onClick={() => change(clearDetail(brief, detail.key))}
                    className="mr-1 rounded-full p-0.5 hover:bg-accent/15"
                    aria-label={`${detail.label} entfernen`}
                  >
                    <Icon name="close" className="h-3.5 w-3.5" />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      <div className="mt-2 flex items-center justify-between gap-3 border-t border-border/70 px-2 pt-2">
        <span className="hidden text-xs text-muted sm:block">
          Details sind optional. Enter startet, Umschalt + Enter macht eine neue Zeile.
        </span>
        <button
          type="submit"
          disabled={!canSend}
          aria-busy={checking}
          className="ml-auto inline-flex h-11 items-center gap-2 rounded-md bg-accent px-5 font-semibold text-on-accent transition hover:brightness-105 active:scale-[0.97] disabled:opacity-35"
        >
          Planung starten
        </button>
      </div>

      {asking && (
        <IntakeQuestions
          questions={asking}
          brief={brief}
          onChange={change}
          onContinue={() => send(brief)}
        />
      )}

      {openDetail && (
        <div
          id="brief-detail"
          role="region"
          aria-label={openDetail.label}
          className="m-2 mt-3 animate-fadein rounded-lg border border-border bg-surface-muted/60 p-4"
        >
          <DetailPanel detail={openDetail.key} brief={brief} set={set} onKeyDown={onKeyDown} />
          <div className="mt-4 flex justify-end">
            <button
              type="button"
              onClick={() => setOpen(null)}
              className="rounded-lg px-3 py-1 text-sm font-medium text-muted hover:bg-surface hover:text-text"
            >
              Fertig
            </button>
          </div>
        </div>
      )}
    </form>
  );
}
