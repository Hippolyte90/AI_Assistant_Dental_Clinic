import { useEffect, useRef, useState } from "react";
import { MicIcon, StopIcon } from "./icons";

interface Props {
  onRecorded: (audio: Blob) => void;
  disabled?: boolean;
  compact?: boolean;
  label?: string;
}

const MAX_SECONDS = 600;
const BARS = 24;

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function Recorder({ onRecorded, disabled, compact, label = "Start dictation" }: Props) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [levels, setLevels] = useState<number[]>(() => Array(BARS).fill(0));
  const [error, setError] = useState("");
  const [playback, setPlayback] = useState("");
  const recorder = useRef<MediaRecorder | null>(null);
  const cleanup = useRef<() => void>(() => undefined);

  useEffect(() => () => cleanup.current(), []);
  useEffect(
    () => () => {
      if (playback) URL.revokeObjectURL(playback);
    },
    [playback],
  );

  async function start() {
    setError("");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("Microphone access was denied. Allow it in the browser, or type the notes.");
      return;
    }
    const mimeType = "audio/webm;codecs=opus";
    const media = new MediaRecorder(
      stream,
      MediaRecorder.isTypeSupported(mimeType) ? { mimeType } : undefined,
    );
    const chunks: BlobPart[] = [];
    media.ondataavailable = (event) => chunks.push(event.data);

    const audioContext = new AudioContext();
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 128;
    audioContext.createMediaStreamSource(stream).connect(analyser);
    const samples = new Uint8Array(analyser.frequencyBinCount);
    let frame = 0;
    const measure = () => {
      analyser.getByteFrequencyData(samples);
      setLevels(
        Array.from({ length: BARS }, (_, index) => Math.min(1, (samples[index + 1] ?? 0) / 190)),
      );
      frame = requestAnimationFrame(measure);
    };
    measure();

    const started = Date.now();
    const timer = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - started) / 1000);
      setSeconds(elapsed);
      if (elapsed >= MAX_SECONDS && media.state === "recording") media.stop();
    }, 250);

    cleanup.current = () => {
      window.clearInterval(timer);
      cancelAnimationFrame(frame);
      stream.getTracks().forEach((track) => track.stop());
      void audioContext.close();
      cleanup.current = () => undefined;
    };
    media.onstop = () => {
      cleanup.current();
      setRecording(false);
      setLevels(Array(BARS).fill(0));
      const audio = new Blob(chunks, { type: media.mimeType || "audio/webm" });
      setPlayback(URL.createObjectURL(audio));
      onRecorded(audio);
    };
    recorder.current = media;
    setSeconds(0);
    setRecording(true);
    media.start();
  }

  const stop = () => recorder.current?.stop();

  if (compact) {
    return (
      <span className="mic-inline">
        <button
          type="button"
          className={recording ? "icon-button live" : "icon-button"}
          onClick={recording ? stop : start}
          disabled={disabled}
          aria-label={recording ? "Stop recording" : "Answer by voice"}
          title={recording ? "Stop recording" : "Answer by voice"}
        >
          {recording ? <StopIcon size={15} /> : <MicIcon size={16} />}
        </button>
        {recording && <span className="timer">{clock(seconds)}</span>}
        {error && <span className="field-error">{error}</span>}
      </span>
    );
  }

  return (
    <div className={recording ? "recorder is-live" : "recorder"}>
      <button
        type="button"
        className="record"
        onClick={recording ? stop : start}
        disabled={disabled}
        aria-label={recording ? "Stop" : playback ? "Record again" : label}
      >
        {recording ? <StopIcon size={24} /> : <MicIcon size={26} />}
      </button>
      <div className="recorder-body">
        {recording ? (
          <>
            <div className="recorder-title">
              <span className="live-dot" aria-hidden /> Listening <span className="timer">{clock(seconds)}</span>
            </div>
            <div className="wave" role="img" aria-label="Microphone level">
              {levels.map((level, index) => (
                <span key={index} style={{ height: `${Math.max(8, level * 100)}%` }} />
              ))}
            </div>
          </>
        ) : playback ? (
          <>
            <div className="recorder-title">Recording saved</div>
            <audio controls src={playback} />
          </>
        ) : (
          <>
            <div className="recorder-title">{label}</div>
            <p className="muted">Describe the treatment, teeth and timing.</p>
          </>
        )}
      </div>
      {error && <p className="field-error recorder-error">{error}</p>}
    </div>
  );
}
