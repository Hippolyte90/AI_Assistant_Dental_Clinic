import type { Interval, TreatmentPlan } from "../types";
import { AlertIcon, ClockIcon } from "./icons";

export function eur(value: string | number): string {
  const [whole, cents] = Number(value).toFixed(2).split(".");
  return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, " ")}.${cents} €`;
}

function span(low: number, high: number): string {
  if (high === 0) return "Single stage";
  const [unit, size] = low >= 60 ? ["months", 30] : low >= 14 ? ["weeks", 7] : ["days", 1];
  const first = Math.round(low / size);
  const last = Math.round(high / size);
  return first === last ? `${first} ${unit}` : `${first}–${last} ${unit}`;
}

function IntervalLine({ interval }: { interval: Interval }) {
  return (
    <div className="interval">
      <ClockIcon size={15} />
      <span>
        Wait <strong>{span(interval.min_days, interval.max_days)}</strong> · {interval.reason}
      </span>
      {interval.assumed && <span className="tag amber">To confirm</span>}
    </div>
  );
}

export function PlanView({ plan }: { plan: TreatmentPlan }) {
  const [low, high] = plan.estimated_duration_days;
  const itemCount = plan.stages.reduce((count, stage) => count + stage.items.length, 0);
  const hasAssumedInterval = plan.stages.some((stage) => stage.interval_after?.assumed);
  return (
    <section aria-label="Treatment plan">
      <dl className="summary">
        <div>
          <dt>Stages</dt>
          <dd>{plan.stages.length}</dd>
        </div>
        <div>
          <dt>Services</dt>
          <dd>{itemCount}</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{span(low, high)}</dd>
        </div>
        <div className="summary-total">
          <dt>Total</dt>
          <dd>{eur(plan.total_eur)}</dd>
        </div>
      </dl>

      {hasAssumedInterval && (
        <p className="notice">
          <AlertIcon size={16} />
          Waiting times marked “To confirm” are standard defaults. Please check them for this
          patient.
        </p>
      )}

      <ol className="timeline">
        {plan.stages.map((stage) => (
          <li className="stage" key={stage.number}>
            <span className="stage-number" aria-hidden>
              {stage.number}
            </span>
            <div className="stage-body">
              <div className="stage-head">
                <div>
                  <h3>
                    <span className="sr-only">Stage {stage.number}: </span>
                    {stage.title}
                  </h3>
                  <p className="muted">{stage.goal}</p>
                </div>
                <strong className="stage-total">{eur(stage.subtotal)}</strong>
              </div>
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
                          {item.provisional && <span className="tag amber">Provisional</span>}
                          {item.auto_added && <span className="tag">Clinic rule</span>}
                        </td>
                        <td>
                          {item.teeth.length ? (
                            <span className="teeth">
                              {item.teeth.map((tooth) => (
                                <span key={tooth}>{tooth}</span>
                              ))}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="num">{item.quantity}</td>
                        <td className="num">{eur(item.unit_price)}</td>
                        <td className="num">{eur(item.line_total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {stage.interval_after && <IntervalLine interval={stage.interval_after} />}
            </div>
          </li>
        ))}
      </ol>

      {plan.unmapped_mentions.length > 0 && (
        <p className="notice">
          <AlertIcon size={16} />
          Mentioned but not in the price list (not priced): {plan.unmapped_mentions.join("; ")}
        </p>
      )}
    </section>
  );
}
