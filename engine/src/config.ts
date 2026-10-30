/**
 * The game config the builder embeds in every page. The Python builder
 * (api/src/reel2play/builder/config.py) produces exactly this shape.
 */

import type { Theme } from "./theme";

export type Language = "ur" | "en";
export type Platform = "hosted" | "meta" | "preview";

export interface Palette {
  /** Page and play-field base: a neutral tint of the brand. */
  background: string;
  /** Raised surfaces: cards, tiles, ground. */
  surface: string;
  /** The brand's main colour: the hero, the bag, buttons. */
  primary: string;
  /** Text and icons drawn on `primary`. */
  primaryInk: string;
  /** Second brand colour: coupons, highlights. */
  accent: string;
  /** Text and icons drawn on `accent`. */
  accentInk: string;
  /** Body text on `background` and `surface`. */
  ink: string;
  muted: string;
}

export interface GameText {
  title: string;
  instruction: string;
  win: string;
  lose: string;
  ctaLabel: string;
  productName: string;
  offer: string | null;
  /** Exactly as the shop owner typed it; never changed by the game. */
  price: string | null;
}

export type Layout = "portrait" | "square" | "landscape";
export const LAYOUTS: readonly Layout[] = ["portrait", "square", "landscape"];

export interface GameConfig {
  version: 1;
  template: string;
  language: Language;
  direction: "rtl" | "ltr";
  seed: number;
  platform: Platform;
  palette: Palette;
  text: GameText;
  assets: {
    /** Transparent product cut-out (data URL). */
    product: string;
    /** Square product picture for the puzzle (data URL). */
    productPhoto: string | null;
    logo: string | null;
    /** The product moving (feature 7): square frames side by side in one image. */
    productFrames?: { strip: string; frames: number; fps: number } | null;
    /** The shop's other products (feature 11), for games that show several. */
    moreProducts?: { image: string; name: string }[];
  };
  /** Template parameters after the builder clamped them to the template's ranges. */
  difficulty: Record<string, number>;
  cta: { kind: "whatsapp" | "link"; url: string };
  coupon: string | null;
  /** Hard stop for every game, in seconds. */
  maxSeconds: number;
  /** Game-time speed-up, for automated tests only. */
  timeScale: number;
  /** Where a hosted page counts events, and (feature 40) asks for a unique win code. */
  analytics: { endpoint: string; adId: string; variant: string; coupons?: string } | null;
  /** A seasonal theme (feature 22): decorations and a greeting on the cards. */
  theme?: Theme;
  /** The page's shape (feature 18); the play field itself is always 9:16. */
  layout?: Layout;
  /** Words some templates need (feature 13): facts to reveal, quiz questions. */
  content?: {
    facts?: string[];
    quiz?: { question: string; options: string[]; answer: number }[];
    /** Feature 24: a new mechanic's script. The builder runs it in its own <script> block;
     * the engine never evaluates text. */
    mechanic?: string | null;
  };
}

export function readConfig(source: unknown = (globalThis as { R2P_CONFIG?: unknown }).R2P_CONFIG): GameConfig {
  if (!source || typeof source !== "object") {
    throw new Error("Reel2Play: no game config on the page");
  }
  const config = source as GameConfig;
  if (config.version !== 1 || !config.template || !config.assets?.product) {
    throw new Error("Reel2Play: the game config is incomplete");
  }
  return config;
}

/**
 * The shape to show: the page address (?layout=square) wins, then the test harness, then the
 * config. Meta playables are always portrait.
 */
export function layoutFor(config: GameConfig, search = globalThis.location?.search ?? "",
  forced = (globalThis as { R2P_LAYOUT?: unknown }).R2P_LAYOUT): Layout {
  if (config.platform === "meta") return "portrait";
  const asked = new URLSearchParams(search).get("layout") ?? forced ?? config.layout;
  return LAYOUTS.includes(asked as Layout) ? (asked as Layout) : "portrait";
}
