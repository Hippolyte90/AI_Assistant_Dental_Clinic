import type { PlanDiff } from "../types";
import { eur } from "./PlanView";

export function VersionDiff({ diff }: { diff: PlanDiff }) {
  const unchanged = !diff.added.length && !diff.removed.length && !diff.changed.length;
  return (
    <aside className="diff">
      <h3>What changed</h3>
      {unchanged && <p className="muted">No service changed.</p>}
      <ul>
        {diff.added.map((line) => (
          <li key={`a${line}`} className="added">+ {line}</li>
        ))}
        {diff.removed.map((line) => (
          <li key={`r${line}`} className="removed">− {line}</li>
        ))}
        {diff.changed.map((line) => (
          <li key={`c${line}`}>~ {line}</li>
        ))}
      </ul>
      <p>
        Total: {eur(diff.total_before)} → <strong>{eur(diff.total_after)}</strong>
      </p>
    </aside>
  );
}
