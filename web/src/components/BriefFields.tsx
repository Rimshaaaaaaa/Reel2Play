import type { ReactNode } from "react";
import type { BriefValues } from "../api";
import "./BriefFields.css";

const OCCASIONS = [
  ["none", "None"],
  ["ramzan", "Ramzan"],
  ["eid", "Eid"],
  ["independence_day", "14 August"],
  ["wedding_season", "Wedding season"],
  ["winter_sale", "Winter sale"],
] as const;

interface Props {
  fields: BriefValues;
  set: <K extends keyof BriefValues>(key: K, value: BriefValues[K]) => void;
  /** Shown just before the consent box, such as the file picker. */
  children?: ReactNode;
  /** Feature 46: in a batch each product has its own price, typed next to its file. */
  pricePerProduct?: boolean;
}

/** Shop, order contact, price, offer, language and consent: asked the same way everywhere. */
export function BriefFields({ fields, set, children, pricePerProduct = false }: Props) {
  return (
    <>
      <label className="field">
        <span>Shop name</span>
        <input
          required
          maxLength={120}
          value={fields.shopName}
          onChange={(e) => set("shopName", e.target.value)}
          autoComplete="organization"
        />
      </label>

      <div className="field-row">
        <label className="field">
          <span>WhatsApp number for orders</span>
          <input
            inputMode="tel"
            placeholder="+92 300 1234567"
            value={fields.whatsappNumber}
            onChange={(e) => set("whatsappNumber", e.target.value)}
          />
          <small>Include your country code, like +92, +971 or +44.</small>
        </label>
        <label className="field">
          <span>Or your shop link</span>
          <input
            type="url"
            placeholder="https://"
            value={fields.shopUrl}
            onChange={(e) => set("shopUrl", e.target.value)}
          />
        </label>
      </div>

      <div className="field-row">
        {pricePerProduct ? null : (
          <label className="field">
            <span>Price</span>
            <input
              maxLength={40}
              placeholder="Rs 2,499"
              value={fields.price}
              onChange={(e) => set("price", e.target.value)}
            />
            <small>Shown exactly as you type it.</small>
          </label>
        )}
        <label className="field">
          <span>{pricePerProduct ? "Offer for every product (optional)" : "Offer (optional)"}</span>
          <input
            maxLength={200}
            placeholder="20% off this week"
            value={fields.offer}
            onChange={(e) => set("offer", e.target.value)}
          />
        </label>
      </div>

      <fieldset className="field">
        <legend>Game language</legend>
        <div className="choices">
          {(
            [
              ["auto", "Same as the video"],
              ["ur", "اردو"],
              ["en", "English"],
            ] as const
          ).map(([value, label]) => (
            <label key={value} className="choice">
              <input
                type="radio"
                name="language"
                value={value}
                checked={fields.language === value}
                onChange={() => set("language", value)}
              />
              <span lang={value === "ur" ? "ur" : undefined}>{label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="field">
        <legend>Occasion (optional)</legend>
        <div className="choices">
          {OCCASIONS.map(([value, label]) => (
            <label key={value} className="choice">
              <input
                type="radio"
                name="occasion"
                value={value}
                checked={(fields.occasion ?? "none") === value}
                onChange={() => set("occasion", value)}
              />
              <span>{label}</span>
            </label>
          ))}
        </div>
        <small>The game gets decorations and a greeting for it.</small>
      </fieldset>

      {children}

      <label className="consent">
        <input
          type="checkbox"
          checked={fields.rightsConfirmed}
          onChange={(e) => set("rightsConfirmed", e.target.checked)}
        />
        <span>
          {pricePerProduct
            ? "These videos and photos are mine to use for ads. I understand their sound will be removed and replaced with Reel2Play's own sound effects."
            : "This video is mine to use for ads. I understand its sound will be removed and replaced with Reel2Play's own sound effects."}
        </span>
      </label>
    </>
  );
}
