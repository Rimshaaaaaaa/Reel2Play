/**
 * Score sharing without personal data (feature 42). A player who finished can challenge a
 * friend: the link carries only the score, the goal and the time (?beat=7-10-18.4) and marks the play as
 * shared (from=share). No name, number or device goes anywhere; the friend's intro card says
 * "A friend scored 7 of 10 in 18.4 s".
 */

import type { Language } from "./config";

export interface Challenge {
  score: number;
  goal: number;
  seconds: number;
}

const BEAT = /^(\d{1,3})-(\d{1,3})-(\d{1,2}(?:\.\d)?)$/;

export function readChallenge(
  search: string = typeof location === "undefined" ? "" : location.search): Challenge | null {
  let value: string | null = null;
  try {
    value = new URLSearchParams(search).get("beat");
  } catch {
    return null;
  }
  const match = value ? BEAT.exec(value) : null;
  if (!match) return null;
  const score = Number(match[1]);
  const goal = Number(match[2]);
  const seconds = Number(match[3]);
  if (score > goal || seconds <= 0 || seconds > 60) return null;
  return { score, goal, seconds };
}

/** The game's own address with the score; null where the page has no web address (tests). */
export function challengeLink(href: string, challenge: Challenge): string | null {
  let url: URL;
  try {
    url = new URL(href);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return null;
  const layout = url.searchParams.get("layout");
  url.search = "";
  url.hash = "";
  if (layout === "square" || layout === "landscape") url.searchParams.set("layout", layout);
  url.searchParams.set("beat",
    `${challenge.score}-${challenge.goal}-${challenge.seconds.toFixed(1)}`);
  url.searchParams.set("from", "share");
  return url.toString();
}

export function challengeText(language: Language, product: string, challenge: Challenge): string {
  const { goal } = challenge;
  const seconds = challenge.seconds.toFixed(1);
  return language === "ur"
    ? `میں نے ${product} کی گیم میں ${seconds} سیکنڈ میں ${goal} میں سے ${challenge.score} بنائے۔ کیا آپ آگے نکل سکتے ہیں؟`
    : `I scored ${challenge.score} of ${goal} in ${seconds} s in the ${product} game. Can you beat me?`;
}

export function challengeIntro(language: Language, challenge: Challenge): string {
  const { goal } = challenge;
  const seconds = challenge.seconds.toFixed(1);
  return language === "ur"
    ? `ایک دوست نے ${seconds} سیکنڈ میں ${goal} میں سے ${challenge.score} بنائے۔ کیا آپ آگے نکل سکتے ہیں؟`
    : `A friend scored ${challenge.score} of ${goal} in ${seconds} s. Can you beat it?`;
}
