// Mirrors backend/app/models/schemas.py. Money is a decimal string.

export interface Health {
  status: string;
  llm: string;
  catalog_items: number;
  rules_validated: boolean;
  clinic_name: string;
}

export interface AccountUser {
  name: string;
  email: string;
}

export interface AuthStatus {
  required?: boolean;
  authenticated: boolean;
  user: AccountUser | null;
}

export interface Session {
  id: string;
  patient_label: string;
  state: "CREATED" | "TRANSCRIBED" | "DRAFT" | "CONFIRMED";
  transcript: string;
  current_version: number;
}

export interface SessionSummary {
  id: string;
  patient_label: string;
  state: Session["state"];
  status: "DRAFT" | "FINAL" | null;
  current_version: number;
  total_eur: string | null;
  stage_count: number;
  preview: string;
  created_at: string;
  updated_at: string;
}

export interface Transcript {
  text: string;
}

export interface Interval {
  min_days: number;
  max_days: number;
  reason: string;
  assumed: boolean;
}

export interface PlanItem {
  catalog_id: string;
  code: string | null;
  name: string;
  quantity: number;
  teeth: number[];
  unit_price: string;
  line_total: string;
  provisional: boolean;
  auto_added: boolean;
}

export interface Stage {
  number: number;
  title: string;
  goal: string;
  items: PlanItem[];
  subtotal: string;
  interval_after: Interval | null;
}

export interface QuestionOption {
  id: string;
  label: string;
  price_delta_eur: string | null;
}

export interface Question {
  id: string;
  text: string;
  kind: "choice" | "missing_param" | "add_on" | "unknown_service" | "interval";
  options: QuestionOption[];
  allow_free_text: boolean;
  blocking: boolean;
}

export interface TreatmentPlan {
  session_id: string;
  version: number;
  status: "DRAFT" | "FINAL";
  stages: Stage[];
  total_eur: string;
  estimated_duration_days: [number, number];
  questions: Question[];
  assumptions: string[];
  unmapped_mentions: string[];
  pdf_path: string;
}

export interface PlanDiff {
  added: string[];
  removed: string[];
  changed: string[];
  total_before: string;
  total_after: string;
}

export interface PlanResult {
  plan: TreatmentPlan;
  diff: PlanDiff | null;
}

export interface Job {
  id: string;
  status: "queued" | "running" | "done" | "error";
  step: string;
  result?: PlanResult;
  error?: string;
}

export interface Answer {
  question_id: string;
  option_id?: string;
  free_text?: string;
}
