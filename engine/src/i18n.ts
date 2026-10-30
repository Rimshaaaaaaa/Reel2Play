/** The engine's own interface words, in Urdu and English (the shop's words come from config). */

import type { Language } from "./config";

const WORDS = {
  en: {
    play: "Tap to play",
    playAgain: "Play again",
    time: "Time",
    soundOn: "Sound on",
    soundOff: "Sound off",
    yourCode: "Your code",
    price: "Price",
    loading: "Loading…",
    captionsOn: "Sound captions on",
    captionsOff: "Sound captions off",
    soundCatch: "Caught!",
    soundMiss: "Missed",
    soundCoin: "Got it!",
    soundBump: "Oops",
    soundWin: "You did it!",
    soundJump: "Jump",
    soundSwap: "Swap",
    challenge: "Challenge a friend",
    optin: "Get this shop's offers on WhatsApp",
  },
  ur: {
    play: "کھیلنے کے لیے ٹیپ کریں",
    playAgain: "دوبارہ کھیلیں",
    time: "وقت",
    soundOn: "آواز آن",
    soundOff: "آواز بند",
    yourCode: "آپ کا کوڈ",
    price: "قیمت",
    loading: "لوڈ ہو رہا ہے…",
    captionsOn: "آواز کی سرخیاں آن",
    captionsOff: "آواز کی سرخیاں بند",
    soundCatch: "پکڑ لیا!",
    soundMiss: "چھوٹ گیا",
    soundCoin: "مل گیا!",
    soundBump: "اوہو",
    soundWin: "شاباش!",
    soundJump: "چھلانگ",
    soundSwap: "بدل دیا",
    challenge: "دوست کو چیلنج کریں",
    optin: "اس دکان کی آفرز واٹس ایپ پر پائیں",
  },
} as const;

export type WordKey = keyof (typeof WORDS)["en"];

export function words(language: Language): Record<WordKey, string> {
  return WORDS[language];
}

export function directionFor(language: Language): "rtl" | "ltr" {
  return language === "ur" ? "rtl" : "ltr";
}

/** System fonts only: a game page never downloads anything after it loads. */
export function fontStack(language: Language): string {
  return language === "ur"
    ? '"Noto Nastaliq Urdu", "Jameel Noori Nastaleeq", "Noto Naskh Arabic", "Geeza Pro", "Segoe UI", sans-serif'
    : 'ui-rounded, "SF Pro Rounded", "Segoe UI", Roboto, system-ui, sans-serif';
}
