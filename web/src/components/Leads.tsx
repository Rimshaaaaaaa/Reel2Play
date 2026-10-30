import { useEffect, useState } from "react";
import { ApiError, downloadLeads, getLeads, setLeads, type LeadsOut } from "../api";
import "./Leads.css";

/**
 * Feature 43: players can ask for the shop's offers on WhatsApp. Nothing is kept unless they
 * agree in the chat, and STOP deletes it. The owner turns it on, sees how many agreed, and
 * downloads the list for their own WhatsApp.
 */
export function Leads({ shopKey }: { shopKey: string }) {
  const [leads, setState] = useState<LeadsOut | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getLeads(shopKey)
      .then(setState)
      .catch(() => setState(null));
  }, [shopKey]);

  async function toggle() {
    if (!leads) return;
    setBusy(true);
    setProblem(null);
    try {
      setState(await setLeads(shopKey, !leads.enabled));
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : "That did not go through. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    setProblem(null);
    try {
      const blob = await downloadLeads(shopKey);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "whatsapp-sign-ups.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : "The list could not be downloaded.");
    }
  }

  if (!leads) return null;
  return (
    <section className="card leads" aria-labelledby="leads-title">
      <div className="leads-head">
        <h2 id="leads-title">Offers on WhatsApp</h2>
        <label className="switch">
          <input
            type="checkbox"
            role="switch"
            checked={leads.enabled}
            disabled={busy || (!leads.available && !leads.enabled)}
            onChange={() => void toggle()}
          />
          <span className="switch-track" aria-hidden="true">
            <span className="switch-knob" />
          </span>
          <span>{leads.enabled ? "On" : "Off"}</span>
        </label>
      </div>
      <p className="leads-note">
        When on, your games end with a small "Get this shop's offers on WhatsApp" link. A player
        who taps it sends us a message, and we ask in the chat whether you may send them offers.
        Only a yes is kept; they can send STOP any time.
      </p>
      {!leads.available ? (
        <p className="leads-note">This needs WhatsApp to be set up on the server first.</p>
      ) : null}
      <div className="leads-count">
        <p>
          <strong>{leads.agreed}</strong> {leads.agreed === 1 ? "person has" : "people have"} agreed
        </p>
        <button
          type="button"
          className="btn btn-quiet"
          disabled={leads.agreed === 0}
          onClick={() => void download()}
        >
          Download the list
        </button>
      </div>
      {problem ? (
        <p className="form-error" role="alert">
          {problem}
        </p>
      ) : null}
    </section>
  );
}
