import { useState } from "react";
import type { Captions, Embed, ShareOut } from "../api";
import "./ShareCard.css";

type Channel = "instagram" | "facebook" | "whatsapp_status";

const CHANNELS: { id: Channel; label: string }[] = [
  { id: "whatsapp_status", label: "WhatsApp Status" },
  { id: "instagram", label: "Instagram" },
  { id: "facebook", label: "Facebook" },
];

/** A button that copies text and says so for a moment. */
function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }
  return (
    <button type="button" className="btn btn-quiet copy" onClick={copy} data-copied={copied}>
      {copied ? "Copied" : label}
    </button>
  );
}

function CaptionTabs({ captions }: { captions: Captions }) {
  const [channel, setChannel] = useState<Channel>("whatsapp_status");
  const text = captions[channel];
  return (
    <div className="captions">
      <div className="tabs" role="tablist" aria-label="Where you will post">
        {CHANNELS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`tab-${id}`}
            aria-selected={channel === id}
            aria-controls="caption-panel"
            onClick={() => setChannel(id)}
          >
            {label}
          </button>
        ))}
      </div>
      <div id="caption-panel" role="tabpanel" aria-labelledby={`tab-${channel}`}>
        <p
          className="caption-text"
          lang={captions.language}
          dir={captions.language === "ur" ? "rtl" : "ltr"}
        >
          {text}
        </p>
        <CopyButton text={text} label="Copy caption" />
      </div>
    </div>
  );
}

/** Feature 18: the same tested game as a square or landscape page, and Reels to match. */
function OtherShapes({ share }: { share: ShareOut }) {
  const shapes = [
    {
      name: "Square",
      use: "Instagram and Facebook feeds",
      link: share.square_link,
      reel: share.square_reel_url,
      file: "reel-square.mp4",
    },
    {
      name: "Landscape",
      use: "your website and YouTube",
      link: share.landscape_link,
      reel: share.wide_reel_url,
      file: "reel-wide.mp4",
    },
  ].filter((shape) => shape.link || shape.reel);
  if (shapes.length === 0) return null;
  return (
    <div className="shapes">
      <h3>Other shapes</h3>
      <ul>
        {shapes.map((shape) => (
          <li key={shape.name} className="shape" data-shape={shape.name.toLowerCase()}>
            <span className="shape-icon" aria-hidden="true" />
            <div>
              <p className="shape-name">{shape.name}</p>
              <p className="shape-use">For {shape.use}</p>
            </div>
            <div className="shape-actions">
              {shape.link ? (
                <a className="btn btn-quiet" href={shape.link} target="_blank" rel="noreferrer">
                  Open game
                </a>
              ) : null}
              {shape.reel ? (
                <a className="btn btn-quiet" href={shape.reel} download={shape.file}>
                  Download Reel
                </a>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Feature 36: an A4 poster for the shop counter; its QR code was scanned back before saving. */
function CounterPoster({ share }: { share: ShareOut }) {
  if (!share.poster_url) return null;
  return (
    <div className="poster">
      {share.poster_preview_url ? (
        <a className="poster-sheet" href={share.poster_url} target="_blank" rel="noreferrer">
          <img src={share.poster_preview_url} alt="The counter poster: your product, offer and a QR code" />
        </a>
      ) : null}
      <div className="poster-copy">
        <h3>Counter poster</h3>
        <p>
          An A4 page with your offer and a QR code that opens the game. Print it for the counter
          or the shop window; plays from it are counted on their own.
        </p>
        <a className="btn btn-quiet" href={share.poster_url} download="poster.pdf">
          Download poster (PDF)
        </a>
      </div>
    </div>
  );
}

const EMBED_NAMES: Record<Embed["shape"], { label: string; use: string }> = {
  tall: { label: "Tall", use: "a side column, or a page people open on their phones" },
  wide: { label: "Wide", use: "a full-width section: the game beside your offer" },
};

/** Feature 37: the game on the shop's own website, as a short snippet to paste. */
function WebsiteEmbed({ embeds }: { embeds: Embed[] }) {
  const [shape, setShape] = useState<Embed["shape"]>("tall");
  const chosen = embeds.find((embed) => embed.shape === shape) ?? embeds[0];
  if (!chosen) return null;
  return (
    <div className="embed">
      <h3>Put it on your website</h3>
      <div className="tabs" role="tablist" aria-label="Shape on your website">
        {embeds.map((embed) => (
          <button
            key={embed.shape}
            type="button"
            role="tab"
            id={`embed-${embed.shape}`}
            aria-selected={embed.shape === chosen.shape}
            aria-controls="embed-panel"
            onClick={() => setShape(embed.shape)}
          >
            {EMBED_NAMES[embed.shape].label}
          </button>
        ))}
      </div>
      <div id="embed-panel" role="tabpanel" aria-labelledby={`embed-${chosen.shape}`}>
        <p className="embed-use">For {EMBED_NAMES[chosen.shape].use}. Paste it into an HTML or embed block.</p>
        <pre className="embed-code">
          <code>{chosen.code}</code>
        </pre>
        <CopyButton text={chosen.code} label="Copy code" />
      </div>
    </div>
  );
}

/** What a published ad leaves with: the link, the gameplay Reel, captions, and Meta files. */
export function ShareCard({ share }: { share: ShareOut }) {
  const metaFiles = [
    { url: share.meta_html_url, name: "Playable, one HTML file" },
    { url: share.meta_zip_url, name: "Playable as a ZIP" },
    { url: share.lead_in_url, name: "Lead-in video" },
  ].filter((file): file is { url: string; name: string } => Boolean(file.url));
  return (
    <section className="card share" aria-labelledby="share-title">
      <h2 id="share-title">Your game is live</h2>
      <div className="share-link">
        <a href={share.link} target="_blank" rel="noreferrer" className="link-text">
          {share.link.replace(/^https?:\/\//, "")}
        </a>
        <div className="link-actions">
          <CopyButton text={share.link} label="Copy link" />
          <a className="btn" href={share.link} target="_blank" rel="noreferrer">
            Open game
          </a>
        </div>
      </div>

      {share.reel_url ? (
        <div className="reel">
          <video
            src={share.reel_url}
            controls
            muted
            playsInline
            preload="metadata"
            poster={share.preview_url ?? undefined}
            aria-label="Gameplay Reel"
          />
          <div className="reel-copy">
            <h3>Gameplay Reel</h3>
            <p>
              {share.reel_seconds ? `${Math.round(share.reel_seconds)} seconds, ` : ""}
              recorded from the tester's winning run. Post it as a Reel or Story, or on your
              WhatsApp Status, with the link.
            </p>
            <a className="btn btn-quiet" href={share.reel_url} download="reel.mp4">
              Download Reel
            </a>
          </div>
        </div>
      ) : null}

      <OtherShapes share={share} />
      <CounterPoster share={share} />
      {share.embeds && share.embeds.length > 0 ? <WebsiteEmbed embeds={share.embeds} /> : null}

      {share.captions ? <CaptionTabs captions={share.captions} /> : null}

      {metaFiles.length > 0 ? (
        <details className="meta-files">
          <summary>For app developers: Meta playable files</summary>
          <p>
            For Meta App Installs campaigns. The button calls FbPlayableAd.onCTAClick(); preview
            it in Meta's playable preview tool before uploading.
          </p>
          <ul>
            {metaFiles.map((file) => (
              <li key={file.name}>
                <a href={file.url} download>
                  {file.name}
                </a>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
