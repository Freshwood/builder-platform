"use client";

import type { Question } from "@/api";

import { Chips, NumberInput } from "@/components/BriefControls";
import { ANSWER_FIELD } from "@/lib/intake";
import type { Brief, Option } from "@/lib/brief";

/** True when the customer already gave the answer to ``question`` (in the brief form). */
export function isAnswered(question: Question, brief: Brief): boolean {
  if (question.field === "size") return Boolean(brief.width || brief.depth || brief.height);
  const key = ANSWER_FIELD[question.field];
  return Boolean(key && brief[key]);
}

/**
 * The few questions the engine still sees open. Answers are written straight into the brief, so
 * "Weiter" and the brief form's own start button do the same thing.
 */
export function IntakeQuestions({
  questions,
  brief,
  onChange,
  onContinue,
}: {
  questions: Question[];
  brief: Brief;
  onChange: (brief: Brief) => void;
  onContinue: () => void;
}) {
  const answered = questions.some((q) => isAnswered(q, brief));
  return (
    <section
      aria-label="Rückfragen"
      data-testid="intake-questions"
      className="m-2 mt-3 animate-fadein rounded-lg border border-border bg-surface-muted/60 p-4"
    >
      <h2 className="mb-3 text-base font-semibold">Noch ein paar kurze Fragen</h2>
      <div className="space-y-4">
        {questions.map((question) => {
          if (question.field === "size") {
            return (
              <fieldset key={question.field}>
                <legend className="mb-2 text-sm font-medium">{question.text}</legend>
                <div className="grid grid-cols-3 gap-3">
                  <NumberInput
                    label="Breite"
                    unit="cm"
                    value={brief.width}
                    onChange={(width) => onChange({ ...brief, width })}
                  />
                  <NumberInput
                    label="Tiefe"
                    unit="cm"
                    value={brief.depth}
                    onChange={(depth) => onChange({ ...brief, depth })}
                  />
                  <NumberInput
                    label="Höhe"
                    unit="cm"
                    value={brief.height}
                    onChange={(height) => onChange({ ...brief, height })}
                  />
                </div>
              </fieldset>
            );
          }
          const key = ANSWER_FIELD[question.field];
          if (!key || !question.options?.length) return null;
          const options: Option[] = question.options.map((o) => ({
            value: o.value,
            label: o.label,
            text: o.label,
          }));
          return (
            <Chips
              key={question.field}
              legend={question.text}
              options={options}
              value={String(brief[key] ?? "")}
              onChange={(value) => onChange({ ...brief, [key]: value as string })}
            />
          );
        })}
      </div>
      <div className="mt-4 flex items-center justify-between gap-3">
        <p className="text-xs text-muted">
          Du kannst auch ohne Antwort weitermachen, dann nehme ich sinnvolle Annahmen.
        </p>
        <button
          type="button"
          onClick={onContinue}
          className="rounded-md border border-text bg-surface px-4 py-2 text-sm font-semibold transition hover:bg-accent-soft"
        >
          {answered ? "Weiter" : "Weiter mit Annahmen"}
        </button>
      </div>
    </section>
  );
}
