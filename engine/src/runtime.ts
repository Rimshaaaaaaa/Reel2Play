/**
 * The shared runtime: builds the page, scales the canvas, feeds input and time to the
 * template, enforces the hard time limit, and always ends on the offer.
 */

import { Sfx, type SfxName } from "./audio";
import { type GameConfig, layoutFor, readConfig } from "./config";
import { H, setCalm, W } from "./draw";
import type { GameContext, Images, Outcome, TemplateFactory, TemplateGame } from "./game";
import { fontStack, words } from "./i18n";
import { createPlatform } from "./platform";
import { createRng } from "./random";
import { drawTheme } from "./theme";
import { buildUi } from "./ui";

export type Phase = "loading" | "intro" | "playing" | "ended";
const CAPTION_S = 0.9;

export interface DebugHooks {
  config: GameConfig;
  phase(): Phase;
  elapsed(): number;
  outcome(): Outcome | null;
  state(): Record<string, unknown>;
  runs(): number;
  firstFrameMs(): number | null;
  start(): void;
  /**
   * Manual clock for the play-tester and scripted players: while on, game time only moves
   * through advance(), so an agent can look, think and act without the game running on.
   */
  setManual(on: boolean): void;
  advance(seconds: number): void;
  /** Where a play-field point is on the screen, for real taps. */
  toScreen(x: number, y: number): { x: number; y: number };
}

declare global {
  interface Window {
    __r2p?: DebugHooks;
  }
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Reel2Play: an embedded image could not be read"));
    image.src = src;
  });
}

async function loadImages(config: GameConfig): Promise<Images> {
  const moving = config.assets.productFrames ?? null;
  const [product, productPhoto, logo, strip] = await Promise.all([
    loadImage(config.assets.product),
    config.assets.productPhoto ? loadImage(config.assets.productPhoto) : Promise.resolve(null),
    config.assets.logo ? loadImage(config.assets.logo) : Promise.resolve(null),
    moving ? loadImage(moving.strip) : Promise.resolve(null),
  ]);
  const productFrames = moving && strip ? { image: strip, frames: moving.frames, fps: moving.fps } : null;
  const more = await Promise.all((config.assets.moreProducts ?? []).map((p) => loadImage(p.image)));
  return { product, productPhoto, logo, productFrames, more };
}

/** Pointer position in play-field coordinates. */
export function toLogical(clientX: number, clientY: number, rect: DOMRect): { x: number; y: number } {
  return {
    x: ((clientX - rect.left) / rect.width) * W,
    y: ((clientY - rect.top) / rect.height) * H,
  };
}

