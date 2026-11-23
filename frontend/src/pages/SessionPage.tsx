import { useEffect, useState } from "react";
import { api } from "../api/client";
import {
  AlertIcon,
  CheckIcon,
  ChevronIcon,
  DocumentIcon,
  DownloadIcon,
  ListIcon,
  PlusIcon,
  TrashIcon,
} from "../components/icons";
import { Logo, LogoMark } from "../components/Logo";
import { MyPlansPage } from "./MyPlansPage";
import { PdfViewer } from "../components/PdfViewer";
import { PlanView } from "../components/PlanView";
import { QuestionsPanel } from "../components/QuestionsPanel";
import { Recorder } from "../components/Recorder";
import { Stepper } from "../components/Stepper";
import { TranscriptEditor } from "../components/TranscriptEditor";
import { VersionDiff } from "../components/VersionDiff";
import type { Answer, Health, PlanDiff, TreatmentPlan } from "../types";

const STEP_LABELS: Record<string, string> = {
  queued: "Getting ready…",
  starting: "Getting ready…",
  transcribe: "Transcribing your dictation…",
  extract: "Reading the clinical notes…",
  match: "Matching services to the price list…",
  apply: "Applying your answers…",
  revise: "Applying your changes…",
  price: "Calculating prices…",
  pdf: "Preparing the document…",
};

