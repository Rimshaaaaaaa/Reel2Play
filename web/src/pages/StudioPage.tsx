import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, getShop, rememberShop, storedShop, type ShopOut } from "../api";
import { Coupons } from "../components/Coupons";
import { Leads } from "../components/Leads";
import { STATUS_LABEL, TEMPLATE_NAME, percent, rupees } from "../format";
import "./StudioPage.css";

/** The shop's own page: every game, how it is doing, what it cost, and the brand kit (45). */
export function StudioPage() {
  const [stored, setStored] = useState(storedShop);
  const [shop, setShop] = useState<ShopOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!stored) return;
    getShop(stored.key)
      .then(setShop)
      .catch((problem: unknown) => {
        if (problem instanceof ApiError && problem.status === 401) {
          rememberShop(null);
          setStored(null);
        } else setError("The studio could not be loaded. Check the connection and refresh.");
      });
  }, [stored]);

  if (!stored) {
    return (
      <section className="studio-empty">
        <h1>Your studio</h1>
        <p>
          This browser has not made a game yet. <Link to="/">Upload a Reel</Link> and your games,
          their plays and order taps will be kept here. Working for several brands? Use an{" "}
          <Link to="/agency">agency workspace</Link>.
        </p>
      </section>
    );
  }
  if (error) return <p className="form-error" role="alert">{error}</p>;
  if (!shop) return <p role="status">Loading your studio…</p>;

  return (
    <div className="studio">
      <header className="studio-head">
        <h1 dir="auto">{shop.name}</h1>
        <Link to="/batch" className="btn btn-quiet">
          Games for several products
        </Link>
        <button
          type="button"
          className="btn btn-quiet"
          onClick={() => {
            rememberShop(null);
            setStored(null);
          }}
        >
          Forget this browser
        </button>
      </header>

      <dl className="totals">
        <div>
          <dt>Games</dt>
          <dd>{shop.totals.ads}</dd>
        </div>
        <div>
          <dt>Live</dt>
          <dd>{shop.totals.published}</dd>
        </div>
        <div>
          <dt>Plays</dt>
          <dd>{shop.totals.plays}</dd>
        </div>
        <div>
          <dt>Order taps</dt>
          <dd>{shop.totals.cta_taps}</dd>
        </div>
        <div>
          <dt>Model cost</dt>
          <dd>{rupees(shop.totals.pkr)}</dd>
        </div>
      </dl>

      {shop.brand_kit ? (
        <section className="card kit" aria-labelledby="kit-title">
          <h2 id="kit-title">Brand kit</h2>
          <div className="swatches">
            {shop.brand_kit.palette.map((color) => (
              <span key={color} className="swatch" style={{ background: color }} title={color} />
            ))}
          </div>
          {shop.brand_kit.tone ? <p>Tone: {shop.brand_kit.tone}</p> : null}
          <p className="kit-note">Used again for your next game.</p>
        </section>
      ) : null}

      {shop.memory && shop.memory.length > 0 ? (
        <section className="card memory" aria-labelledby="memory-title">
          <h2 id="memory-title">What works for your shop</h2>
          <p className="kit-note">
            From your own games' plays. The director reads this before designing your next game.
          </p>
          <ul className="memory-list">
            {shop.memory.map((line) => {
              const [template = "", rest = ""] = line.split(/:\s(.*)/s);
              return (
                <li key={line} data-best={line.endsWith("the best so far") || undefined}>
                  <strong>{TEMPLATE_NAME[template] ?? template}</strong>
                  <span>{rest.replace(/, the best so far$/, "")}</span>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      <Coupons shopKey={stored.key} />
      <Leads shopKey={stored.key} />

      <ul className="ad-list">
        {shop.ads.map((ad) => (
          <li key={ad.id} className="card ad-row">
            {ad.preview_url ? <img src={ad.preview_url} alt="" /> : <span className="no-preview" />}
            <div className="ad-row-copy">
              <Link to={`/ads/${ad.id}`} className="ad-row-title">
                {ad.product ?? "Game"}
              </Link>
              <span className="status-chip" data-status={ad.status}>
                {STATUS_LABEL[ad.status] ?? ad.status}
              </span>
              <p className="ad-row-stats">
                {ad.stats.plays} plays, {percent(ad.stats.completion)} finished,{" "}
                {ad.stats.cta_taps} order taps, {rupees(ad.cost.pkr)}
              </p>
              {ad.stats.poster_plays || ad.stats.website_plays || ad.stats.challenge_plays ? (
                <p className="ad-row-sources">
                  {ad.stats.poster_plays ?? 0} from the counter poster, {ad.stats.website_plays ?? 0}{" "}
                  from your website, {ad.stats.challenge_plays ?? 0} from players' challenges
                </p>
              ) : null}
            </div>
            {ad.link ? (
              <a className="btn btn-quiet" href={ad.link} target="_blank" rel="noreferrer">
                Open
              </a>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