export async function startGame(factory: TemplateFactory, config: GameConfig = readConfig(),
  root: HTMLElement = document.getElementById("app") ?? document.body): Promise<DebugHooks> {
  const platform = createPlatform(config);
  setCalm(globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  const ui = buildUi(root, config, platform, config.assets.product, layoutFor(config));
  const sfx = new Sfx();
  const images = await loadImages(config);
  const context2d = ui.canvas.getContext("2d");
  if (!context2d) throw new Error("Reel2Play: canvas is not available");
  const g: CanvasRenderingContext2D = context2d;

  let phase: Phase = "intro";
  let runs = 0;
  let outcome: Outcome | null = null;
  let firstFrameMs: number | null = null;
  let game: TemplateGame = factory();
  const ctx: GameContext = {
    config, rng: createRng(config.seed), sfx, images, font: fontStack(config.language), elapsed: 0,
  };
  game.init(ctx);

  const resize = () => {
    const rect = ui.stage.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 3);
    ui.canvas.width = Math.max(1, Math.round(rect.width * ratio));
    ui.canvas.height = Math.max(1, Math.round(rect.height * ratio));
  };
  resize();
  new ResizeObserver(resize).observe(ui.stage);

  const finish = (result: Outcome) => {
    phase = "ended";
    outcome = result;
    const won = result === "won";
    sfx.play(won ? "win" : "end");
    const progress = game.progress();
    ui.showEnd({ won, seconds: ctx.elapsed, score: progress.score, goal: progress.goal });
    platform.track("finish", { seconds: Math.round(ctx.elapsed * 10) / 10, won });
    if (won) {
      void platform.winCode().then((code) => {
        if (code && phase === "ended" && outcome === "won") ui.showCode(code);
      });
    }
  };

  const start = () => {
    runs += 1;
    game = factory();
    ctx.rng = createRng(config.seed + runs);
    ctx.elapsed = 0;
    outcome = null;
    game.init(ctx);
    phase = "playing";
    ui.showPlaying();
    platform.track("play");
  };

  root.addEventListener("pointerdown", () => sfx.unlock(), { capture: true });
  root.addEventListener("r2p:mute", (event) => {
    sfx.muted = (event as CustomEvent<boolean>).detail;
  });
  ui.onStart(() => {
    sfx.play("tap");
    start();
  });
  ui.onReplay(start);

  const forward = (phaseName: "down" | "move" | "up") => (event: PointerEvent) => {
    if (phase !== "playing") return;
    if (phaseName === "down") ui.canvas.setPointerCapture?.(event.pointerId);
    const point = toLogical(event.clientX, event.clientY, ui.canvas.getBoundingClientRect());
    game.pointer({ phase: phaseName, ...point }, ctx);
    event.preventDefault();
  };
  ui.canvas.addEventListener("pointerdown", forward("down"));
  ui.canvas.addEventListener("pointermove", forward("move"));
  ui.canvas.addEventListener("pointerup", forward("up"));

  // Feature 23: each sound also shows as words for a moment of game time.
  const t = words(config.language);
  const SOUND_WORDS: Partial<Record<SfxName, string>> = {
    catch: t.soundCatch, miss: t.soundMiss, coin: t.soundCoin, bump: t.soundBump,
    win: t.soundWin, jump: t.soundJump, swap: t.soundSwap,
  };
  let captionLeft = 0;
  sfx.onSound = (name) => {
    const said = SOUND_WORDS[name];
    if (!said || phase !== "playing") return;
    ui.caption(said);
    captionLeft = CAPTION_S;
  };

  const step = (dt: number) => {
    if (phase !== "playing") return;
    ctx.elapsed += dt;
    if (captionLeft > 0) {
      captionLeft -= dt;
      if (captionLeft <= 0) ui.caption(null);
    }
    game.update(dt, ctx);
    let result = game.outcome(ctx);
    if (result === "playing" && ctx.elapsed >= config.maxSeconds) {
      result = game.timeUp?.(ctx) ?? "lost";
    }
    const progress = game.progress();
    ui.setHud(config.maxSeconds - ctx.elapsed, config.maxSeconds, progress.score, progress.goal);
    if (result !== "playing") finish(result);
  };

  const render = () => {
    const scale = ui.canvas.width / W;
    g.setTransform(scale, 0, 0, scale, 0, 0);
    game.draw(g, ctx);
    drawTheme(g, config.theme, ctx.elapsed, config.palette.accent);
    firstFrameMs ??= performance.now();
  };

  let manual = false;
  let last = performance.now();
  const frame = (now: number) => {
    const dt = Math.min(0.05, Math.max(0, (now - last) / 1000)) * config.timeScale;
    last = now;
    if (!manual) step(dt);
    render();
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);

  const hooks: DebugHooks = {
    config,
    phase: () => phase,
    elapsed: () => ctx.elapsed,
    outcome: () => outcome,
    state: () => game.debugState(),
    runs: () => runs,
    firstFrameMs: () => firstFrameMs,
    start,
    setManual: (on) => {
      manual = on;
    },
    advance: (seconds) => {
      const tick = 1 / 60;
      for (let left = seconds; left > 1e-9 && phase === "playing"; left -= tick) {
        step(Math.min(tick, left));
      }
      render();
    },
    toScreen: (x, y) => {
      const rect = ui.canvas.getBoundingClientRect();
      return { x: rect.left + (x / W) * rect.width, y: rect.top + (y / H) * rect.height };
    },
  };
  window.__r2p = hooks;
  return hooks;
}
