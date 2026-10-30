/**
 * Where the game runs decides how the call to action works:
 * - hosted: the end card button is a normal link (WhatsApp chat or the shop's page);
 *   plays, finishes and button taps are counted without any personal data.
 * - meta: Meta playable ads. The button calls FbPlayableAd.onCTAClick() and nothing else:
 *   no links, no redirects, no network calls.
 */

import type { GameConfig } from "./config";

export type TrackEvent = "play" | "finish" | "cta" | "share";

export interface PlatformAdapter {
  /** A real link for the button, or null when the platform handles the tap itself. */
  ctaHref: string | null;
  /** Feature 42: only a published game page (it has an address to share) offers a challenge. */
  canShare: boolean;
  /** Feature 43: a WhatsApp link to ask for the shop's offers, when the shop takes sign-ups. */
  optinUrl: string | null;
  onCta(): void;
  track(event: TrackEvent, data?: { seconds?: number; won?: boolean }): void;
  /**
   * Feature 40: a unique coupon code for a win, from the API, or null (Meta playables, test
   * runs, no network). One code per page visit: a second win shows the same code.
   */
  winCode(): Promise<string | null>;
}

const WIN_CODE = /^R2P-[A-Z0-9]{4}-[A-Z0-9]{4}$/;
const WIN_CODE_WAIT_MS = 4000;

interface FbPlayable {
  onCTAClick(): void;
}

type Analytics = NonNullable<GameConfig["analytics"]>;

/**
 * Where to count events: the config's own setting, or a tag the hosted page adds to its
 * head when it is published. The tested game file has neither, so tests stay offline.
 */
export function pageAnalytics(): Analytics | null {
  if (typeof document === "undefined") return null;
  const content = document.querySelector('meta[name="r2p-analytics"]')?.getAttribute("content");
  if (!content) return null;
  try {
    const value = JSON.parse(content) as Partial<Analytics>;
    if (typeof value.endpoint !== "string" || typeof value.adId !== "string") return null;
    const found: Analytics = {
      endpoint: value.endpoint,
      adId: value.adId,
      variant: String(value.variant ?? "A"),
    };
    if (typeof value.coupons === "string") found.coupons = value.coupons;
    return found;
  } catch {
    return null;
  }
}

/** Feature 43: the sign-up link the game page carries when the shop takes sign-ups. */
export function pageOptin(): string | null {
  if (typeof document === "undefined") return null;
  const content = document.querySelector('meta[name="r2p-optin"]')?.getAttribute("content");
  if (!content) return null;
  try {
    const url = (JSON.parse(content) as { url?: unknown }).url;
    return typeof url === "string" && url.startsWith("https://wa.me/") ? url : null;
  } catch {
    return null;
  }
}

/**
 * Where this play started, from the page address (features 36 and 37): the counter
 * poster's QR code adds ?from=qr, a website embed adds ?from=embed. Nothing about the player.
 */
export function playSource(search: string = typeof location === "undefined" ? "" : location.search):
  "qr" | "embed" | "share" | null {
  try {
    const value = new URLSearchParams(search).get("from");
    return value === "qr" || value === "embed" || value === "share" ? value : null;
  } catch {
    return null;
  }
}

export function createPlatform(config: GameConfig): PlatformAdapter {
  if (config.platform === "meta") {
    return {
      ctaHref: null,
      canShare: false,
      optinUrl: null,
      onCta: () => (globalThis as { FbPlayableAd?: FbPlayable }).FbPlayableAd?.onCTAClick(),
      track: () => undefined,
      winCode: () => Promise.resolve(null),
    };
  }
  const analytics = config.analytics ?? pageAnalytics();
  const source = playSource();
  const track = (event: TrackEvent, data: { seconds?: number; won?: boolean } = {}) => {
    if (!analytics || typeof navigator === "undefined" || !navigator.sendBeacon) return;
    const body = JSON.stringify({ ad: analytics.adId, variant: analytics.variant, event, ...data,
      ...(source ? { from: source } : {}) });
    // Plain text keeps it a simple request: no preflight from the sandboxed page.
    navigator.sendBeacon(analytics.endpoint, new Blob([body], { type: "text/plain" }));
  };
  let asked: Promise<string | null> | null = null;
  const ask = async (endpoint: string, ad: string, variant: string): Promise<string | null> => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), WIN_CODE_WAIT_MS);
    try {
      const reply = await fetch(endpoint, {
        method: "POST",
        // Plain text keeps it a simple request; no cookies, nothing about the player.
        headers: { "Content-Type": "text/plain" },
        body: JSON.stringify({ ad, variant, ...(source ? { from: source } : {}) }),
        credentials: "omit",
        cache: "no-store",
        signal: controller.signal,
      });
      if (!reply.ok) return null;
      const value = (await reply.json()) as { code?: unknown };
      return typeof value.code === "string" && WIN_CODE.test(value.code) ? value.code : null;
    } catch {
      return null;
    } finally {
      clearTimeout(timer);
    }
  };
  const winCode = (): Promise<string | null> => {
    if (!analytics?.coupons || typeof fetch === "undefined") return Promise.resolve(null);
    asked ??= ask(analytics.coupons, analytics.adId, analytics.variant).then((code) => {
      if (code === null) asked = null; // try again on the next win
      return code;
    });
    return asked;
  };
  return {
    ctaHref: config.cta.url,
    canShare: config.platform === "hosted" && analytics !== null,
    optinUrl: config.platform === "hosted" ? pageOptin() : null,
    onCta: () => track("cta"),
    track,
    winCode,
  };
}
