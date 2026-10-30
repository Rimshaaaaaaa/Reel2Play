import { useEffect, useState } from "react";
import { getWhy, type WhyOut } from "../api";
import { ACTOR_LABEL, rupees } from "../format";
import "./WhyPanel.css";

/** Steps that are choices or corrections, rather than progress. */
const DECISIONS = new Set([
  "analysis.done",
  "game.designed",
  "build.corrected",
  "gate.failed",
  "fix.done",
  "test.needs_person",
  "guard.flagged",
  "safety.blocked",
  "safety.offer_removed",
  "publish.meta_skipped",
]);

/** Why the agents did what they did, from the audit trail, and what it cost (51, 48). */
export function WhyPanel({ adId, settled }: { adId: string; settled: boolean }) {
  const [open, setOpen] = useState(false);
  const [why, setWhy] = useState<WhyOut | null>(null);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    getWhy(adId)
      .then((value) => !cancelled && setWhy(value))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [open, adId, settled]);

  const decisions = why?.decisions.filter((d) => DECISIONS.has(d.action)) ?? [];
  return (
    <details className="card why" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Why the agents decided this</summary>
      {why ? (
        <div className="why-body">
          <p className={why.trail_intact ? "trail ok" : "trail bad"}>
            {why.trail_intact
              ? `Audit trail intact: ${why.entries_checked} entries checked against their hashes.`
              : "The audit trail does not match its hashes: an entry was changed after it was written."}
          </p>

          {why.builds.length > 0 ? (
            <section>
              <h3>Game builds</h3>
              <ol className="why-list">
                {why.builds.map((build) => (
                  <li key={build.number}>
                    <strong>
                      Build {build.number}, {build.template}
                    </strong>
                    <span>{build.reason}</span>
                  </li>
                ))}
              </ol>
            </section>
          ) : null}

          {why.fixes.length > 0 ? (
            <section>
              <h3>Fix rounds</h3>
              <ol className="why-list">
                {why.fixes.map((fix) => (
                  <li key={fix.round}>
                    <strong>
                      Round {fix.round}: {fix.failed_gates.join(", ").replaceAll("_", " ")}
                    </strong>
                    <span>{fix.change}</span>
                  </li>
                ))}
              </ol>
            </section>
          ) : null}

          {decisions.length > 0 ? (
            <section>
              <h3>Decisions and checks</h3>
              <ul className="why-list">
                {decisions.map((decision, index) => (
                  <li key={`${decision.at}-${index}`}>
                    <strong>{ACTOR_LABEL[decision.actor] ?? decision.actor}</strong>
                    <span>{decision.message}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section>
            <h3>Model cost</h3>
            <p>
              {rupees(why.cost.pkr)} for {why.cost.calls} model call
              {why.cost.calls === 1 ? "" : "s"}
              {Object.keys(why.cost_by_role).length > 0
                ? `: ${Object.entries(why.cost_by_role)
                    .map(([role, pkr]) => `${role} ${rupees(pkr)}`)
                    .join(", ")}.`
                : "."}
            </p>
          </section>
        </div>
      ) : open ? (
        <p role="status">Loading the audit trail…</p>
      ) : null}
    </details>
  );
}
