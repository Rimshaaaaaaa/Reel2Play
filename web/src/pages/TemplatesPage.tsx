import { useEffect, useState, type FormEvent } from "react";
import { ApiError, getTemplates, submitTemplate, type SubmissionOut, type TemplateCard } from "../api";
import { PhoneFrame } from "../components/PhoneFrame";
import "./TemplatesPage.css";

const STATUS_WORDS: Record<SubmissionOut["status"], string> = {
  checks_failed: "Not sent for review: fix these and send it again",
  waiting: "Passed the checks; waiting for review by the Reel2Play team",
  approved: "Approved",
  rejected: "Not approved",
};

function Submit() {
  const [name, setName] = useState("");
  const [contact, setContact] = useState("");
  const [spec, setSpec] = useState<File | null>(null);
  const [code, setCode] = useState<File | null>(null);
  const [licensed, setLicensed] = useState(false);
  const [result, setResult] = useState<SubmissionOut | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!spec || !code) return;
    setBusy(true);
    setProblem(null);
    try {
      setResult(
        await submitTemplate({ designerName: name, designerContact: contact, templateJson: spec, gameTs: code }),
      );
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : "That did not go through. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card submit" aria-labelledby="submit-title">
      <h2 id="submit-title">Send us a template</h2>
      <p className="templates-note">
        Designers: send a template.json and a game.ts written against the shared engine (see
        templates/ in the code for nine examples). Code checks them first; the Reel2Play team
        reviews what passes, and an approved template is play-tested like every game before any
        shop gets it, with your name on it here.
      </p>
      <form className="submit-form" onSubmit={(e) => void send(e)}>
        <div className="field-row">
          <label className="field">
            <span>Your name or studio</span>
            <input required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="field">
            <span>How we reach you (email or website)</span>
            <input required maxLength={200} value={contact} onChange={(e) => setContact(e.target.value)} />
          </label>
        </div>
        <div className="field-row">
          <label className="field">
            <span>template.json</span>
            <input type="file" accept=".json,application/json" onChange={(e) => setSpec(e.target.files?.[0] ?? null)} />
          </label>
          <label className="field">
            <span>game.ts</span>
            <input type="file" accept=".ts,text/plain" onChange={(e) => setCode(e.target.files?.[0] ?? null)} />
          </label>
        </div>
        <label className="consent">
          <input type="checkbox" checked={licensed} onChange={(e) => setLicensed(e.target.checked)} />
          <span>I made this template and license it to Reel2Play's shops.</span>
        </label>
        <button type="submit" className="btn" disabled={busy || !licensed || !spec || !code || !name || !contact}>
          {busy ? "Sending…" : "Send the template"}
        </button>
      </form>
      {result ? (
        <div className="submit-result" data-status={result.status} role="status">
          <p className="submit-status">{STATUS_WORDS[result.status]}</p>
          {result.problems.length ? (
            <ul>
              {result.problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          ) : null}
          {result.token ? (
            <p className="templates-note">
              Keep this to check your review later: <code>{result.id}</code> with the code{" "}
              <code>{result.token}</code>.
            </p>
          ) : null}
        </div>
      ) : null}
      {problem ? (
        <p className="form-error" role="alert">
          {problem}
        </p>
      ) : null}
    </section>
  );
}

/** Feature 49: every game template, with a demo to play and its designer's name. */
export function TemplatesPage() {
  const [cards, setCards] = useState<TemplateCard[] | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);

  useEffect(() => {
    getTemplates()
      .then(setCards)
      .catch(() => setCards([]));
  }, []);

  const chosen = cards?.find((card) => card.id === playing) ?? null;
  return (
    <div className="templates">
      <header className="templates-head">
        <h1>Game templates</h1>
        <p className="templates-lede">
          The games the director chooses from. Each one is play-tested on every build; play a demo
          with a synthetic product below.
        </p>
      </header>
      <div className="templates-body">
        <ul className="template-grid">
          {(cards ?? []).map((card) => (
            <li key={card.id} className="card template-card" data-playing={card.id === playing || undefined}>
              <h2>{card.name}</h2>
              <p>{card.description}</p>
              <p className="template-meta">
                <span>{card.control}</span>
                <span>Good for {card.good_for.join(", ")}</span>
              </p>
              <div className="template-foot">
                <span className="template-by">By {card.designer}</span>
                <button
                  type="button"
                  className="btn btn-quiet"
                  onClick={() => {
                    setPlaying(card.id);
                    document.querySelector(".templates-phone")?.scrollIntoView?.({ block: "nearest" });
                  }}
                >
                  Play the demo
                </button>
              </div>
            </li>
          ))}
        </ul>
        <aside className="templates-phone" aria-live="polite">
          <PhoneFrame sign={chosen ? chosen.name : "Pick a demo"}>
            {chosen ? (
              <iframe
                key={chosen.id}
                className="game"
                src={chosen.demo_url}
                title={`${chosen.name} demo`}
                sandbox="allow-scripts"
              />
            ) : (
              <p className="preview-empty">Choose "Play the demo" on any template.</p>
            )}
          </PhoneFrame>
        </aside>
      </div>
      <Submit />
    </div>
  );
}
