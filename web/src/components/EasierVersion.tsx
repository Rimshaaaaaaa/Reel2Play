import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, decideEasier, getEasier, storedShop, type AdOut, type EasierOut } from "../api";
import { percent } from "../format";
import "./EasierVersion.css";

const POLL_MS = 5000;
const WORKING = new Set(["making", "using"]);

/** One raised gauge: how many players got this far, with the line code compares it to. */
function Gauge({ label, value, line }: { label: string; value: number | null; line: number }) {
  const share = Math.max(0, Math.min(1, value ?? 0));
  return (
    <div className="gauge" data-low={value !== null && value < line ? "true" : undefined}>
      <div className="gauge-head">
        <span>{label}</span>
        <strong>{percent(value)}</strong>
      </div>
      <div className="gauge-track" role="img" aria-label={`${label}: ${percent(value)}`}>
        <span className="gauge-fill" style={{ inlineSize: `${share * 100}%` }} />
        <span className="gauge-line" style={{ insetInlineStart: `${line * 100}%` }} />
      </div>
    </div>
  );
}

/**
 * Feature 44: when players find a live game hard, an easier version is made and tested;
 * the owner plays it and chooses whether it takes over the game's link.
 */
export function EasierVersion({ ad }: { ad: AdOut }) {
  const [easier, setEasier] = useState<EasierOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const shop = storedShop();
  const mine = Boolean(shop && ad.shop_id && shop.id === ad.shop_id);

  const load = useCallback(() => {
    getEasier(ad.id)
      .then(setEasier)
      .catch(() => setEasier(null));
  }, [ad.id]);
  useEffect(load, [load]);

  const working = Boolean(easier?.version?.state && WORKING.has(easier.version.state));
  useEffect(() => {
    if (!working) return;
    const timer = window.setInterval(load, POLL_MS);
    return () => window.clearInterval(timer);
  }, [working, load]);

  async function decide(choice: "use" | "dismiss") {
    if (!shop) return;
    setBusy(true);
    setProblem(null);
    try {
      setEasier(await decideEasier(ad.id, shop.key, choice));
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : "That did not go through. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!easier || (!easier.hard && !easier.version)) return null;
  const version = easier.version;
  const stats = easier.stats;
  const winShare = stats.finishes ? (stats.wins ?? 0) / stats.finishes : null;

  return (
    <section className="card easier" aria-labelledby="easier-title">
      <h2 id="easier-title">
        {version?.state === "used" ? "The easier version is live" : "Players find this game hard"}
      </h2>
      {easier.reason ? (
        <p className="easier-why">From your players' numbers: {easier.reason}.</p>
      ) : null}
      <div className="gauges">
        <Gauge label="Reach the end" value={stats.completion ?? null} line={0.5} />
        <Gauge label="Win, of those" value={winShare} line={0.4} />
      </div>

      {version?.state === "making" ? (
        <p className="easier-state" role="status">
          Making and testing an easier version of the same game…
        </p>
      ) : null}
      {version?.state === "ready" ? (
        <div className="easier-ready">
          <p>
            We made the same game easier and it passed every check
            {version.change ? `: ${version.change}` : ""}. It goes live only if you choose it, under
            the same link, so your shared links, poster and website keep working.
          </p>
          <div className="easier-actions">
            {version.play_url ? (
              <a className="btn btn-quiet" href={version.play_url} target="_blank" rel="noreferrer">
                Play the easier version
              </a>
            ) : null}
            {mine ? (
              <>
                <button type="button" className="btn" disabled={busy} onClick={() => void decide("use")}>
                  Use the easier version
                </button>
                <button
                  type="button"
                  className="btn btn-quiet"
                  disabled={busy}
                  onClick={() => void decide("dismiss")}
                >
                  Keep this one
                </button>
              </>
            ) : (
              <p className="easier-note">Open this page in the browser that made the game to choose.</p>
            )}
          </div>
        </div>
      ) : null}
      {version?.state === "using" ? (
        <p className="easier-state" role="status">
          Publishing the easier version under your link…
        </p>
      ) : null}
      {version?.state === "used" ? (
        <p className="easier-state">
          Your link now opens the easier version. <Link to={`/ads/${version.id}`}>See it</Link>
        </p>
      ) : null}
      {version?.state === "dismissed" ? (
        <p className="easier-state">You kept this game as it is.</p>
      ) : null}
      {version && version.status === "needs_person" ? (
        <p className="easier-state">The easier version did not pass every check, so it was not offered.</p>
      ) : null}
      {problem ? (
        <p className="form-error" role="alert">
          {problem}
        </p>
      ) : null}
    </section>
  );
}

/** On an easier version's own page: which game it makes easier. */
export function EasierNote({ ad }: { ad: AdOut }) {
  if (!ad.easier_for) return null;
  return (
    <p className="card easier-of">
      An easier version of <Link to={`/ads/${ad.easier_for}`}>this game</Link>, made because players
      found it hard.
    </p>
  );
}
