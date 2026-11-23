interface Props {
  value: string;
  onChange: (text: string) => void;
  disabled?: boolean;
}

export function TranscriptEditor({ value, onChange, disabled }: Props) {
  return (
    <label className="field">
      <span>Dictation (check it, correct it, or type or paste notes)</span>
      <textarea
        rows={9}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        placeholder="e.g. Root canal on 36 with a rubber dam. Two weeks later a core build-up on 36."
      />
    </label>
  );
}
