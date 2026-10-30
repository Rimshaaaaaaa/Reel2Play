import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  ApiError,
  IMPORT_START_URL,
  getImportPosts,
  getImportStatus,
  importPost,
  type BriefValues,
  type ImportPost,
  type VideoOut,
} from "../api";
import { EMPTY_BRIEF, briefProblem } from "../brief";
import { BriefFields } from "../components/BriefFields";
import { PreparingPanel } from "../components/PreparingPanel";
import { useAdOnceReady } from "../hooks/useAdOnceReady";
import "./ImportPage.css";

const SESSION_STORAGE = "r2p.import";

const SIGN_IN_PROBLEMS: Record<string, string> = {
  denied: "Facebook access was not allowed, so nothing was imported.",
  expired: "That sign-in took too long or was already used. Try again.",
  failed: "Facebook did not finish the sign-in. Try again in a minute.",
};

function savedSession(): string | null {
  try {
    return window.sessionStorage.getItem(SESSION_STORAGE);
  } catch {
    return null;
  }
}

function saveSession(session: string | null): void {
  try {
    if (session) window.sessionStorage.setItem(SESSION_STORAGE, session);
    else window.sessionStorage.removeItem(SESSION_STORAGE);
  } catch {
    // Without storage the sign-in lasts until this tab is reloaded.
  }
}

function shortDate(value: string | null): string | null {
  if (!value) return null;
  const day = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(day.getTime())) return null;
  return day.toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" });
}

type Stage =
  | { kind: "picking" }
  | { kind: "editing"; post: ImportPost; error: string | null }
  | { kind: "sending"; post: ImportPost }
  | { kind: "preparing"; post: ImportPost; video: VideoOut };

