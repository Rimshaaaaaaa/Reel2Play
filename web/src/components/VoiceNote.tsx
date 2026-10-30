import { useEffect, useMemo, useRef, useState } from "react";
import "./VoiceNote.css";

const MAX_SECONDS = 60;

interface Props {
  value: File | null;
  onChange: (file: File | null) => void;
}

function canRecord(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.MediaRecorder !== "undefined" &&
    typeof navigator.mediaDevices?.getUserMedia === "function"
  );
}

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/**
 * Feature 10: the owner says the offer instead of typing it ("Eid sale, 20% off, for young
 * girls"). Recorded in the browser where it can, or chosen as an audio file; at most a minute.
 */
export function VoiceNote({ value, onChange }: Props) {
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [problem, setProblem] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const url = useMemo(() => (value ? URL.createObjectURL(value) : null), [value]);
  useEffect(() => () => (url ? URL.revokeObjectURL(url) : undefined), [url]);
  useEffect(
    () => () => {
      window.clearInterval(timer.current);
      recorder.current?.stream.getTracks().forEach((track) => track.stop());
    },
    [],
  );

  function stop() {
    window.clearInterval(timer.current);
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  async function start() {
    setProblem(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setProblem("The microphone is not available. Choose an audio file instead.");
      return;
    }
    const chunks: Blob[] = [];
    const next = new MediaRecorder(stream);
    next.addEventListener("dataavailable", (event) => chunks.push(event.data));
    next.addEventListener("stop", () => {
      stream.getTracks().forEach((track) => track.stop());
      setRecording(false);
      const type = next.mimeType || "audio/webm";
      const extension = type.includes("mp4") ? "m4a" : "webm";
      onChange(new File(chunks, `voice-note.${extension}`, { type }));
    });
    recorder.current = next;
    next.start();
    setSeconds(0);
    setRecording(true);
    const started = Date.now();
    timer.current = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - started) / 1000);
      setSeconds(elapsed);
      if (elapsed >= MAX_SECONDS) stop();
    }, 250);
  }

  return (
    <fieldset className="field voice">
      <legend>Voice note (optional)</legend>
      <small>
        Say the offer, the occasion and who it is for, like “Eid sale, 20% off, for young girls”.
        Up to a minute.
      </small>

      {value && url ? (
        <div className="voice-take">
          <audio src={url} controls aria-label="Your voice note" />
          <button type="button" className="btn btn-quiet" onClick={() => onChange(null)}>
            Remove
          </button>
        </div>
      ) : recording ? (
        <div className="voice-take" role="status">
          <span className="voice-live" aria-hidden="true" />
          <span className="voice-clock">Recording {clock(seconds)}</span>
          <button type="button" className="btn" onClick={stop}>
            Stop
          </button>
        </div>
      ) : (
        <div className="voice-take">
          {canRecord() ? (
            <button type="button" className="btn btn-quiet" onClick={() => void start()}>
              <span className="voice-mic" aria-hidden="true" />
              Record a voice note
            </button>
          ) : null}
          <label className="voice-file">
            <span>{canRecord() ? "or choose an audio file" : "Choose an audio file"}</span>
            <input
              type="file"
              accept="audio/*"
              onChange={(e) => onChange(e.target.files?.[0] ?? null)}
            />
          </label>
        </div>
      )}
      {problem ? (
        <p className="form-error" role="alert">
          {problem}
        </p>
      ) : null}
    </fieldset>
  );
}
