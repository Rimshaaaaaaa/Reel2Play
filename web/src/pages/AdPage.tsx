import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, getAd, isSettled, streamAd, type AdOut } from "../api";
import { AdProgress } from "../components/AdProgress";
import { PhoneFrame } from "../components/PhoneFrame";
import { ProductPreview } from "../components/ProductPreview";
import { WhyPanel } from "../components/WhyPanel";
import "./AdPage.css";

const POLL_MS = 1500;
const POLL_WHILE_STREAMING_MS = 5000;

/**
 * A signed link changes on every fetch (its expiry moves every second). Keep the first link
 * for the same file so the game inside the iframe is not reloaded, and reset to
 * "tap to start", on every poll.
 */
function useStableSrc(url: string | null | undefined): string | undefined {
  const [stable, setStable] = useState<string | undefined>(url ?? undefined);
  if (!url) return undefined;
  // Same file (ignoring the changing ?exp=&sig= part): keep the first link.
  if (stable === undefined || stable.split("?")[0] !== url.split("?")[0]) {
    setStable(url); // a new build: adopt its link
    return url;
  }
  return stable;
}

/** Keeps one ad fresh: live events when the browser can stream, polling otherwise. */
function useAd(id: string): { ad: AdOut | null; missing: boolean } {
  const [ad, setAd] = useState<AdOut | null>(null);
  const [missing, setMissing] = useState(false);
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const load = async (): Promise<AdOut | null> => {
      try {
        const next = await getAd(id);
        if (!cancelled) setAd(next);
        return next;
      } catch (error) {
        if (!cancelled && error instanceof ApiError && error.status === 404) setMissing(true);
        return null;
      }
    };
    const stop = streamAd(id, () => void load());
    const poll = async () => {
      const next = await load();
      if (cancelled || (next && isSettled(next))) return;
      timer = window.setTimeout(poll, stop ? POLL_WHILE_STREAMING_MS : POLL_MS);
    };
    void poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      stop?.();
    };
  }, [id]);
  return { ad, missing };
}

export function AdPage() {
  const { adId = "" } = useParams();
  const { ad, missing } = useAd(adId);
  // Hooks must run before any early return.
  const game = useStableSrc(ad?.build_url);

  if (missing) {
    return (
      <section>
        <h1>Game not found</h1>
        <p>
          This game does not exist. <Link to="/">Make one from your Reel</Link>.
        </p>
      </section>
    );
  }

  const sprites = ad?.sprites ?? [];
  return (
    <div className="ad-page">
      <section className="ad-main">
        <h1>{ad?.brief?.product ?? "Your game"}</h1>
        {ad?.is_synthetic ? <p className="synthetic-note">Synthetic sample</p> : null}
        {ad ? (
          <>
            <AdProgress ad={ad} />
            <WhyPanel adId={ad.id} settled={isSettled(ad)} />
          </>
        ) : (
          <div className="card" role="status">
            Loading…
          </div>
        )}
      </section>
      <aside className="ad-phone">
        <PhoneFrame sign={ad?.brief?.product ?? "Your shop"}>
          {game ? (
            <iframe
              className="game"
              src={game}
              title="Your game"
              sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
            />
          ) : sprites.length ? (
            <ProductPreview sprites={sprites} />
          ) : (
            <p className="preview-empty">The game appears here as soon as it is built.</p>
          )}
        </PhoneFrame>
      </aside>
    </div>
  );
}