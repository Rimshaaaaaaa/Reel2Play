import { useCallback, useEffect, useState } from "react";
import { getComparison, sendVote, type Comparison } from "../api";
import "./ComparePage.css";

type Choice = "game" | "still";

/** Blind preference test (feature 41): the same ad as a game and as a picture, unlabelled. */
export function ComparePage() {
  const [pair, setPair] = useState<Comparison | null>(null);
  const [state, setState] = useState<"loading" | "empty" | "ready" | "thanks">("loading");

  const load = useCallback(
    () =>
      getComparison()
        .then((value) => {
          setPair(value);
          setState("ready");
        })
        .catch(() => setState("empty")),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);

  function another() {
    setState("loading");
    void load();
  }

  async function pick(choice: Choice) {
    if (!pair) return;
    await sendVote(pair, choice).catch(() => undefined);
    setState("thanks");
  }

  if (state === "empty") {
    return <p>There is nothing to compare yet. Come back once a few games are live.</p>;
  }
  const sides: Choice[] = pair?.game_side === "left" ? ["game", "still"] : ["still", "game"];
  return (
    <div className="compare">
      <header className="compare-intro">
        <h1>Which ad would make you buy?</h1>
        <p>Look at both, play if you like, then pick one. We only keep your pick.</p>
      </header>
      {state === "thanks" ? (
        <div className="card compare-thanks" role="status">
          <h2>Thank you</h2>
          <button type="button" className="btn" onClick={another}>
            Compare another
          </button>
        </div>
      ) : pair ? (
        <div className="pair">
          {sides.map((kind, index) => (
            <section key={kind} className="card option" aria-label={`Ad ${index + 1}`}>
              {kind === "game" ? (
                <iframe
                  src={pair.game_url}
                  title={`Ad ${index + 1}`}
                  sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
                />
              ) : (
                <figure
                  className="still"
                  lang={pair.still.language}
                  dir={pair.still.language === "ur" ? "rtl" : "ltr"}
                >
                  <img src={pair.still.image_url} alt="" />
                  <figcaption>
                    <strong>{pair.still.product}</strong>
                    {pair.still.offer ? <span>{pair.still.offer}</span> : null}
                    {pair.still.price ? <span>{pair.still.price}</span> : null}
                  </figcaption>
                </figure>
              )}
              <button type="button" className="btn" onClick={() => void pick(kind)}>
                Ad {index + 1}
              </button>
            </section>
          ))}
        </div>
      ) : (
        <p role="status">Loading…</p>
      )}
    </div>
  );
}
