import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { TreatmentPlan } from "../types";

export function PdfViewer({ plan }: { plan: TreatmentPlan }) {
  const [pages, setPages] = useState(0);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    setPages(0);
    setFailed(false);
    api
      .pdfPages(plan.pdf_path)
      .then((result) => active && setPages(result.pages))
      .catch(() => active && setFailed(true));
    return () => {
      active = false;
    };
  }, [plan.pdf_path]);

  if (failed) {
    return <p className="notice">The preview is unavailable. Use Download PDF to open it.</p>;
  }
  if (!pages) return <p className="muted">Loading the document…</p>;

  return (
    <div className="pdf-preview">
      {Array.from({ length: pages }, (_, index) => (
        <img
          key={index}
          src={`${plan.pdf_path}/pages/${index + 1}`}
          alt={`Treatment plan, version ${plan.version}, page ${index + 1} of ${pages}`}
        />
      ))}
    </div>
  );
}
