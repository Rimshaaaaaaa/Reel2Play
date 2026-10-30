import type { VideoOut } from "../api";
import "./PreparingPanel.css";

interface Props {
  failed: VideoOut | null;
  onReset: () => void;
  resetLabel?: string;
}

/** While the video is prepared (sound removed, length read); or why it could not be used. */
export function PreparingPanel({ failed, onReset, resetLabel = "Choose another video" }: Props) {
  if (failed) {
    return (
      <div className="card status status-failed" role="status" aria-live="polite">
        <h2>We could not use this video</h2>
        <p>{failed.error ?? "The file could not be read."}</p>
        <button type="button" className="btn btn-quiet" onClick={onReset}>
          {resetLabel}
        </button>
      </div>
    );
  }
  return (
    <div className="card status" role="status" aria-live="polite">
      <h2>Preparing your video</h2>
      <p>We are removing the sound and reading the length. This takes a few seconds.</p>
    </div>
  );
}
