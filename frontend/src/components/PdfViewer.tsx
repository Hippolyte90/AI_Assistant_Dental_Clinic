import type { TreatmentPlan } from "../types";

interface Props {
  plans: TreatmentPlan[];
  selected: TreatmentPlan;
  onSelect: (version: number) => void;
}

export function PdfViewer({ plans, selected, onSelect }: Props) {
  return (
    <section aria-label="PDF">
      <div className="pdf-bar">
        <label>
          Version{" "}
          <select value={selected.version} onChange={(e) => onSelect(Number(e.target.value))}>
            {plans.map((plan) => (
              <option key={plan.version} value={plan.version}>
                v{plan.version} – {plan.status}
              </option>
            ))}
          </select>
        </label>
        <a className="button secondary" href={selected.pdf_path} download>
          Download PDF
        </a>
      </div>
      <iframe key={selected.pdf_path} title="Treatment plan PDF" src={selected.pdf_path} />
    </section>
  );
}
