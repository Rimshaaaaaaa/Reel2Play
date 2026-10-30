import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, getCoupons, redeemCoupon, type CouponsOut, type RedeemOut } from "../api";
import "./Coupons.css";

const TONE: Record<RedeemOut["result"], "good" | "warn" | "bad"> = {
  redeemed: "good",
  already_used: "bad",
  shared_code: "warn",
  not_found: "bad",
};

/**
 * Feature 40: every win gives the player their own code, which arrives in the WhatsApp order
 * message. The shop types it here when the customer orders, and each code works once.
 */
export function Coupons({ shopKey }: { shopKey: string }) {
  const [counts, setCounts] = useState<CouponsOut | null>(null);
  const [code, setCode] = useState("");
  const [answer, setAnswer] = useState<RedeemOut | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    getCoupons(shopKey)
      .then(setCounts)
      .catch(() => setCounts(null));
  }, [shopKey]);
  useEffect(load, [load]);

  async function check(event: FormEvent) {
    event.preventDefault();
    if (!code.trim()) return;
    setBusy(true);
    setProblem(null);
    try {
      setAnswer(await redeemCoupon(shopKey, code));
      setCode("");
      load();
    } catch (error) {
      setAnswer(null);
      setProblem(error instanceof ApiError ? error.message : "That did not go through. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card coupons" aria-labelledby="coupons-title">
      <div className="coupons-head">
        <h2 id="coupons-title">Win codes</h2>
        {counts ? (
          <p className="coupons-count">
            <strong>{counts.issued}</strong> given, <strong>{counts.redeemed}</strong> used
          </p>
        ) : null}
      </div>
      <p className="coupons-note">
        Each winner gets their own code in the WhatsApp order message. When they order, type the
        code here: it works once.
      </p>
      <form className="redeem" onSubmit={(event) => void check(event)}>
        <label htmlFor="redeem-code">Customer's code</label>
        <div className="redeem-row">
          <input
            id="redeem-code"
            className="redeem-input"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="R2P-K7QD-M2XP"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            maxLength={24}
            dir="ltr"
          />
          <button type="submit" className="btn" disabled={busy || !code.trim()}>
            {busy ? "Checking…" : "Use code"}
          </button>
        </div>
      </form>
      {answer ? (
        <p className="redeem-answer" data-tone={TONE[answer.result]} role="status">
          {answer.message}
          {answer.product ? <span className="redeem-product"> {answer.product}</span> : null}
        </p>
      ) : null}
      {problem ? (
        <p className="form-error" role="alert">
          {problem}
        </p>
      ) : null}
    </section>
  );
}
