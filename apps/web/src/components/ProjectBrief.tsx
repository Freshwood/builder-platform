"use client";

import clsx from "clsx";
import { useId, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";

import {
  BRIEF_FIELDS,
  EMPTY_BRIEF,
  EXPERIENCE,
  FINISHES,
  LOCATIONS,
  MOUNTINGS,
  SIZE_MODES,
  TOOLS,
  WOODS,
  briefCompleteness,
  briefMessage,
  type Brief,
  type Option,
} from "@/lib/brief";
import { AutoTextarea } from "@/components/AutoTextarea";

const EXAMPLES: { label: string; brief: Partial<Brief> }[] = [
  {
    label: "Hochbeet",
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
    label: "Bücherregal",
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
    label: "Gartenbank",
    brief: {
      description: "Eine Gartenbank 1,6 m lang mit Rückenlehne.",
      location: "outdoor",
      wood: "larch",
      finish: "oil",
    },
  },
  {
    label: "Fensterläden",
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
];

function Chips({
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
      <legend className="mb-1.5 text-sm font-medium">
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
              "rounded-full border px-3 py-1 text-sm transition-colors",
              selected(option.value)
                ? "border-accent bg-accent-soft font-medium text-accent-strong"
                : "border-border bg-surface hover:bg-surface-muted",
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

const inputClass =
  "w-full rounded-lg border border-border bg-surface px-3 py-2 text-base placeholder:text-muted/70";

function NumberInput({
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
    <Field label={label}>
      <span className="relative block">
        <input
          inputMode="decimal"
          value={value}
          onChange={(event) => onChange(event.target.value.replace(/[^\d.,]/g, ""))}
          className={clsx(inputClass, "pr-10")}
        />
        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-muted">
          {unit}
        </span>
      </span>
    </Field>
  );
}

export function ProjectBrief({
  onSubmit,
  busy,
}: {
  onSubmit: (message: string) => boolean;
  busy: boolean;
}) {
  const [brief, setBrief] = useState<Brief>(EMPTY_BRIEF);
  const detailsId = useId();
  const filled = briefCompleteness(brief);
  const canSend = brief.description.trim().length > 0 && !busy;

  function set<K extends keyof Brief>(key: K, value: Brief[K]) {
    setBrief((current) => ({ ...current, [key]: value }));
  }

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!canSend) return;
    if (onSubmit(briefMessage(brief))) setBrief(EMPTY_BRIEF);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-2xl border border-border bg-surface p-4 shadow-sm sm:p-6"
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
        minRows={4}
        autoFocus
        placeholder={
          "Beschreibe dein Vorhaben in eigenen Worten, z. B.:\n" +
          "„Ein Kräuterregal für den Balkon mit drei schrägen Ebenen, " +
          "passend in eine Nische von 90 cm.“"
        }
        className="w-full resize-none rounded-xl border border-border bg-surface-muted/40 px-4 py-3 text-lg leading-relaxed placeholder:text-base placeholder:text-muted/80"
      />
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">Beispiel übernehmen:</span>
        {EXAMPLES.map((example) => (
          <button
            key={example.label}
            type="button"
            onClick={() => setBrief({ ...EMPTY_BRIEF, ...example.brief })}
            className="rounded-full border border-border px-3 py-0.5 hover:bg-surface-muted"
          >
            {example.label}
          </button>
        ))}
      </div>

      <section aria-labelledby={detailsId} className="mt-6 border-t border-border pt-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id={detailsId} className="font-semibold">
              Details zu deinem Vorhaben
            </h2>
            <p className="text-sm text-muted">
              Alles optional – je mehr du angibst, desto besser passt die Planung und desto weniger
              muss der Assistent nachfragen.
            </p>
          </div>
          <div className="min-w-40 text-sm" aria-live="polite">
            <span className="text-muted">
              {filled} von {BRIEF_FIELDS} Angaben
            </span>
            <div
              className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-muted"
              role="presentation"
            >
              <div
                className="h-full rounded-full bg-accent transition-all"
                style={{ width: `${(filled / BRIEF_FIELDS) * 100}%` }}
              />
            </div>
          </div>
        </div>

        <div className="mt-4 grid gap-5 md:grid-cols-2">
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
          <div className="md:col-span-2">
            <p className="mb-1.5 text-sm font-medium">Maße</p>
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
            <div className="mt-2">
              <Chips
                legend="Die Maße sind …"
                options={SIZE_MODES}
                value={brief.sizeMode}
                onChange={(v) => set("sizeMode", (v as string) || "approx")}
              />
            </div>
          </div>
          <div className="md:col-span-2">
            <Chips
              legend="Material / Holzart"
              options={WOODS}
              value={brief.wood}
              onChange={(v) => set("wood", v as string)}
            />
          </div>
          <Chips
            legend="Oberfläche"
            options={FINISHES}
            value={brief.finish}
            onChange={(v) => set("finish", v as string)}
          />
          <Chips
            legend="Deine Erfahrung"
            options={EXPERIENCE}
            value={brief.experience}
            onChange={(v) => set("experience", v as string)}
          />
          <div className="md:col-span-2">
            <Chips
              legend="Welches Werkzeug hast du?"
              options={TOOLS}
              value={brief.tools}
              onChange={(v) => set("tools", v as string[])}
              multiple
            />
          </div>
          <div className="sm:max-w-48">
            <NumberInput
              label="Budget für Material"
              unit="€"
              value={brief.budget}
              onChange={(v) => set("budget", v)}
            />
          </div>
          <div className="md:col-span-2">
            <Field
              label="Nutzung, Belastung und besondere Wünsche"
              hint="Was soll darauf oder darin? Türen, Schubladen, Rollen? Wie viel Platz ist da?"
            >
              <AutoTextarea
                value={brief.usage}
                onChange={(value) => set("usage", value)}
                onKeyDown={onKeyDown}
                minRows={2}
                placeholder="z. B. für Werkzeugkisten bis 40 kg, mit abschließbarer Tür"
                className={clsx(inputClass, "resize-none")}
              />
            </Field>
          </div>
        </div>
      </section>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-muted">
          Strg + Enter sendet. Freie Entwürfe dauern je nach Sprachmodell bis zu einigen Minuten –
          du siehst dabei live, woran gerade gearbeitet wird.
        </p>
        <button
          type="submit"
          disabled={!canSend}
          className="rounded-xl bg-accent px-6 py-2.5 font-semibold text-white shadow-sm disabled:opacity-50 dark:text-black"
        >
          Planung starten
        </button>
      </div>
    </form>
  );
}
