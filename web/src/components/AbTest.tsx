import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  getAbTest,
  makeVersions,
  storedShop,
  type AbTestOut,
  type AdOut,
} from "../api";
import { percent, STATUS_LABEL, TEMPLATE_NAME } from "../format";
import "./AbTest.css";

const POLL_MS = 5000;
const SETTLED = new Set(["published", "needs_person", "blocked", "failed", "ready", "replaced"]);

/**
 * Feature 19: two more versions of a published game, with another template, other colours
 * and other button words, shared through one link so the shop can see which one sells.
 */
export function AbTest({ ad }: { ad: AdOut }) {
  const [test, setTest] = useState<AbTestOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const shop = storedShop();
  const mine = Boolean(shop && ad.shop_id && shop.id === ad.shop_id);

  const load = useCallback(() => {
    getAbTest(ad.id)
      .then(setTest)
      .catch(() => setProblem("The test could not be loaded. Refresh to try again."));
  }, [ad.id]);

  useEffect(load, [load]);

  const running = test ? test.versions.some((v) => !SETTLED.has(v.status)) : false;
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(load, POLL_MS);
    return () => window.clearInterval(timer);
  }, [running, load]);

  async function start() {
    if (!shop) return;
    setBusy(true);
    setProblem(null);
    try {
      setTest(await makeVersions(ad.id, shop.key));
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : "That did not start. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (!test) return null;
  const single = test.versions.length < 2;

  return (
    <section className="card ab" aria-labelledby="ab-title">
      <h2 id="ab-title">Test three versions</h2>
      {single ? (
        <>
          <p>
            Make two more versions of this game, each with another game type, other colours and
            other button words. One link shares your customers between all three, so you can
            see which one gets the most orders.
          </p>
          {mine ? (
            <button type="button" className="btn" disabled={busy} onClick={() => void start()}>
              {busy ? "Starting…" : "Make two more versions"}
            </button>
          ) : (
            <p className="ab-note">Open this page in the browser that made the game to start a test.</p>
          )}
        </>
      ) : (
        <>
          <ul className="ab-versions">
            {test.versions.map((version) => {
              const leading = test.leader === version.variant;
              return (
                <li key={version.id} className="ab-version" data-leading={leading || undefined}>
                  <span className="ab-letter" aria-hidden="true">
                    {version.variant}
                  </span>
                  <div className="ab-what">
                    <p className="ab-name">Version {version.variant}</p>
                    {version.template ? (
                      <span className="ab-template">{TEMPLATE_NAME[version.template] ?? version.template}</span>
                    ) : null}
                    <span className="status-chip" data-status={version.status}>
                      {STATUS_LABEL[version.status] ?? version.status}
                    </span>
                  </div>
                  <dl className="ab-numbers">
                    <div>
                      <dt>Plays</dt>
                      <dd>{version.stats.plays ?? 0}</dd>
                    </div>
                    <div>
                      <dt>Finished</dt>
                      <dd>{percent(version.stats.completion ?? null)}</dd>
                    </div>
                    <div>
                      <dt>Order taps</dt>
                      <dd>{percent(version.stats.cta_rate ?? null)}</dd>
                    </div>
                  </dl>
                  {version.link ? (
                    <a className="ab-open" href={version.link} target="_blank" rel="noreferrer">
                      Open
                    </a>
                  ) : null}
                </li>
              );
            })}
          </ul>
          <p className="ab-verdict" role="status">
            {test.verdict}
          </p>
          {test.link ? (
            <p className="ab-link">
              Share this one link: <a href={test.link}>{test.link.replace(/^https?:\/\//, "")}</a>
            </p>
          ) : null}
        </>
      )}
      {problem ? (
        <p className="form-error" role="alert">
          {problem}
        </p>
      ) : null}
    </section>
  );
}
