import { CheckIcon } from "./icons";

const STEPS = ["Dictate", "Review", "Clarify", "Confirmed"];

export function Stepper({ current }: { current: number }) {
  return (
    <ol className="stepper" aria-label="Progress">
      {STEPS.map((label, index) => {
        const done = index < current || (index === current && index === STEPS.length - 1);
        const state = done ? "done" : index === current ? "current" : "todo";
        return (
          <li key={label} className={state} aria-current={index === current ? "step" : undefined}>
            <span className="step-dot">{done ? <CheckIcon size={13} /> : index + 1}</span>
            <span className="step-label">{label}</span>
          </li>
        );
      })}
    </ol>
  );
}
