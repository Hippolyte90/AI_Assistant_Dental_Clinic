import type {
  Answer,
  AuthStatus,
  Health,
  Job,
  PlanResult,
  Session,
  SessionSummary,
  Transcript,
  TreatmentPlan,
} from "../types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch {
    throw new Error("The assistant's server is not reachable. Is the backend running?");
  }
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/")) {
      window.dispatchEvent(new Event("cuspia:signed-out"));
    }
    const body = await response.json().catch(() => null);
    throw new Error(body?.message ?? `Request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

function audioForm(blob: Blob): FormData {
  const form = new FormData();
  form.append("file", blob, "recording.webm");
  return form;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForJob(jobId: string, onStep: (step: string) => void): Promise<PlanResult> {
  for (;;) {
    const job = await request<Job>(`/jobs/${jobId}`);
    onStep(job.step);
    if (job.status === "done") return job.result!;
    if (job.status === "error") throw new Error(job.error ?? "The plan could not be built.");
    await sleep(800);
  }
}

export const api = {
  authStatus: () => request<AuthStatus>("/auth/status"),
  login: (email: string, password: string) =>
    request<AuthStatus>("/auth/login", json("POST", { email, password })),
  register: (name: string, email: string, password: string) =>
    request<AuthStatus>("/auth/register", json("POST", { name, email, password })),
  logout: () => request<unknown>("/auth/logout", { method: "POST" }),
  health: () => request<Health>("/health"),
  listSessions: () => request<SessionSummary[]>("/sessions"),
  getSession: (id: string) => request<Session>(`/sessions/${id}`),
  createSession: (patient_label: string) =>
    request<Session>("/sessions", json("POST", { patient_label })),
  deleteSession: (id: string) => request<unknown>(`/sessions/${id}`, { method: "DELETE" }),
  uploadAudio: (id: string, blob: Blob) =>
    request<Transcript>(`/sessions/${id}/audio`, { method: "POST", body: audioForm(blob) }),
  transcribe: (blob: Blob) =>
    request<Transcript>("/transcribe", { method: "POST", body: audioForm(blob) }),
  saveTranscript: (id: string, text: string) =>
    request<Session>(`/sessions/${id}/transcript`, json("PUT", { text })),
  buildPlan: async (id: string, onStep: (step: string) => void) => {
    const { job_id } = await request<{ job_id: string }>(`/sessions/${id}/plan`, { method: "POST" });
    return waitForJob(job_id, onStep);
  },
  revisePlan: async (
    id: string,
    answers: Answer[],
    corrections: string,
    onStep: (step: string) => void,
  ) => {
    const { job_id } = await request<{ job_id: string }>(
      `/sessions/${id}/revise`,
      json("POST", { answers, corrections: corrections || null }),
    );
    return waitForJob(job_id, onStep);
  },
  confirmPlan: (id: string, accept_defaults: boolean) =>
    request<TreatmentPlan>(`/sessions/${id}/confirm`, json("POST", { accept_defaults })),
  listPlans: (id: string) => request<TreatmentPlan[]>(`/sessions/${id}/plans`),
  pdfPages: (pdfPath: string) =>
    request<{ pages: number }>(`${pdfPath.replace(/^\/api/, "")}/pages`),
};
