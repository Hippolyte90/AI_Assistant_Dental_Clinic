import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Answer, Question, QuestionOption } from "../types";
import { eur } from "./PlanView";
import { Recorder } from "./Recorder";

interface Props {
  questions: Question[];
  busy: boolean;
  onApply: (answers: Answer[], corrections: string) => void;
  onConfirm: (acceptDefaults: boolean) => void;
  onError: (message: string) => void;
}

type Draft = Record<string, { option_id?: string; free_text?: string }>;

function delta(option: QuestionOption): string {
  if (option.price_delta_eur === null) return "";
  const value = Number(option.price_delta_eur);
  if (value === 0) return "no price change";
  return `${value > 0 ? "+" : "−"}${eur(Math.abs(value))}`;
}

export function QuestionsPanel({ questions, busy, onApply, onConfirm, onError }: Props) {
  const [draft, setDraft] = useState<Draft>({});
  const [corrections, setCorrections] = useState("");
  const [acceptDefaults, setAcceptDefaults] = useState(false);
  const [speak, setSpeak] = useState(false);
  const [listening, setListening] = useState(false);

  const questionKey = questions.map((question) => question.id).join("|");
  useEffect(() => {
    setDraft({});
    setCorrections("");
    setAcceptDefaults(false);
  }, [questionKey]);

  useEffect(() => {
    if (!speak || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    questions.forEach((question) => {
      const utterance = new SpeechSynthesisUtterance(question.text);
      utterance.lang = "en-US";
      window.speechSynthesis.speak(utterance);
    });
    return () => window.speechSynthesis.cancel();
  }, [speak, questionKey]); // eslint-disable-line react-hooks/exhaustive-deps

  async function voice(audio: Blob, apply: (text: string) => void) {
    setListening(true);
    try {
      apply((await api.transcribe(audio)).text);
    } catch (error) {
      onError((error as Error).message);
    } finally {
      setListening(false);
    }
  }

  const answers: Answer[] = Object.entries(draft)
    .filter(([, value]) => value.option_id || value.free_text?.trim())
    .map(([question_id, value]) => ({
      question_id,
      option_id: value.free_text?.trim() ? undefined : value.option_id,
      free_text: value.free_text?.trim() || undefined,
    }));
  const hasChanges = answers.length > 0 || corrections.trim().length > 0;
  const blocking = questions.filter((question) => question.blocking);
  const canConfirm = !busy && !hasChanges && (blocking.length === 0 || acceptDefaults);

  return (
    <section className="questions" aria-label="Questions for the dentist">
      <div className="section-head">
        <h2>{questions.length ? `Questions (${questions.length})` : "No open questions"}</h2>
        {questions.length > 0 && "speechSynthesis" in window && (
          <label className="check">
            <input type="checkbox" checked={speak} onChange={(e) => setSpeak(e.target.checked)} />
            Read aloud
          </label>
        )}
      </div>

      {questions.map((question) => {
        const current = draft[question.id] ?? {};
        return (
          <fieldset className="question" key={question.id} disabled={busy}>
            <legend>
              {question.text}
              {!question.blocking && <span className="tag">optional</span>}
            </legend>
            <div className="options">
              {question.options.map((option) => (
                <button
                  type="button"
                  key={option.id}
                  aria-pressed={current.option_id === option.id}
                  className={current.option_id === option.id ? "option on" : "option"}
                  onClick={() =>
                    setDraft({ ...draft, [question.id]: { option_id: option.id } })
                  }
                >
                  {option.label}
                  {delta(option) && <small>{delta(option)}</small>}
                </button>
              ))}
            </div>
            {question.allow_free_text && (
              <div className="free">
                <input
                  aria-label={`Other answer: ${question.text}`}
                  placeholder="Or type an answer"
                  value={current.free_text ?? ""}
                  onChange={(e) =>
                    setDraft({ ...draft, [question.id]: { free_text: e.target.value } })
                  }
                />
                <Recorder
                  compact
                  disabled={busy || listening}
                  onRecorded={(audio) =>
                    void voice(audio, (text) =>
                      setDraft((old) => ({ ...old, [question.id]: { free_text: text } })),
                    )
                  }
                />
              </div>
            )}
          </fieldset>
        );
      })}

      <label className="field">
        <span>Other corrections</span>
        <div className="free">
          <textarea
            rows={2}
            value={corrections}
            disabled={busy}
            onChange={(e) => setCorrections(e.target.value)}
            placeholder="e.g. Remove the radiograph and add a filling on 21"
          />
          <Recorder
            compact
            disabled={busy || listening}
            onRecorded={(audio) =>
              void voice(audio, (text) => setCorrections((old) => `${old} ${text}`.trim()))
            }
          />
        </div>
      </label>
      {listening && <p className="muted">Transcribing your answer…</p>}

      <div className="actions">
        <button type="button" disabled={busy || !hasChanges} onClick={() => onApply(answers, corrections)}>
          Apply and regenerate PDF
        </button>
        <button
          type="button"
          className="confirm"
          disabled={!canConfirm}
          onClick={() => onConfirm(acceptDefaults)}
        >
          Confirm final plan
        </button>
      </div>
      {hasChanges && <p className="muted">Apply your changes before confirming.</p>}
      {blocking.length > 0 && (
        <label className="check">
          <input
            type="checkbox"
            checked={acceptDefaults}
            disabled={busy}
            onChange={(e) => setAcceptDefaults(e.target.checked)}
          />
          Accept the provisional choices for the {blocking.length} unanswered question(s)
        </label>
      )}
    </section>
  );
}
