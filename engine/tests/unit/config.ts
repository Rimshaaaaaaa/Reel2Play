import type { GameConfig } from "../../src/config";

/** A small valid config for unit tests (synthetic values). */
export function testConfig(overrides: Partial<GameConfig> = {}): GameConfig {
  return {
    version: 1,
    template: "catch",
    language: "en",
    direction: "ltr",
    seed: 1,
    platform: "hosted",
    palette: {
      background: "#e9ecef",
      surface: "#fbfbfd",
      primary: "#c8243a",
      primaryInk: "#ffffff",
      accent: "#f2b705",
      accentInk: "#23232e",
      ink: "#23232e",
      muted: "#5d5f6e",
    },
    text: {
      title: "Catch",
      instruction: "Catch it",
      win: "You won!",
      lose: "Nice try!",
      ctaLabel: "Order",
      productName: "Sneaker",
      offer: "20% off",
      price: "Rs 2,499",
    },
    assets: { product: "data:image/png;base64,AA==", productPhoto: null, logo: null },
    difficulty: { goal: 10 },
    cta: { kind: "whatsapp", url: "https://wa.me/923001234567?text=Hi" },
    coupon: "R2PTEST",
    maxSeconds: 30,
    timeScale: 1,
    analytics: null,
    ...overrides,
  };
}
