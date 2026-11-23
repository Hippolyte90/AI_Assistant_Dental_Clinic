import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Answer, Question, QuestionOption } from "../types";
import { CheckIcon, RefreshIcon, SpeakerIcon } from "./icons";
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
  if (value === 0) return "Same price";
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
  const optional = questions.filter((question) => !question.blocking);
  const answeredBlocking = blocking.filter((question) =>
    answers.some((answer) => answer.question_id === question.id),
  ).length;
  const canConfirm = !busy && !hasChanges && (blocking.length === 0 || acceptDefaults);

  function renderQuestion(question: Question) {
    const current = draft[question.id] ?? {};
    const answered = answers.some((answer) => answer.question_id === question.id);
    return (
      <fieldset
        className={answered ? "question answered" : "question"}
        key={question.id}
        disabled={busy}
      >
        <legend>{question.text}</legend>
        <div className="options">
          {question.options.map((option) => {
            const selected = current.option_id === option.id;
            return (
              <button
                type="button"
                key={option.id}
                aria-pressed={selected}
                className={selected ? "option on" : "option"}
                onClick={() => setDraft({ ...draft, [question.id]: { option_id: option.id } })}
              >
                <span>{option.label}</span>
                {delta(option) && <small>{delta(option)}</small>}
              </button>
            );
          })}
        </div>
        {question.allow_free_text && (
          <div className="free">
            <input
              aria-label={`Other answer: ${question.text}`}
              placeholder="Other answer"
              value={current.free_text ?? ""}
              onChange={(event) =>
                setDraft({ ...draft, [question.id]: { free_text: event.target.value } })
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
  }

  return (
    <section className="card questions" aria-label="Questions for the dentist">
      <div className="card-head">
        <div>
          <h2>{blocking.length ? "A few details needed" : "Review and confirm"}</h2>
          <p className="muted">
            {blocking.length
              ? `${answeredBlocking} of ${blocking.length} answered`
              : "All required details are complete."}
          </p>
        </div>
        {questions.length > 0 && "speechSynthesis" in window && (
          <label className={speak ? "toggle on" : "toggle"}>
            <input
              type="checkbox"
              checked={speak}
              onChange={(event) => setSpeak(event.target.checked)}
            />
            <SpeakerIcon size={15} /> Read aloud
          </label>
        )}
      </div>

      {blocking.length > 0 && (
        <div
          className="progress-track"
          role="progressbar"
          aria-label="Questions answered"
          aria-valuemin={0}
          aria-valuemax={blocking.length}
          aria-valuenow={answeredBlocking}
        >
          <span style={{ width: `${(answeredBlocking / blocking.length) * 100}%` }} />
        </div>
      )}

      {blocking.map(renderQuestion)}

      {optional.length > 0 && (
        <details className="group">
          <summary>Waiting times to confirm ({optional.length})</summary>
          <div className="group-body">{optional.map(renderQuestion)}</div>
        </details>
      )}

      <label className="field">
        <span>Other changes</span>
        <div className="free">
          <textarea
            rows={2}
            value={corrections}
            disabled={busy}
            onChange={(event) => setCorrections(event.target.value)}
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

      <div className="action-bar">
        {blocking.length > 0 && !hasChanges && (
          <label className="check">
            <input
              type="checkbox"
              checked={acceptDefaults}
              disabled={busy}
              onChange={(event) => setAcceptDefaults(event.target.checked)}
            />
            Accept the provisional choices for the {blocking.length} unanswered question
            {blocking.length > 1 ? "s" : ""}
          </label>
        )}
        {hasChanges && <p className="muted">Update the plan before confirming.</p>}
        <div className="actions">
          <button
            type="button"
            className="secondary grow"
            disabled={busy || !hasChanges}
            onClick={() => onApply(answers, corrections)}
          >
            <RefreshIcon size={16} /> Update plan
          </button>
          <button
            type="button"
            className="grow"
            disabled={!canConfirm}
            onClick={() => onConfirm(acceptDefaults)}
          >
            <CheckIcon size={16} /> Confirm plan
          </button>
        </div>
      </div>
    </section>
  );
}
