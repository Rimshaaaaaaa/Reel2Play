/**
 * The page around the play field: intro card, timer and score, sound switch, and the end
 * card with the offer, the owner's price and the call to action. Built with DOM nodes and
 * textContent only, so nothing in the config can inject markup.
 */

import { challengeIntro, challengeLink, challengeText, readChallenge } from "./challenge";
import { darken, lighten } from "./color";
import type { GameConfig, Layout } from "./config";
import { fontStack, words } from "./i18n";
import { greeting } from "./theme";
import type { PlatformAdapter } from "./platform";

export const ATTRIBUTION = "Built with Muse Spark Open";

type Attrs = Record<string, string>;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Attrs = {},
  ...children: (Node | string | null)[]): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (name === "text") node.textContent = value;
    else node.setAttribute(name, value);
  }
  for (const child of children) {
    if (child !== null) node.append(child);
  }
  return node;
}

export interface EndResult {
  won: boolean;
  seconds: number;
  /** Feature 42: for a challenge link; a goal of 0 means the game has no score to share. */
  score?: number;
  goal?: number;
}

export interface Ui {
  stage: HTMLElement;
  canvas: HTMLCanvasElement;
  onStart(handler: () => void): void;
  onReplay(handler: () => void): void;
  setHud(timeLeft: number, total: number, score: number, goal: number): void;
  /** Show a sound as words for a moment (feature 23); `null` clears it. */
  caption(text: string | null): void;
  showPlaying(): void;
  showEnd(result: EndResult): void;
  /** Feature 40: show a unique win code, and put it in the order message too. */
  showCode(code: string): void;
}

function themeVars(config: GameConfig): string {
  const p = config.palette;
  return [
    `--r2p-bg:${p.background}`,
    `--r2p-surface:${p.surface}`,
    `--r2p-surface-edge:${darken(p.surface, 0.16)}`,
    `--r2p-primary:${p.primary}`,
    `--r2p-primary-hi:${lighten(p.primary, 0.12)}`,
    `--r2p-primary-edge:${darken(p.primary, 0.32)}`,
    `--r2p-primary-ink:${p.primaryInk}`,
    `--r2p-accent:${p.accent}`,
    `--r2p-accent-ink:${p.accentInk}`,
    `--r2p-ink:${p.ink}`,
    `--r2p-muted:${p.muted}`,
    `--r2p-font:${fontStack(config.language)}`,
  ].join(";");
}

/** Square and landscape pages (feature 18): the product and offer beside the play field. */
function sidePanel(config: GameConfig, productSrc: string): HTMLElement {
  const text = config.text;
  return el("aside", { class: "r2p-side", "data-r2p": "side" },
    el("img", { class: "r2p-side-hero", src: productSrc, alt: "" }),
    el("p", { class: "r2p-side-name", text: text.productName }),
    text.offer ? el("p", { class: "r2p-side-offer", text: text.offer }) : null,
    text.price ? el("p", { class: "r2p-side-price", text: text.price }) : null,
    el("p", { class: "r2p-side-hint", text: text.instruction }));
}

