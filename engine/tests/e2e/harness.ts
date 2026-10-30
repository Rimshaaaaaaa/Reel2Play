/**
 * Builds a game page from dist/ the same way the Python builder does: the HTML shell with
 * its {{PLACEHOLDERS}} filled, using the synthetic fixtures as the product.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Page } from "@playwright/test";
import type { GameConfig } from "../../src/config";

const here = path.dirname(fileURLToPath(import.meta.url));
const dist = path.resolve(here, "../../dist");
const fixtures = path.resolve(here, "../../../fixtures/synthetic");

const dataUrl = (file: string, type: string) =>
  `data:${type};base64,${readFileSync(path.join(fixtures, file)).toString("base64")}`;

const templates = path.resolve(here, "../../../templates");

/** A template's parameters at one difficulty tier, as the builder resolves them. */
export function tier(template: string, level: "easy" | "normal" | "hard" = "normal"): Record<string, number> {
  const spec = JSON.parse(readFileSync(path.join(templates, template, "template.json"), "utf8")) as {
    params: Record<string, Record<string, number>>;
  };
  return Object.fromEntries(Object.entries(spec.params).map(([name, values]) => [name, values[level]!]));
}

/** Game seconds per tap for a person playing this template (template.json, default 0.35). */
export function pace(template: string): number {
  const spec = JSON.parse(readFileSync(path.join(templates, template, "template.json"), "utf8")) as {
    tester_pace_seconds?: number;
  };
  return spec.tester_pace_seconds ?? 0.35;
}

export function testConfig(template: string, overrides: Partial<GameConfig> = {}): GameConfig {
  return {
    version: 1,
    template,
    language: "en",
    direction: "ltr",
    seed: 7,
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
      title: "Catch the Sneaker!",
      instruction: "Slide the bag to catch 10 sneakers.",
      win: "You won 20% off!",
      lose: "So close! Your offer is still here.",
      ctaLabel: "Order on WhatsApp",
      productName: "Canvas sneaker (synthetic)",
      offer: "20% off this week",
      price: "Rs 2,499",
    },
    assets: {
      product: dataUrl("synthetic-sprite.png", "image/png"),
      productPhoto: dataUrl("synthetic-photo.jpg", "image/jpeg"),
      logo: null,
    },
    difficulty: tier(template),
    cta: { kind: "whatsapp", url: "https://wa.me/923001234567?text=Hi%20I%20want%20the%20sneaker" },
    coupon: "R2PTEST",
    maxSeconds: 30,
    timeScale: 1,
    analytics: null,
    // Synthetic words for the templates that need them, labelled as test data.
    content: {
      facts: ["Synthetic: soft canvas", "Synthetic: rubber sole", "Synthetic: six colours"],
      quiz: [
        { question: "What is the synthetic sneaker made of?", options: ["Canvas", "Glass", "Paper"], answer: 0 },
        { question: "Which part is rubber?", options: ["The laces", "The sole", "The box"], answer: 1 },
        { question: "What is the offer?", options: ["Free socks", "Buy one", "20% off this week"], answer: 2 },
      ],
    },
    ...overrides,
  };
}

/** A synthetic moving product (feature 7): six square frames of a box turning. */
export function movingProduct(): { strip: string; frames: number; fps: number } {
  return { strip: dataUrl("synthetic-strip.png", "image/png"), frames: 6, fps: 6 };
}

/** JSON that is safe inside a <script> element. */
export function scriptJson(value: unknown): string {
  return JSON.stringify(value)
    .replaceAll("<", "\\u003c")
    .replaceAll(" ", "\\u2028")
    .replaceAll(" ", "\\u2029");
}

/** The example mechanic (feature 24), written for tests: templates/custom/example-mechanic.txt. */
export const EXAMPLE_MECHANIC = readFileSync(path.join(templates, "custom", "example-mechanic.txt"), "utf8");

/** The <script> block the builder writes for a checked mechanic (api/builder/mechanic.py). */
function mechanicHead(script: string): string {
  const hooks = ["setup", "update", "draw", "tap", "drag", "hint"]
    .map((name) => `${name}: typeof ${name} === "function" ? ${name} : undefined`)
    .join(", ");
  return '<script>Object.defineProperty(Function.prototype, "constructor", { value: undefined });\n' +
    `window.__r2pMechanic = (function () {\n"use strict";\n${script}\nreturn {${hooks}};\n})();</script>`;
}

export function gameHtml(config: GameConfig): string {
  const read = (file: string) => readFileSync(path.join(dist, file), "utf8");
  const fill: Record<string, string> = {
    LANG: config.language,
    DIR: config.direction,
    TITLE: config.text.title,
    HEAD: config.content?.mechanic ? mechanicHead(config.content.mechanic) : "",
    STYLE: read("game.css"),
    CONFIG: scriptJson(config),
    SCRIPT: read(`${config.template}.js`),
  };
  return read("shell.html").replace(/\{\{([A-Z]+)\}\}/g, (_, key: string) => fill[key] ?? "");
}

export interface Watch {
  errors: string[];
  requests: string[];
}

/** Open a game page and record console errors and any network request. */
export async function openGame(page: Page, config: GameConfig): Promise<Watch> {
  const watch: Watch = { errors: [], requests: [] };
  page.on("console", (message) => {
    if (message.type() === "error") watch.errors.push(message.text());
  });
  page.on("pageerror", (error) => watch.errors.push(error.message));
  page.on("request", (request) => {
    if (!request.url().startsWith("data:")) watch.requests.push(request.url());
  });
  await page.setContent(gameHtml(config));
  await page.waitForFunction(() => window.__r2p?.phase() === "intro");
  return watch;
}

/** Drag a finger between two play-field points, through a few moves on the way. */
export async function dragAt(page: Page, x1: number, y1: number, x2: number, y2: number): Promise<void> {
  const [from, to] = await page.evaluate(
    ([a, b, c, d]) => [window.__r2p!.toScreen(a!, b!), window.__r2p!.toScreen(c!, d!)],
    [x1, y1, x2, y2],
  );
  await page.mouse.move(from!.x, from!.y);
  await page.mouse.down();
  await page.mouse.move(to!.x, to!.y, { steps: 6 });
  await page.mouse.up();
}

export async function tapAt(page: Page, x: number, y: number): Promise<void> {
  const point = await page.evaluate(([lx, ly]) => window.__r2p!.toScreen(lx!, ly!), [x, y]);
  await page.mouse.move(point.x, point.y);
  await page.mouse.down();
  await page.mouse.up();
}

/** Pause the game clock, then press play, so no real time leaks into the run. */
export async function startManual(page: Page): Promise<void> {
  await page.evaluate(() => window.__r2p!.setManual(true));
  await page.locator('[data-r2p="play"]').click();
}

export const advance = (page: Page, seconds: number) =>
  page.evaluate((s) => window.__r2p!.advance(s), seconds);
