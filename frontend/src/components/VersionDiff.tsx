import type { PlanDiff } from "../types";
import { eur } from "./PlanView";

export function VersionDiff({ diff }: { diff: PlanDiff }) {
  const unchanged = !diff.added.length && !diff.removed.length && !diff.changed.length;
  const change = Number(diff.total_after) - Number(diff.total_before);
  return (
    <aside className="diff" aria-label="What changed">
      <div className="diff-head">
        <h3>What changed</h3>
        <span>
          {eur(diff.total_before)} → <strong>{eur(diff.total_after)}</strong>
          {change !== 0 && (
            <em className={change > 0 ? "up" : "down"}>
              {change > 0 ? "+" : "−"}
              {eur(Math.abs(change))}
            </em>
          )}
        </span>
      </div>
      {unchanged && <p className="muted">No service changed.</p>}
      <ul>
        {diff.added.map((line) => (
          <li key={`a${line}`} className="added">
            <b>+</b> {line}
          </li>
        ))}
        {diff.removed.map((line) => (
          <li key={`r${line}`} className="removed">
            <b>−</b> {line}
          </li>
        ))}
        {diff.changed.map((line) => (
          <li key={`c${line}`}>
            <b>~</b> {line}
          </li>
        ))}
      </ul>
    </aside>
  );
}
