import { useEffect, useRef, useState } from "react";

interface Props {
  onRecorded: (audio: Blob) => void;
  disabled?: boolean;
  compact?: boolean;
  label?: string;
}

const MAX_SECONDS = 600;

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function Recorder({ onRecorded, disabled, compact, label = "Start dictation" }: Props) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState("");
  const [playback, setPlayback] = useState("");
  const recorder = useRef<MediaRecorder | null>(null);
  const cleanup = useRef<() => void>(() => undefined);

  useEffect(() => () => cleanup.current(), []);
  useEffect(() => () => {
    if (playback) URL.revokeObjectURL(playback);
  }, [playback]);

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
    analyser.fftSize = 256;
    audioContext.createMediaStreamSource(stream).connect(analyser);
    const samples = new Uint8Array(analyser.frequencyBinCount);
    let frame = 0;
    const measure = () => {
      analyser.getByteFrequencyData(samples);
      setLevel(Math.min(1, samples.reduce((sum, v) => sum + v, 0) / samples.length / 90));
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
      setLevel(0);
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
          {recording ? "■" : "🎤"}
        </button>
        {recording && <span className="timer">{clock(seconds)}</span>}
        {error && <span className="field-error">{error}</span>}
      </span>
    );
  }

  return (
    <div className="recorder">
      <button
        type="button"
        className={recording ? "record live" : "record"}
        onClick={recording ? stop : start}
        disabled={disabled}
      >
        <span className="dot" aria-hidden />
        {recording ? "Stop" : playback ? "Record again" : label}
      </button>
      {recording && (
        <div className="meter-row">
          <span className="timer">{clock(seconds)}</span>
          <span className="meter" role="img" aria-label="Microphone level">
            <span style={{ width: `${level * 100}%` }} />
          </span>
        </div>
      )}
      {!recording && playback && <audio controls src={playback} />}
      {error && <p className="field-error">{error}</p>}
    </div>
  );
}
