import { useEffect, useState } from "react";
import { api } from "../api/client";
import { PdfViewer } from "../components/PdfViewer";
import { PlanView } from "../components/PlanView";
import { QuestionsPanel } from "../components/QuestionsPanel";
import { Recorder } from "../components/Recorder";
import { TranscriptEditor } from "../components/TranscriptEditor";
import { VersionDiff } from "../components/VersionDiff";
import type { Answer, Health, PlanDiff, TreatmentPlan } from "../types";

const STEP_LABELS: Record<string, string> = {
  queued: "Waiting…",
  starting: "Starting…",
  transcribe: "Transcribing the dictation…",
  extract: "Reading the dictation (local AI)…",
  match: "Matching services to the price list…",
  apply: "Applying your answers…",
  revise: "Applying your corrections (local AI)…",
  price: "Calculating prices…",
  pdf: "Generating the PDF…",
};

export function SessionPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [patient, setPatient] = useState("");
  const [transcript, setTranscript] = useState("");
  const [plans, setPlans] = useState<TreatmentPlan[]>([]);
  const [selectedVersion, setSelectedVersion] = useState(0);
  const [diff, setDiff] = useState<PlanDiff | null>(null);
  const [step, setStep] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  const busy = step !== "";
  const latest = plans[plans.length - 1];
  const selected = plans.find((plan) => plan.version === selectedVersion) ?? latest;
  const isFinal = latest?.status === "FINAL";

  async function run(first: string, work: () => Promise<void>) {
    setError("");
    setStep(first);
    try {
      await work();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setStep("");
    }
  }

  async function ensureSession(): Promise<string> {
    if (sessionId) return sessionId;
    const session = await api.createSession(patient);
    setSessionId(session.id);
    return session.id;
  }

  async function refresh(id: string, version: number) {
    setPlans(await api.listPlans(id));
    setSelectedVersion(version);
  }

  const onRecorded = (audio: Blob) =>
    run("transcribe", async () => {
      const id = await ensureSession();
      const result = await api.uploadAudio(id, audio);
      if (!result.text) throw new Error("No speech was detected. Please record again.");
      const text = `${transcript} ${result.text}`.trim();
      setTranscript(text);
      await api.saveTranscript(id, text);
    });

  const build = () =>
    run("starting", async () => {
      const id = await ensureSession();
      await api.saveTranscript(id, transcript);
      const result = await api.buildPlan(id, setStep);
      setDiff(null);
      await refresh(id, result.plan.version);
    });

  const apply = (answers: Answer[], corrections: string) =>
    run("starting", async () => {
      const result = await api.revisePlan(sessionId, answers, corrections, setStep);
      setDiff(result.diff);
      await refresh(sessionId, result.plan.version);
    });

  const confirm = (acceptDefaults: boolean) =>
    run("pdf", async () => {
      const final = await api.confirmPlan(sessionId, acceptDefaults);
      setDiff(null);
      await refresh(sessionId, final.version);
    });

  const reset = () =>
    run("starting", async () => {
      if (sessionId) await api.deleteSession(sessionId);
      setSessionId("");
      setPatient("");
      setTranscript("");
      setPlans([]);
      setSelectedVersion(0);
      setDiff(null);
    });

  const llmProblem = health && health.llm !== "ok";

  return (
    <div className="app">
      <header>
        <div>
          <h1>{health?.clinic_name ?? "Dental Clinic"}</h1>
          <p>Treatment plan assistant · runs entirely on this computer</p>
        </div>
        <span className={health && !llmProblem ? "badge ok" : "badge bad"}>
          {!health ? "Server offline" : llmProblem ? `AI: ${health.llm}` : `AI ready · ${health.model}`}
        </span>
      </header>

      {health && !health.rules_validated && (
        <p className="banner">
          Default intervals have not been validated by a dentist. They are shown as assumptions.
        </p>
      )}
      {error && (
        <p className="banner error" role="alert">
          {error}
        </p>
      )}
      {busy && (
        <p className="banner progress" role="status">
          <span className="spinner" aria-hidden /> {STEP_LABELS[step] ?? "Working…"}
        </p>
      )}

      <main>
        <div className="column">
          <section className="card">
            <h2>1. Dictation</h2>
            <label className="field">
              <span>Patient reference (optional)</span>
              <input
                value={patient}
                maxLength={80}
                disabled={Boolean(sessionId)}
                onChange={(event) => setPatient(event.target.value)}
                placeholder="e.g. P-1042"
              />
            </label>
            <Recorder onRecorded={onRecorded} disabled={busy || isFinal} />
            <TranscriptEditor value={transcript} onChange={setTranscript} disabled={busy || isFinal} />
            <div className="actions">
              <button type="button" disabled={busy || isFinal || !transcript.trim()} onClick={build}>
                {plans.length ? "Rebuild plan from dictation" : "Build treatment plan"}
              </button>
              <button type="button" className="secondary" disabled={busy} onClick={reset}>
                {sessionId ? "Delete and start over" : "Clear"}
              </button>
            </div>
          </section>

          {latest && !isFinal && (
            <section className="card">
              <QuestionsPanel
                questions={latest.questions}
                busy={busy}
                onApply={apply}
                onConfirm={confirm}
                onError={setError}
              />
            </section>
          )}
          {isFinal && (
            <section className="card done">
              <h2>Plan confirmed</h2>
              <p>Version {latest.version} is final. Download the PDF for signature.</p>
            </section>
          )}
        </div>

        <div className="column">
          {!selected && (
            <section className="card empty">
              <h2>2. Treatment plan</h2>
              <p className="muted">
                Dictate or paste the notes, then build the plan. Stages, intervals, prices and the
                PDF will appear here.
              </p>
            </section>
          )}
          {selected && (
            <>
              {diff && selected.version === latest.version && <VersionDiff diff={diff} />}
              <section className="card">
                <div className="section-head">
                  <h2>2. Treatment plan · v{selected.version}</h2>
                  <span className={selected.status === "FINAL" ? "badge ok" : "badge draft"}>
                    {selected.status}
                  </span>
                </div>
                <PlanView plan={selected} />
              </section>
              <section className="card">
                <h2>3. PDF</h2>
                <PdfViewer plans={plans} selected={selected} onSelect={setSelectedVersion} />
              </section>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
