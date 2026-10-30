import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, getBatch, type BatchItem, type BatchOut } from "../api";
import { STATUS_LABEL, TEMPLATE_NAME } from "../format";
import "./BatchPage.css";

const POLL_MS = 5000;

function ItemCard({ item, number }: { item: BatchItem; number: number }) {
  const status = item.status ?? (item.video_status === "failed" ? "failed" : "queued");
  return (
    <li className="set-card">
      <div className="set-picture">
        {item.preview_url ? (
          <img src={item.preview_url} alt="" />
        ) : (
          <span className="set-number" aria-hidden="true">
            {number}
          </span>
        )}
      </div>
      <div className="set-copy">
        <p className="set-name" dir="auto">
          {item.name ?? `Product ${number}`}
        </p>
        <p className="set-meta">
          <span className="status-chip" data-status={status}>
            {STATUS_LABEL[status] ?? status}
          </span>
          {item.template ? <span>{TEMPLATE_NAME[item.template] ?? item.template}</span> : null}
          {item.price ? <span dir="auto">{item.price}</span> : null}
        </p>
        <div className="set-actions">
          {item.link ? (
            <a className="btn" href={item.link} target="_blank" rel="noreferrer">
              Open game
            </a>
          ) : null}
          {item.ad_id ? (
            <Link className="btn btn-quiet" to={`/ads/${item.ad_id}`}>
              {item.link ? "Share it" : "See progress"}
            </Link>
          ) : null}
        </div>
      </div>
    </li>
  );
}

/** Feature 46: every product of a batch, each on its way to a tested game. */
export function BatchStatusPage() {
  const { batchId = "" } = useParams();
  const [batch, setBatch] = useState<BatchOut | null>(null);
  const [missing, setMissing] = useState(false);

  const load = useCallback(() => {
    getBatch(batchId)
      .then(setBatch)
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 404) setMissing(true);
      });
  }, [batchId]);
  useEffect(load, [load]);

  const working = batch ? batch.finished < batch.items.length : true;
  useEffect(() => {
    if (!working || missing) return;
    const timer = window.setInterval(load, POLL_MS);
    return () => window.clearInterval(timer);
  }, [working, missing, load]);

  if (missing) {
    return (
      <section>
        <h1>Batch not found</h1>
        <p>
          This batch does not exist. <Link to="/batch">Start a new one</Link>.
        </p>
      </section>
    );
  }
  if (!batch) return <p role="status">Loading your games…</p>;
  const total = batch.items.length;
  return (
    <div className="batch">
      <header className="batch-head">
        <h1>Your set of {total} games</h1>
        <p className="batch-lede" role="status">
          {batch.published} of {total} live
          {working ? ", the rest are being made and tested." : "."}
        </p>
        <div
          className="set-progress"
          role="progressbar"
          aria-label="Games finished"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={batch.finished}
        >
          <span style={{ inlineSize: `${(batch.finished / Math.max(1, total)) * 100}%` }} />
        </div>
      </header>
      <ul className="set-grid">
        {batch.items.map((item, index) => (
          <ItemCard key={item.video_id} item={item} number={index + 1} />
        ))}
      </ul>
      <p className="batch-alt">
        Every game is also in your <Link to="/studio">studio</Link>.
      </p>
    </div>
  );
}
