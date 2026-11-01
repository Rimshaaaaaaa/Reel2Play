import { useEffect, useState } from "react";
import { ApiError, getSamples, trySample, type SampleOut, type VideoOut } from "../api";
import { useAdOnceReady } from "../hooks/useAdOnceReady";
import "./TryPage.css";

/** For judges: pick a sample Reel and watch each agent work on it, live (feature 60). */
export function TryPage() {
  const [samples, setSamples] = useState<SampleOut[] | null>(null);
  const [video, setVideo] = useState<VideoOut | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const failed = useAdOnceReady(video);

  useEffect(() => {
    if (!failed) return;
    setError(failed.error ?? "The sample could not be prepared. Try another sample.");
    setVideo(null);
    setBusyKey(null);
  }, [failed]);

  useEffect(() => {
    getSamples()
      .then(setSamples)
      .catch(() => setError("The samples could not be loaded. Check the connection and refresh."));
  }, []);

  async function start(sample: SampleOut) {
    setBusyKey(sample.key);
    setError(null);
    try {
      setVideo(await trySample(sample.key));
    } catch (problem) {
      setBusyKey(null);
      setError(problem instanceof ApiError ? problem.message : "That did not start. Try again.");
    }
  }

  return (
    <div className="try">
      <header className="try-intro">
        <h1>Watch a Reel become a game</h1>
        <p>
          Pick a sample. The director reads it, the product is cut out, a game is built, the
          tester plays it on a small phone and a tablet, and the publisher makes the link and
          the Reel. Each step appears as it happens.
        </p>
      </header>
      {error || failed ? (
        <p className="form-error" role="alert">
          {failed?.error ?? error}
        </p>
      ) : null}
      {samples ? (
        <ul className="samples">
          {samples.map((sample) => (
            <li key={sample.key} className="card sample">
              <video src={sample.video_url} muted loop autoPlay playsInline aria-hidden="true" />
              <div className="sample-copy">
                <h2 lang={sample.language} dir={sample.language === "ur" ? "rtl" : "ltr"}>
                  {sample.title}
                </h2>
                <p>{sample.about}</p>
                {sample.synthetic ? (
                  <p className="synthetic-note" title={sample.source}>
                    Synthetic sample
                  </p>
                ) : null}
                <button
                  type="button"
                  className="btn"
                  disabled={busyKey !== null}
                  onClick={() => void start(sample)}
                  aria-label={`Make a game from ${sample.title}`}
                >
                  {busyKey === sample.key ? "Starting…" : "Make this game"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : error ? null : (
        <p role="status">Loading samples…</p>
      )}
    </div>
  );
}
