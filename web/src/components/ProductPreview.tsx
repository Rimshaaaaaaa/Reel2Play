import type { CSSProperties } from "react";
import type { AdOut } from "../api";
import "./ProductPreview.css";

/**
 * The cut-out before the game is built: moving when the video showed the product turning
 * (feature 7), with the shop's other products beside it (feature 11).
 */
export function ProductPreview({ sprites }: { sprites: AdOut["sprites"] }) {
  const main = sprites.find((s) => s.product_index === 0) ?? sprites[0];
  if (!main) return null;
  const others = sprites.filter((s) => s.product_index > 0);
  const moving = main.strip_url && main.strip_frames >= 2;
  return (
    <div className="product-preview">
      {moving ? (
        <div
          className="sprite sprite-moving"
          role="img"
          aria-label="Your product, cut out and moving"
          style={
            {
              backgroundImage: `url("${main.strip_url}")`,
              "--frames": main.strip_frames,
            } as CSSProperties
          }
        />
      ) : (
        <img className="sprite" src={main.url} alt="Your product, cut out" />
      )}
      {others.length ? (
        <ul className="product-others" aria-label="Your other products">
          {others.map((s) => (
            <li key={s.url}>
              <img src={s.url} alt="" />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