/** Import a video from the shop's own Instagram account or Facebook Page (feature 3). */
export function ImportPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const fromFacebook = new URLSearchParams(location.hash.slice(1));
  const [session, setSession] = useState<string | null>(
    () => fromFacebook.get("session") ?? savedSession(),
  );
  const [notice, setNotice] = useState<string | null>(
    () => SIGN_IN_PROBLEMS[fromFacebook.get("error") ?? ""] ?? null,
  );
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [posts, setPosts] = useState<ImportPost[] | null>(null);
  const [stage, setStage] = useState<Stage>({ kind: "picking" });
  const [fields, setFields] = useState<BriefValues>(EMPTY_BRIEF);
  const failed = useAdOnceReady(stage.kind === "preparing" ? stage.video : null);
  const formRef = useRef<HTMLFormElement>(null);

  // The sign-in comes back in the address's fragment; keep it out of the address bar.
  useEffect(() => {
    if (!location.hash) return;
    const fresh = new URLSearchParams(location.hash.slice(1)).get("session");
    if (fresh) saveSession(fresh);
    navigate("/import", { replace: true });
  }, [location.hash, navigate]);

  useEffect(() => {
    if (session) return;
    getImportStatus()
      .then((status) => setEnabled(status.enabled))
      .catch(() => setEnabled(false));
  }, [session]);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    getImportPosts(session)
      .then((found) => !cancelled && setPosts(found))
      .catch((problem: unknown) => {
        if (cancelled) return;
        if (problem instanceof ApiError && problem.status === 401) {
          saveSession(null);
          setSession(null);
        }
        setNotice(problem instanceof ApiError ? problem.message : "Your posts did not load.");
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  useEffect(() => {
    if (stage.kind === "editing") formRef.current?.scrollIntoView?.({ block: "start" }); // jsdom has no scrolling
  }, [stage.kind]);

  const set = <K extends keyof BriefValues>(key: K, value: BriefValues[K]) =>
    setFields((current) => ({ ...current, [key]: value }));

  async function submit(event: FormEvent, post: ImportPost) {
    event.preventDefault();
    const problem = briefProblem(fields);
    if (problem || !session) {
      setStage({ kind: "editing", post, error: problem ?? "Sign in again." });
      return;
    }
    setStage({ kind: "sending", post });
    try {
      setStage({ kind: "preparing", post, video: await importPost(session, post.id, fields) });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "That did not work. Try again.";
      setStage({ kind: "editing", post, error: message });
    }
  }

  return (
    <div className="import">
      <header className="import-intro">
        <h1>Import a post</h1>
        <p>
          Pick a video you already posted on your Instagram account or Facebook Page. We only read
          your posts; we never post or change anything.
        </p>
      </header>

      {notice ? (
        <p className="form-error" role="alert">
          {notice}
        </p>
      ) : null}

      {!session ? (
        <SignIn enabled={enabled} />
      ) : stage.kind === "preparing" ? (
        <PreparingPanel
          failed={failed}
          resetLabel="Pick another post"
          onReset={() => setStage({ kind: "picking" })}
        />
      ) : posts === null ? (
        <p role="status">Loading your posts…</p>
      ) : posts.length === 0 ? (
        <div className="card import-empty">
          <h2>No videos found</h2>
          <p>
            Your Pages and the Instagram account linked to them have no videos we can read.{" "}
            <Link to="/">Upload the video file instead</Link>.
          </p>
        </div>
      ) : (
        <>
          <ul className="posts" aria-label="Your videos">
            {posts.map((post) => (
              <PostCard
                key={post.id}
                post={post}
                chosen={stage.kind !== "picking" && stage.post.id === post.id}
                onChoose={() => setStage({ kind: "editing", post, error: null })}
              />
            ))}
          </ul>

          {stage.kind === "editing" || stage.kind === "sending" ? (
            <form
              ref={formRef}
              className="brief-form card import-form"
              onSubmit={(event) => void submit(event, stage.post)}
              noValidate
            >
              <h2>About this offer</h2>
              <BriefFields fields={fields} set={set} />
              {stage.kind === "editing" && stage.error ? (
                <p className="form-error" role="alert">
                  {stage.error}
                </p>
              ) : null}
              <button
                type="submit"
                className="btn"
                disabled={stage.kind === "sending" || !fields.rightsConfirmed}
              >
                {stage.kind === "sending" ? "Importing…" : "Make my game"}
              </button>
            </form>
          ) : null}
        </>
      )}
    </div>
  );
}

function SignIn({ enabled }: { enabled: boolean | null }) {
  if (enabled === null) return <p role="status">Checking…</p>;
  if (!enabled) {
    return (
      <div className="card import-empty">
        <h2>Importing is not set up here yet</h2>
        <p>
          This server has no Facebook app connected. <Link to="/">Upload the video file</Link>{" "}
          instead; it makes the same game.
        </p>
      </div>
    );
  }
  return (
    <div className="card import-signin">
      <h2>Sign in with the account that runs your shop's Page</h2>
      <p>
        Facebook asks which Pages to share. Pick your shop's Page; its linked Instagram account
        comes with it.
      </p>
      <a className="btn" href={IMPORT_START_URL}>
        Continue with Facebook
      </a>
    </div>
  );
}

interface PostCardProps {
  post: ImportPost;
  chosen: boolean;
  onChoose: () => void;
}

function PostCard({ post, chosen, onChoose }: PostCardProps) {
  const date = shortDate(post.created_at);
  const where = post.source === "instagram" ? "Instagram" : "Facebook Page";
  return (
    <li className="card post" data-chosen={chosen || undefined} data-locked={!post.downloadable || undefined}>
      <div className="post-thumb">
        {post.thumbnail_url ? (
          <img src={post.thumbnail_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
        ) : null}
        <span className="post-source" data-source={post.source}>
          {where}
        </span>
      </div>
      <div className="post-copy">
        <p className="post-account">
          <span>{post.account}</span>
          {date ? <time dateTime={post.created_at ?? undefined}>{date}</time> : null}
        </p>
        {post.caption ? <p className="post-caption">{post.caption}</p> : null}
        {post.downloadable ? (
          <button
            type="button"
            className={chosen ? "btn" : "btn btn-quiet"}
            aria-pressed={chosen}
            onClick={onChoose}
          >
            {chosen ? "Chosen" : "Use this video"}
          </button>
        ) : (
          <p className="post-locked">
            Instagram keeps this file because of its music. Upload it instead.
          </p>
        )}
      </div>
    </li>
  );
}
