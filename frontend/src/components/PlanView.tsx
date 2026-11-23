import type { Interval, TreatmentPlan } from "../types";

export function eur(value: string | number): string {
  const [whole, cents] = Number(value).toFixed(2).split(".");
  return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, " ")}.${cents} €`;
}

function span(low: number, high: number): string {
  if (high === 0) return "single stage";
  const [unit, size] = low >= 60 ? ["months", 30] : low >= 14 ? ["weeks", 7] : ["days", 1];
  const first = Math.round(low / size);
  const last = Math.round(high / size);
  return first === last ? `${first} ${unit}` : `${first}–${last} ${unit}`;
}

function IntervalLine({ interval }: { interval: Interval }) {
  return (
    <p className="interval">
      ↓ Next stage after <strong>{span(interval.min_days, interval.max_days)}</strong> (
      {interval.reason})
      {interval.assumed && <span className="tag amber">assumption</span>}
    </p>
  );
}

export function PlanView({ plan }: { plan: TreatmentPlan }) {
  const [low, high] = plan.estimated_duration_days;
  return (
    <section aria-label="Treatment plan">
      <dl className="summary">
        <div>
          <dt>Stages</dt>
          <dd>{plan.stages.length}</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{span(low, high)}</dd>
        </div>
        <div>
          <dt>Total</dt>
          <dd>{eur(plan.total_eur)}</dd>
        </div>
      </dl>
      {plan.stages.map((stage) => (
        <article className="stage" key={stage.number}>
          <h3>
            Stage {stage.number}: {stage.title}
          </h3>
          <p className="muted">{stage.goal}</p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Teeth</th>
                  <th className="num">Qty</th>
                  <th className="num">Unit</th>
                  <th className="num">Total</th>
                </tr>
              </thead>
              <tbody>
                {stage.items.map((item, index) => (
                  <tr key={`${item.catalog_id}-${index}`}>
                    <td>
                      {item.name}
                      {item.provisional && <span className="tag amber">provisional</span>}
                      {item.auto_added && <span className="tag">clinic rule</span>}
                    </td>
                    <td>{item.teeth.join(", ") || "—"}</td>
                    <td className="num">{item.quantity}</td>
                    <td className="num">{eur(item.unit_price)}</td>
                    <td className="num">{eur(item.line_total)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={4}>Stage subtotal</td>
                  <td className="num">{eur(stage.subtotal)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
          {stage.interval_after && <IntervalLine interval={stage.interval_after} />}
        </article>
      ))}
      {plan.unmapped_mentions.length > 0 && (
        <p className="notice">
          Mentioned but not in the price list (not priced): {plan.unmapped_mentions.join("; ")}
        </p>
      )}
    </section>
  );
}
