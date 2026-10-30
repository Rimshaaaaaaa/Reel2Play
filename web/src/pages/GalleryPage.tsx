import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getGallery, type GalleryAd } from "../api";
import { percent } from "../format";
import "./GalleryPage.css";

/** The evaluated ads, each one playable (feature 61). */
export function GalleryPage() {
  const [ads, setAds] = useState<GalleryAd[] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    getGallery()
      .then(setAds)
      .catch(() => setError(true));
  }, []);
  return (
    <div className="gallery">
      <header className="gallery-intro">
        <h1>Gallery</h1>
        <p>
          Games made from real shops' videos during the evaluation, each tested before anyone
          played it. Tap one to play.
        </p>
        <Link to="/compare" className="btn btn-quiet">
          Help us test: game or picture?
        </Link>
      </header>
      {error ? (
        <p className="form-error" role="alert">
          The gallery could not be loaded. Check the connection and refresh.
        </p>
      ) : ads === null ? (
        <p role="status">Loading…</p>
      ) : ads.length === 0 ? (
        <p className="gallery-empty">
          The gallery fills up as the evaluation runs. Meanwhile, <Link to="/try">try a sample</Link>.
        </p>
      ) : (
        <ul className="tiles">
          {ads.map((ad) => (
            <li key={ad.id} className="card tile">
              <a href={ad.link} target="_blank" rel="noreferrer" className="tile-play">
                {ad.preview_url ? <img src={ad.preview_url} alt="" /> : <span />}
                <span className="tile-title" lang={ad.language} dir="auto">
                  {ad.product}
                </span>
              </a>
              <p className="tile-meta">
                {ad.category.replaceAll("_", " ")}, {ad.template ?? "game"},{" "}
                {ad.stats.plays} plays, {percent(ad.stats.completion)} finished
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