export function SessionPage({
  onSignOut,
  userName,
}: {
  onSignOut?: () => void;
  userName?: string;
}) {
  const [health, setHealth] = useState<Health | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [patient, setPatient] = useState("");
  const [transcript, setTranscript] = useState("");
  const [plans, setPlans] = useState<TreatmentPlan[]>([]);
  const [selectedVersion, setSelectedVersion] = useState(0);
  const [diff, setDiff] = useState<PlanDiff | null>(null);
  const [view, setView] = useState<"plan" | "pdf">("plan");
  const [step, setStep] = useState("");
  const [error, setError] = useState("");
  const [screen, setScreen] = useState<"editor" | "plans">("editor");

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  const busy = step !== "";
  const latest = plans[plans.length - 1];
  const selected = plans.find((plan) => plan.version === selectedVersion) ?? latest;
  const isFinal = latest?.status === "FINAL";
  const currentStep = isFinal ? 3 : latest ? 2 : transcript.trim() ? 1 : 0;
  const ready = health?.status === "ok" && health.llm === "ok";

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
      setView("plan");
      await refresh(id, result.plan.version);
    });

  const apply = (answers: Answer[], corrections: string) =>
    run("starting", async () => {
      const result = await api.revisePlan(sessionId, answers, corrections, setStep);
      setDiff(result.diff);
      setView("plan");
      await refresh(sessionId, result.plan.version);
    });

  const confirm = (acceptDefaults: boolean) =>
    run("pdf", async () => {
      const final = await api.confirmPlan(sessionId, acceptDefaults);
      setDiff(null);
      setView("pdf");
      await refresh(sessionId, final.version);
    });

  function clearWorkspace() {
    setSessionId("");
    setPatient("");
    setTranscript("");
    setPlans([]);
    setSelectedVersion(0);
    setDiff(null);
    setView("plan");
    setError("");
    setScreen("editor");
  }

  const openPlan = (id: string) => {
    if (id === sessionId) {
      setScreen("editor");
      return;
    }
    const unsaved = !latest && transcript.trim();
    if (unsaved && !window.confirm("Leave your current notes? Unsaved edits will be lost.")) return;
    void run("starting", async () => {
      const [session, versions] = await Promise.all([api.getSession(id), api.listPlans(id)]);
      setSessionId(session.id);
      setPatient(session.patient_label);
      setTranscript(session.transcript);
      setPlans(versions);
      setSelectedVersion(versions[versions.length - 1]?.version ?? 0);
      setDiff(null);
      setView("plan");
      setScreen("editor");
    });
  };

  const onPlanDeleted = (id: string) => {
    if (id !== sessionId) return;
    clearWorkspace();
    setScreen("plans");
  };

  const removeSession = () => {
    if (!window.confirm("Delete this plan with its recordings and all versions?")) return;
    void run("starting", async () => {
      await api.deleteSession(sessionId);
      clearWorkspace();
    });
  };

  const dictation = (
    <>
      <label className="field">
        <span>Patient reference</span>
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
      <button
        type="button"
        className={latest ? "secondary" : "primary-wide"}
        disabled={busy || isFinal || !transcript.trim()}
        onClick={build}
      >
        {latest ? "Rebuild plan from notes" : "Build treatment plan"}
      </button>
    </>
  );

  return (
    <div className="app">
      <header className="topbar">
        <Logo />
        <span className="clinic">{health?.clinic_name ?? ""}</span>
        <nav className="main-nav" aria-label="Main">
          <button
            type="button"
            className={screen === "editor" ? "on" : ""}
            aria-current={screen === "editor" ? "page" : undefined}
            onClick={() => setScreen("editor")}
          >
            Workspace
          </button>
          <button
            type="button"
            className={screen === "plans" ? "on" : ""}
            aria-current={screen === "plans" ? "page" : undefined}
            onClick={() => setScreen("plans")}
          >
            My plans
          </button>
        </nav>
        {screen === "editor" && <Stepper current={currentStep} />}
        <div className="topbar-actions">
          <span className={ready ? "status ok" : "status bad"}>
            <span aria-hidden />
            {ready ? "Ready" : "Unavailable"}
          </span>
          <button type="button" className="ghost" disabled={busy} onClick={clearWorkspace}>
            <PlusIcon size={16} /> New patient
          </button>
          {userName && <span className="user-name">{userName}</span>}
          {onSignOut && (
            <button type="button" className="ghost" disabled={busy} onClick={onSignOut}>
              Sign out
            </button>
          )}
        </div>
      </header>

      {(error || busy) && (
        <div className="toast-area">
          {error && (
            <p className="toast error" role="alert">
              <AlertIcon size={17} /> {error}
              <button type="button" aria-label="Dismiss" onClick={() => setError("")}>
                ×
              </button>
            </p>
          )}
          {busy && (
            <p className="toast" role="status">
              <span className="spinner" aria-hidden /> {STEP_LABELS[step] ?? "Working…"}
            </p>
          )}
        </div>
      )}

      {screen === "plans" ? (
        <MyPlansPage
          busy={busy}
          currentId={sessionId}
          onOpen={openPlan}
          onDeleted={onPlanDeleted}
          onNew={clearWorkspace}
        />
      ) : (
      <main className="workspace">
        <div className="pane left">
          {latest ? (
            <details className="card collapsible">
              <summary>
                <span>
                  <strong>Clinical notes</strong>
                  <small>{patient ? `Patient ${patient}` : "No patient reference"}</small>
                </span>
                <ChevronIcon />
              </summary>
              <div className="collapsible-body">{dictation}</div>
            </details>
          ) : (
            <section className="card">
              <div className="card-head">
                <div>
                  <h2>New treatment plan</h2>
                  <p className="muted">Dictate the work to be done, or type your notes.</p>
                </div>
              </div>
              {dictation}
            </section>
          )}

          {latest && !isFinal && (
            <QuestionsPanel
              questions={latest.questions}
              busy={busy}
              onApply={apply}
              onConfirm={confirm}
              onError={setError}
            />
          )}

          {isFinal && (
            <section className="card done">
              <span className="done-icon">
                <CheckIcon size={22} />
              </span>
              <h2>Plan confirmed</h2>
              <p>Version {latest.version} is final and ready for signature.</p>
              <a className="button" href={latest.pdf_path} download>
                <DownloadIcon size={16} /> Download final PDF
              </a>
            </section>
          )}

          {sessionId && (
            <button type="button" className="danger-link" disabled={busy} onClick={removeSession}>
              <TrashIcon size={15} /> Delete this plan
            </button>
          )}
        </div>

        <div className="pane right">
          {!selected ? (
            <section className="empty">
              <LogoMark size={64} />
              <h2>Your treatment plan will appear here</h2>
              <p>Stages, waiting times, prices and a ready-to-sign PDF.</p>
              <ol>
                <li>
                  <b>1</b> Dictate the treatment
                </li>
                <li>
                  <b>2</b> Answer a few questions
                </li>
                <li>
                  <b>3</b> Confirm and share the PDF
                </li>
              </ol>
            </section>
          ) : (
            <>
              {diff && selected.version === latest.version && <VersionDiff diff={diff} />}
              <section className="card plan-card">
                <div className="plan-head">
                  <div className="plan-title">
                    <h2>Treatment plan</h2>
                    <span className={selected.status === "FINAL" ? "pill final" : "pill draft"}>
                      {selected.status === "FINAL" ? "Final" : "Draft"}
                    </span>
                  </div>
                  <div className="plan-tools">
                    <label className="version">
                      <span className="sr-only">Version</span>
                      <select
                        value={selected.version}
                        onChange={(event) => setSelectedVersion(Number(event.target.value))}
                      >
                        {plans.map((plan) => (
                          <option key={plan.version} value={plan.version}>
                            Version {plan.version}
                            {plan.status === "FINAL" ? " (final)" : ""}
                          </option>
                        ))}
                      </select>
                    </label>
                    <a className="button secondary" href={selected.pdf_path} download>
                      <DownloadIcon size={16} /> Download PDF
                    </a>
                  </div>
                </div>
                <div className="tabs" role="tablist" aria-label="Plan view">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={view === "plan"}
                    className={view === "plan" ? "on" : ""}
                    onClick={() => setView("plan")}
                  >
                    <ListIcon size={16} /> Plan
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={view === "pdf"}
                    className={view === "pdf" ? "on" : ""}
                    onClick={() => setView("pdf")}
                  >
                    <DocumentIcon size={16} /> PDF
                  </button>
                </div>
                {view === "plan" ? <PlanView plan={selected} /> : <PdfViewer plan={selected} />}
              </section>
            </>
          )}
        </div>
      </main>
      )}
    </div>
  );
}
