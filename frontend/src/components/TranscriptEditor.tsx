interface Props {
  value: string;
  onChange: (text: string) => void;
  disabled?: boolean;
}

export function TranscriptEditor({ value, onChange, disabled }: Props) {
  return (
    <label className="field">
      <span>Clinical notes</span>
      <textarea
        rows={7}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        placeholder="Your dictation appears here. You can also type or paste notes, e.g. Root canal on 36 with a rubber dam. Two weeks later a core build-up on 36."
      />
    </label>
  );
}
