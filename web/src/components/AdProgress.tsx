import type { AdOut } from "../api";
import { isSettled } from "../api";
import { ACTOR_LABEL, OCCASION_LABEL } from "../format";
import { AbTest } from "./AbTest";
import { EasierNote, EasierVersion } from "./EasierVersion";
import { ShareCard } from "./ShareCard";
import { TestReport } from "./TestReport";
import "./AdProgress.css";


const OFFER_SOURCE: Record<string, string> = {
  owner: "from you",
  voice: "said in your voice note",
  caption: "read from the video's text",
  speech: "heard in the video",
  none: "",
};

/** Passed checks are listed in the report, so the timeline keeps only failures. */
const HIDDEN_ACTIONS = new Set(["gate.passed"]);

export function AdProgress({ ad }: { ad: AdOut }) {
  const settled = isSettled(ad);
  const lines = ad.progress.filter((line) => !HIDDEN_ACTIONS.has(line.action));
  return (
    <div className="ad-progress">
      {ad.share ? <ShareCard share={ad.share} /> : null}
      <EasierNote ad={ad} />
      {(ad.status === "published" || ad.status === "replaced") && !ad.easier_for ? (
        <EasierVersion ad={ad} />
      ) : null}
      {ad.share && (ad.variant ?? "A") === "A" ? <AbTest ad={ad} /> : null}
      {ad.report ? <TestReport report={ad.report} /> : null}

      <section className="card" aria-labelledby="progress-title">
        <h2 id="progress-title">
          {ad.status === "published"
            ? "How your game was made"
            : settled
              ? "Done so far"
              : "Working on your game"}
        </h2>
        <ol className="timeline" aria-live="polite">
          {lines.map((line, index) => {
            const running = !settled && index === lines.length - 1;
            return (
              <li key={`${line.at}-${index}`} className={running ? "running" : undefined}>
                <span className="actor">{ACTOR_LABEL[line.actor] ?? line.actor}</span>
                <span className="message">{line.message}</span>
              </li>
            );
          })}
        </ol>
        {(ad.status === "failed" || ad.status === "blocked") && ad.error ? (
          <p className="ad-error" role="alert">
            {ad.error}
          </p>
        ) : null}
      </section>

      {ad.brief ? (
        <section className="card brief" aria-labelledby="brief-title">
          <h2 id="brief-title">What the director found</h2>
          <dl>
            <div>
              <dt>Product</dt>
              <dd>{ad.brief.product}</dd>
            </div>
            <div>
              <dt>Colours</dt>
              <dd className="swatches">
                {ad.brief.palette.map((color) => (
                  <span key={color} className="swatch" style={{ background: color }} title={color} />
                ))}
              </dd>
            </div>
            <div>
              <dt>Price</dt>
              <dd>{ad.brief.price ?? "Not given; the game shows no price"}</dd>
            </div>
            <div>
              <dt>Offer</dt>
              <dd>
                {ad.brief.offer_text ?? "No offer"}
                {ad.brief.offer_text ? (
                  <small> ({OFFER_SOURCE[ad.brief.offer_source] ?? ad.brief.offer_source})</small>
                ) : null}
              </dd>
            </div>
            {ad.brief.occasion && OCCASION_LABEL[ad.brief.occasion] ? (
              <div>
                <dt>Occasion</dt>
                <dd>{OCCASION_LABEL[ad.brief.occasion]}</dd>
              </div>
            ) : null}
            {ad.brief.more_products?.length ? (
              <div>
                <dt>Other products</dt>
                <dd>{ad.brief.more_products.join(", ")}</dd>
              </div>
            ) : null}
            <div>
              <dt>Game language</dt>
              <dd>{ad.brief.language === "ur" ? <span lang="ur">اردو</span> : "English"}</dd>
            </div>
          </dl>
          {ad.sprites[0] && ad.sprites[0].quality === "lower" ? (
            <p className="note">
              The cut-out used the simple method, so its edges may be rough. It improves once the
              SAM 3.1 worker is running.
            </p>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
