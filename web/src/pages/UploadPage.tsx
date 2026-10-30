import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  agencyBrand,
  ApiError,
  chooseBrand,
  uploadVideo,
  type BriefValues,
  type UploadFields,
  type VideoOut,
} from "../api";
import { EMPTY_BRIEF, briefProblem } from "../brief";
import { BriefFields } from "../components/BriefFields";
import { PhoneFrame } from "../components/PhoneFrame";
import { PreparingPanel } from "../components/PreparingPanel";
import { VoiceNote } from "../components/VoiceNote";
import { useAdOnceReady } from "../hooks/useAdOnceReady";
import "./UploadPage.css";

type Stage =
  | { kind: "editing"; error: string | null }
  | { kind: "sending" }
  | { kind: "preparing"; video: VideoOut };

const EMPTY: UploadFields = { ...EMPTY_BRIEF, files: [], voiceNote: null };

function usePreview(file: File | undefined): string | null {
  const url = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => (url ? URL.revokeObjectURL(url) : undefined), [url]);
  return url;
}

export function UploadPage() {
  const [brand, setBrand] = useState(agencyBrand);
  const [fields, setFields] = useState<UploadFields>(() =>
    brand ? { ...EMPTY, shopName: brand.name } : EMPTY,
  );
  const [stage, setStage] = useState<Stage>({ kind: "editing", error: null });
  const firstFile = fields.files[0];
  const preview = usePreview(firstFile);
  const failed = useAdOnceReady(stage.kind === "preparing" ? stage.video : null);

  const set = <K extends keyof BriefValues>(key: K, value: BriefValues[K]) =>
    setFields((current) => ({ ...current, [key]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    const problem = briefProblem(fields);
    if (problem) {
      setStage({ kind: "editing", error: problem });
      return;
    }
    setStage({ kind: "sending" });
    try {
      const video = await uploadVideo(fields);
      setStage({ kind: "preparing", video });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Upload failed. Try again.";
      setStage({ kind: "editing", error: message });
    }
  }

  const busy = stage.kind === "sending";

  return (
    <div className="upload">
      <section className="upload-copy">
        <h1>Your Reel, as a 20-second game</h1>
        <p className="upload-lede">
          Send one product video or a few photos. We build a short game that stars your product
          and ends on your offer, test it on small and large phones, and send you the link.
        </p>

        {stage.kind === "editing" || stage.kind === "sending" ? (
          <>
            {brand ? (
              <div className="import-hint brand-hint" role="status">
                <p>
                  Making a game for <strong dir="auto">{brand.name}</strong>, from your agency
                  workspace.
                </p>
                <button
                  type="button"
                  className="btn btn-quiet"
                  onClick={() => {
                    chooseBrand(null);
                    setBrand(null);
                  }}
                >
                  Use my own shop
                </button>
              </div>
            ) : null}
            <div className="import-hint">
              <p>Already posted it on Instagram or Facebook?</p>
              <Link to="/import" className="btn btn-quiet">
                Import a post
              </Link>
            </div>
            <div className="import-hint">
              <p>Many products? Make a game for each in one go.</p>
              <Link to="/batch" className="btn btn-quiet">
                Upload a batch
              </Link>
            </div>
            <form className="brief-form card" onSubmit={submit} noValidate>
              <BriefFields fields={fields} set={set}>
                <label className="field file-field">
                  <span>Video or photos</span>
                  <input
                    type="file"
                    accept="video/mp4,video/quicktime,video/webm,image/jpeg,image/png,image/webp"
                    multiple
                    onChange={(e) => {
                      const files = Array.from(e.target.files ?? []);
                      setFields((current) => ({ ...current, files }));
                    }}
                  />
                  <small>One video up to 3 minutes, or up to 6 photos.</small>
                </label>
                {fields.files.length > 1 &&
                fields.files.every((file) => file.type.startsWith("image/")) ? (
                  <label className="choice catalog-choice">
                    <input
                      type="checkbox"
                      checked={Boolean(fields.catalog)}
                      onChange={(e) =>
                        setFields((current) => ({ ...current, catalog: e.target.checked }))
                      }
                    />
                    <span>These are different products (the first one is the main product)</span>
                  </label>
                ) : null}
                <label className="choice lab-choice">
                  <input
                    type="checkbox"
                    checked={Boolean(fields.lab)}
                    onChange={(e) => setFields((current) => ({ ...current, lab: e.target.checked }))}
                  />
                  <span>
                    Experimental: let the director invent a new kind of game for this product
                    (checked and play-tested like every game)
                  </span>
                </label>
                <VoiceNote
                  value={fields.voiceNote}
                  onChange={(voiceNote) => setFields((current) => ({ ...current, voiceNote }))}
                />
              </BriefFields>

              {stage.kind === "editing" && stage.error ? (
                <p className="form-error" role="alert">
                  {stage.error}
                </p>
              ) : null}

              <button
                type="submit"
                className="btn"
                disabled={busy || !fields.rightsConfirmed || fields.files.length === 0}
              >
                {busy ? "Sending…" : "Make my game"}
              </button>
            </form>
          </>
        ) : (
          <PreparingPanel
            failed={failed}
            onReset={() => setStage({ kind: "editing", error: null })}
          />
        )}
      </section>

      <aside className="upload-preview">
        <PhoneFrame sign={fields.shopName || "Your shop"}>
          {preview && firstFile?.type.startsWith("video/") ? (
            <video src={preview} muted loop autoPlay playsInline aria-label="Your video, muted" />
          ) : preview ? (
            <img src={preview} alt="Your product photo" />
          ) : (
            <p className="preview-empty">Your video plays here, without its sound.</p>
          )}
        </PhoneFrame>
      </aside>
    </div>
  );
}