export function buildUi(root: HTMLElement, config: GameConfig, platform: PlatformAdapter,
  productSrc: string, layout: Layout = "portrait"): Ui {
  const t = words(config.language);
  const text = config.text;
  const challenge = platform.canShare ? readChallenge() : null;
  root.className = "r2p";
  root.setAttribute("dir", config.direction);
  root.setAttribute("lang", config.language);
  root.setAttribute("style", themeVars(config));

  const canvas = el("canvas", { "aria-label": text.title, role: "img" });
  const timerFill = el("span", { class: "r2p-timer-fill" });
  const timer = el("div", { class: "r2p-timer", role: "progressbar", "aria-label": t.time,
    "aria-valuemin": "0", "aria-valuemax": "100" }, timerFill);
  const score = el("div", { class: "r2p-score", "data-r2p": "score", "aria-live": "polite" });
  const mute = el("button", { class: "r2p-mute", type: "button", "aria-pressed": "false",
    "aria-label": t.soundOff, text: "♪" });
  const cc = el("button", { class: "r2p-cc", type: "button", "aria-pressed": "true",
    "aria-label": t.captionsOn, text: "CC" });
  const hud = el("div", { class: "r2p-hud", hidden: "" }, timer, score, cc, mute);
  const captionLine = el("p", { class: "r2p-caption", role: "status", "aria-live": "polite",
    "data-r2p": "caption", hidden: "" });

  const play = el("button", { class: "r2p-btn", type: "button", "data-r2p": "play", text: t.play });
  const hello = greeting(config.theme, config.language);
  const badge = () => (hello ? el("p", { class: "r2p-occasion", "data-theme": config.theme ?? "",
    text: hello }) : null);
  const intro = el("section", { class: "r2p-card r2p-intro", "data-r2p": "intro" },
    badge(),
    el("img", { class: "r2p-hero", src: productSrc, alt: text.productName }),
    el("h1", { text: text.title }),
    el("p", { text: text.instruction }),
    challenge ? el("p", { class: "r2p-challenge", "data-r2p": "challenge",
      text: challengeIntro(config.language, challenge) }) : null,
    play);

  const resultTitle = el("h2", { "data-r2p": "result" });
  const codeText = el("strong", { dir: "ltr", text: config.coupon ?? "" });
  const couponLine = config.coupon
    ? el("p", { class: "r2p-coupon", "data-r2p": "coupon" }, `${t.yourCode}: `, codeText)
    : null;
  const cta = platform.ctaHref
    ? el("a", { class: "r2p-btn", href: platform.ctaHref, target: "_blank", rel: "noopener",
      "data-r2p": "cta", text: text.ctaLabel })
    : el("button", { class: "r2p-btn", type: "button", "data-r2p": "cta", text: text.ctaLabel });
  const orderHref = cta.getAttribute("href");
  const replay = el("button", { class: "r2p-btn r2p-quiet", type: "button", "data-r2p": "replay",
    text: t.playAgain });
  const share = el("a", { class: "r2p-btn r2p-quiet", href: "#", target: "_blank",
    rel: "noopener", "data-r2p": "share", text: t.challenge, hidden: "" });
  let shared: { text: string; url: string } | null = null;
  const end = el("section", { class: "r2p-card r2p-end", "data-r2p": "end", hidden: "" },
    badge(),
    resultTitle,
    el("img", { class: "r2p-hero", src: productSrc, alt: text.productName }),
    el("p", { class: "r2p-product", text: text.productName }),
    text.offer ? el("p", { class: "r2p-offer", "data-r2p": "offer", text: text.offer }) : null,
    text.price ? el("p", { class: "r2p-price", "data-r2p": "price", text: text.price }) : null,
    couponLine,
    cta,
    el("div", { class: "r2p-row" }, replay, share),
    platform.optinUrl ? el("a", { class: "r2p-optin", href: platform.optinUrl, target: "_blank",
      rel: "noopener", "data-r2p": "optin", text: t.optin }) : null,
    el("p", { class: "r2p-attribution", lang: "en", dir: "ltr", text: ATTRIBUTION }));

  const stage = el("div", { class: "r2p-stage" }, canvas, hud, captionLine, intro, end);
  root.setAttribute("data-layout", layout);
  root.replaceChildren(
    layout === "portrait"
      ? stage
      : el("div", { class: "r2p-frame" }, sidePanel(config, productSrc), stage),
  );

  cta.addEventListener("click", () => platform.onCta());
  share.addEventListener("click", (event) => {
    platform.track("share");
    const nav = typeof navigator === "undefined" ? null : navigator;
    if (shared && nav && typeof nav.share === "function") {
      event.preventDefault();
      nav.share({ text: shared.text, url: shared.url }).catch(() => undefined);
    }
  });
  let captionsOn = true;
  cc.addEventListener("click", () => {
    captionsOn = !captionsOn;
    cc.setAttribute("aria-pressed", String(captionsOn));
    cc.setAttribute("aria-label", captionsOn ? t.captionsOn : t.captionsOff);
    if (!captionsOn) captionLine.hidden = true;
  });
  mute.addEventListener("click", () => {
    const muted = mute.getAttribute("aria-pressed") !== "true";
    mute.setAttribute("aria-pressed", String(muted));
    mute.setAttribute("aria-label", muted ? t.soundOn : t.soundOff);
    root.dispatchEvent(new CustomEvent("r2p:mute", { detail: muted }));
  });

  return {
    stage,
    canvas,
    onStart: (handler) => play.addEventListener("click", handler),
    onReplay: (handler) => replay.addEventListener("click", handler),
    setHud(timeLeft, total, value, goal) {
      const share = Math.max(0, Math.min(1, timeLeft / total));
      timerFill.style.transform = `scaleX(${share})`;
      timer.setAttribute("aria-valuenow", String(Math.round(share * 100)));
      score.textContent = goal > 0 ? `${value} / ${goal}` : String(value);
    },
    caption(words) {
      captionLine.textContent = words ?? "";
      captionLine.hidden = !words || !captionsOn;
    },
    showPlaying() {
      captionLine.hidden = true;
      intro.hidden = true;
      end.hidden = true;
      hud.hidden = false;
    },
    showEnd(result) {
      hud.hidden = true;
      captionLine.hidden = true;
      resultTitle.textContent = result.won ? text.win : text.lose;
      end.dataset.won = String(result.won);
      // Prizes are for winners: a lost round still shows the offer, but no code, and the
      // order message it opens carries no code either.
      if (couponLine) couponLine.hidden = !result.won;
      if (orderHref && config.coupon) {
        cta.setAttribute("href", result.won ? orderHref : withoutCode(orderHref, config.coupon));
      }
      const goal = Math.round(result.goal ?? 0);
      // document.URL, not the location object: Meta's review flags any location write-alike.
      const link = platform.canShare && goal > 0 && typeof document !== "undefined"
        ? challengeLink(document.URL, { score: Math.round(result.score ?? 0), goal,
          seconds: Math.round(result.seconds * 10) / 10 })
        : null;
      if (link) {
        const message = challengeText(config.language, text.productName,
          { score: Math.round(result.score ?? 0), goal, seconds: result.seconds });
        shared = { text: message, url: link };
        share.setAttribute("href", `https://wa.me/?text=${encodeURIComponent(`${message} ${link}`)}`);
        share.hidden = false;
      }
      end.hidden = false;
      (cta as HTMLElement).focus({ preventScroll: true });
    },
    showCode(code) {
      if (!couponLine || !config.coupon) return;
      codeText.textContent = code;
      couponLine.dataset.unique = "true";
      const href = cta.getAttribute("href");
      if (href) cta.setAttribute("href", href.split(config.coupon).join(code));
    },
  };
}

/** The order message's code line, as the API writes it (builder/cta.py CODE_LINES). */
const CODE_LABELS = [" My code: ", " میرا کوڈ: "];

/** The order link without the code line, for a round that was not won. */
export function withoutCode(href: string, code: string): string {
  const at = href.indexOf("?text=");
  if (at < 0) return href;
  let message: string;
  try {
    message = decodeURIComponent(href.slice(at + 6));
  } catch {
    return href;
  }
  for (const label of CODE_LABELS) message = message.split(label + code).join("");
  return href.slice(0, at + 6) + encodeURIComponent(message);
}
