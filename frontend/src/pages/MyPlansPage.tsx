import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { DocumentIcon, DownloadIcon, PlusIcon, TrashIcon } from "../components/icons";
import { eur } from "../components/PlanView";
import type { SessionSummary } from "../types";

interface Props {
  busy: boolean;
  currentId: string;
  onOpen: (id: string) => void;
  onDeleted: (id: string) => void;
  onNew: () => void;
}

type Filter = "all" | "draft" | "final" | "notes";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "draft", label: "Drafts" },
  { key: "final", label: "Final" },
  { key: "notes", label: "Notes only" },
];

function kind(plan: SessionSummary): Exclude<Filter, "all"> {
  if (plan.status === "FINAL") return "final";
  return plan.status === "DRAFT" ? "draft" : "notes";
}

const PILL = {
  final: { label: "Final", className: "pill final" },
  draft: { label: "Draft", className: "pill draft" },
  notes: { label: "Notes only", className: "pill notes" },
};

function formatDate(value: string): string {
  return new Date(value).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function MyPlansPage({ busy, currentId, onOpen, onDeleted, onNew }: Props) {
  const [plans, setPlans] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [deleting, setDeleting] = useState("");

  async function load() {
    setError("");
    try {
      setPlans(await api.listSessions());
    } catch (failure) {
      setError((failure as Error).message);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (plans ?? []).filter(
      (plan) =>
        (filter === "all" || kind(plan) === filter) &&
        (!query ||
          plan.patient_label.toLowerCase().includes(query) ||
          plan.preview.toLowerCase().includes(query)),
    );
  }, [plans, search, filter]);

  async function remove(plan: SessionSummary) {
    const name = plan.patient_label || "this plan";
    if (!window.confirm(`Delete ${name} with its recordings and all versions?`)) return;
    setDeleting(plan.id);
    setError("");
    try {
      await api.deleteSession(plan.id);
      setPlans((old) => (old ?? []).filter((item) => item.id !== plan.id));
      onDeleted(plan.id);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setDeleting("");
    }
  }

  return (
    <main className="plans-page">
      <div className="plans-head">
        <div>
          <h1>My plans</h1>
          <p className="muted">
            {plans === null
              ? "Loading…"
              : `${plans.length} saved plan${plans.length === 1 ? "" : "s"}`}
          </p>
        </div>
        <button type="button" disabled={busy} onClick={onNew}>
          <PlusIcon size={16} /> New plan
        </button>
      </div>

      {error && (
        <p className="notice" role="alert">
          {error}{" "}
          <button type="button" className="link-button" onClick={() => void load()}>
            Try again
          </button>
        </p>
      )}

      {plans !== null && plans.length > 0 && (
        <div className="plans-tools">
          <input
            aria-label="Search plans"
            placeholder="Search by patient reference or notes"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <div className="filters" role="group" aria-label="Filter by status">
            {FILTERS.map((item) => (
              <button
                type="button"
                key={item.key}
                aria-pressed={filter === item.key}
                className={filter === item.key ? "on" : ""}
                onClick={() => setFilter(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {plans !== null && plans.length === 0 && !error && (
        <section className="empty">
          <DocumentIcon size={40} />
          <h2>No plans yet</h2>
          <p>Your treatment plans will be saved here automatically.</p>
          <button type="button" disabled={busy} onClick={onNew}>
            <PlusIcon size={16} /> Create your first plan
          </button>
        </section>
      )}

      {plans !== null && plans.length > 0 && visible.length === 0 && (
        <p className="muted plans-none">No plan matches your search.</p>
      )}

      <ul className="plan-list">
        {visible.map((plan) => {
          const state = PILL[kind(plan)];
          return (
            <li className={plan.id === currentId ? "plan-row current" : "plan-row"} key={plan.id}>
              <div className="plan-main">
                <div className="plan-name">
                  <strong>{plan.patient_label || "No patient reference"}</strong>
                  <span className={state.className}>{state.label}</span>
                  {plan.id === currentId && <span className="tag">Open</span>}
                </div>
                <p className="muted plan-preview">{plan.preview || "No notes"}</p>
              </div>
              <dl className="plan-facts">
                <div>
                  <dt>Total</dt>
                  <dd>{plan.total_eur === null ? "—" : eur(plan.total_eur)}</dd>
                </div>
                <div>
                  <dt>Stages</dt>
                  <dd>{plan.stage_count || "—"}</dd>
                </div>
                <div>
                  <dt>Version</dt>
                  <dd>{plan.current_version || "—"}</dd>
                </div>
                <div className="plan-date">
                  <dt>Updated</dt>
                  <dd>{formatDate(plan.updated_at)}</dd>
                </div>
              </dl>
              <div className="plan-actions">
                <button
                  type="button"
                  disabled={busy}
                  aria-label={`Open ${plan.patient_label || "plan"}`}
                  onClick={() => onOpen(plan.id)}
                >
                  Open
                </button>
                {plan.current_version > 0 && (
                  <a
                    className="button secondary icon-only"
                    href={`/api/sessions/${plan.id}/plans/${plan.current_version}/pdf`}
                    download
                    aria-label={`Download PDF for ${plan.patient_label || "plan"}`}
                    title="Download PDF"
                  >
                    <DownloadIcon size={16} />
                  </a>
                )}
                <button
                  type="button"
                  className="secondary icon-only danger"
                  disabled={busy || deleting === plan.id}
                  aria-label={`Delete ${plan.patient_label || "plan"}`}
                  title="Delete"
                  onClick={() => void remove(plan)}
                >
                  <TrashIcon size={16} />
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </main>
  );
}
