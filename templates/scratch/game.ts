/**
 * Scratch card: a gift card with thick silver foil. Rub it off to reveal the product and the
 * shop's offer underneath. The foil is layered, so each spot needs a few passes; the card is
 * won once most of it is clear. Original artwork drawn in code: a ticket-edged card with a
 * holographic shimmer and a little coin that rides under the finger.
 */

import {
  backdrop,
  darken,
  drawProduct,
  fitFont,
  type GameContext,
  lighten,
  type Outcome,
  type PointerInfo,
  param,
  roundRect,
  Sparks,
  startGame,
  type TemplateGame,
  tile3d,
  W,
  withAlpha,
} from "../../engine/src/index";

export const CARD = { x: 36, y: 150, w: 288, h: 340 };
const FOIL = { x: CARD.x + 16, y: CARD.y + 16, w: CARD.w - 32, h: CARD.h - 70 };
const CELL = 12;
const COLS = Math.ceil(FOIL.w / CELL);
const ROWS = Math.ceil(FOIL.h / CELL);
const CELEBRATE_S = 1.2; // the prize stays in view before the end card
const TAP_DAB = 1.8;

export function createScratch(): TemplateGame {
  let foil: number[] = [];
  let lastStroke: number[] = [];
  let stroke = 0;
  let layers = 3;
  let brush = 18;
  let needed = 0.8;
  let timeLimit = 30;
  let revealed = false;
  let revealedFor = 0;
  let coin: { x: number; y: number } | null = null;
  let texture: HTMLCanvasElement | null = null;
  let maskCanvas: HTMLCanvasElement | null = null;
  let layerCanvas: HTMLCanvasElement | null = null;
  let last: { x: number; y: number } | null = null;
  let moved = false;
  let strokes = 0;
  const sparks = new Sparks();

  const clearShare = () => foil.filter((t) => t <= 0).length / foil.length;
  // How far along the player is, counting every layer rubbed off (for the meter).
  const rubbedShare = () => foil.reduce((sum, t) => sum + (layers - Math.max(0, t)), 0)
    / (foil.length * layers);
  const meter = () => (revealed ? 1 : Math.min(0.99, rubbedShare() / needed));

  const rub = (x: number, y: number, ctx: GameContext, depth = 1) => {
    const c0 = Math.max(0, Math.floor((x - brush - FOIL.x) / CELL));
    const c1 = Math.min(COLS - 1, Math.floor((x + brush - FOIL.x) / CELL));
    const r0 = Math.max(0, Math.floor((y - brush - FOIL.y) / CELL));
    const r1 = Math.min(ROWS - 1, Math.floor((y + brush - FOIL.y) / CELL));
    let hit = false;
    for (let r = r0; r <= r1; r++) {
      for (let c = c0; c <= c1; c++) {
        const cx = FOIL.x + (c + 0.5) * CELL;
        const cy = FOIL.y + (r + 0.5) * CELL;
        const index = r * COLS + c;
        // One layer per stroke: rubbing the same spot in one go does not dig deeper.
        if (Math.hypot(cx - x, cy - y) > brush || lastStroke[index] === stroke) continue;
        if ((foil[index] ?? 0) <= 0) continue;
        foil[index] = (foil[index] ?? 0) - depth;
        lastStroke[index] = stroke;
        hit = true;
      }
    }
    if (hit && ctx.rng.next() < 0.25) {
      sparks.burst(ctx.rng, x, y, ["#e9edf2", "#c9d1db", "#ffffff"], 3, 90);
    }
  };

  const rubLine = (from: { x: number; y: number }, to: { x: number; y: number },
    ctx: GameContext) => {
    const steps = Math.max(1, Math.ceil(Math.hypot(to.x - from.x, to.y - from.y) / 6));
    for (let i = 1; i <= steps; i++) {
      rub(from.x + ((to.x - from.x) * i) / steps, from.y + ((to.y - from.y) * i) / steps, ctx);
    }
  };

  const drawPrize = (g: CanvasRenderingContext2D, ctx: GameContext) => {
    const p = ctx.config.palette;
    const glow = g.createRadialGradient(W / 2, FOIL.y + FOIL.h * 0.42, 10, W / 2,
      FOIL.y + FOIL.h * 0.42, FOIL.w * 0.7);
    glow.addColorStop(0, lighten(p.accent, 0.45));
    glow.addColorStop(1, lighten(p.primary, 0.55));
    g.fillStyle = glow;
    roundRect(g, FOIL.x, FOIL.y, FOIL.w, FOIL.h, 12);
    g.fill();
    drawProduct(g, ctx.images, ctx.elapsed, W / 2, FOIL.y + FOIL.h * 0.42, FOIL.w * 0.7,
      FOIL.h * 0.62);
    const words = ctx.config.text.offer ?? ctx.config.text.productName;
    g.fillStyle = p.ink;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.direction = ctx.config.direction;
    g.font = fitFont(g, words, FOIL.w - 24, 24, ctx.font);
    g.fillText(words, W / 2, FOIL.y + FOIL.h - 30);
  };

  /** The foil's look, drawn once: brushed silver with a diagonal sheen and tiny coins. */
  const makeTexture = (ctx: GameContext): HTMLCanvasElement => {
    const canvas = document.createElement("canvas");
    canvas.width = FOIL.w;
    canvas.height = FOIL.h;
    const c = canvas.getContext("2d");
    if (!c) return canvas;
    const base = c.createLinearGradient(0, 0, FOIL.w, FOIL.h);
    base.addColorStop(0, "#c9ced6");
    base.addColorStop(0.45, "#eef1f5");
    base.addColorStop(0.55, "#d3d8e0");
    base.addColorStop(1, "#aeb5bf");
    c.fillStyle = base;
    c.fillRect(0, 0, FOIL.w, FOIL.h);
    c.strokeStyle = "rgba(255, 255, 255, 0.18)";
    c.lineWidth = 1;
    for (let y = 2; y < FOIL.h; y += 3) {
      c.beginPath();
      c.moveTo(0, y + ctx.rng.range(-0.5, 0.5));
      c.lineTo(FOIL.w, y + ctx.rng.range(-0.5, 0.5));
      c.stroke();
    }
    c.fillStyle = "rgba(120, 128, 140, 0.22)";
    for (let y = 26; y < FOIL.h; y += 52) {
      for (let x = (y / 52) % 2 === 0 ? 26 : 52; x < FOIL.w; x += 52) {
        c.beginPath();
        c.arc(x, y, 9, 0, Math.PI * 2);
        c.fill();
      }
    }
    return canvas;
  };

  /** What is left of the foil: each cell's thickness as alpha, smoothly scaled up. */
  const drawFoil = (g: CanvasRenderingContext2D, ctx: GameContext) => {
    if (!texture || !layerCanvas || !maskCanvas) return;
    const m = maskCanvas.getContext("2d");
    const l = layerCanvas.getContext("2d");
    if (!m || !l) return;
    const pixels = m.createImageData(COLS, ROWS);
    foil.forEach((left, i) => {
      pixels.data[i * 4 + 3] = Math.round(Math.max(0, left / layers) * 255);
    });
    m.putImageData(pixels, 0, 0);
    l.globalCompositeOperation = "copy";
    l.drawImage(texture, 0, 0);
    // A soft light sweeps across the foil.
    l.globalCompositeOperation = "source-atop";
    const sweep = ((ctx.elapsed * 0.35) % 1.6) * FOIL.w - FOIL.w * 0.3;
    const sheen = l.createLinearGradient(sweep - 60, 0, sweep + 60, FOIL.h);
    sheen.addColorStop(0, "rgba(255, 255, 255, 0)");
    sheen.addColorStop(0.5, "rgba(255, 255, 255, 0.35)");
    sheen.addColorStop(1, "rgba(255, 255, 255, 0)");
    l.fillStyle = sheen;
    l.fillRect(0, 0, FOIL.w, FOIL.h);
    l.globalCompositeOperation = "destination-in";
    l.imageSmoothingEnabled = true;
    l.drawImage(maskCanvas, 0, 0, COLS * CELL, ROWS * CELL);
    g.drawImage(layerCanvas, FOIL.x, FOIL.y);
  };

  const drawCoin = (g: CanvasRenderingContext2D, ctx: GameContext) => {
    if (!coin) return;
    const p = ctx.config.palette;
    g.save();
    g.translate(coin.x + 14, coin.y + 18);
    g.rotate(-0.4);
    g.fillStyle = darken(p.accent, 0.3);
    g.beginPath();
    g.ellipse(0, 3, 15, 15, 0, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = p.accent;
    g.beginPath();
    g.ellipse(0, 0, 15, 15, 0, 0, Math.PI * 2);
    g.fill();
    g.strokeStyle = withAlpha("#ffffff", 0.6);
    g.lineWidth = 2;
    g.beginPath();
    g.arc(0, 0, 9, 0, Math.PI * 2);
    g.stroke();
    g.restore();
  };

  return {
    id: "scratch",
    init(ctx) {
      const d = ctx.config.difficulty;
      layers = Math.round(param(d, "layers"));
      brush = param(d, "brush");
      needed = param(d, "reveal_share");
      timeLimit = param(d, "time_limit");
      foil = Array.from({ length: COLS * ROWS }, () => layers);
      lastStroke = Array.from({ length: COLS * ROWS }, () => -1);
      stroke = 0;
      strokes = 0;
      revealed = false;
      revealedFor = 0;
      coin = null;
      last = null;
      texture = makeTexture(ctx);
      maskCanvas = document.createElement("canvas");
      maskCanvas.width = COLS;
      maskCanvas.height = ROWS;
      layerCanvas = document.createElement("canvas");
      layerCanvas.width = FOIL.w;
      layerCanvas.height = FOIL.h;
    },
    update(dt, ctx) {
      sparks.update(dt);
      if (revealed) revealedFor += dt;
      if (!revealed && clearShare() >= needed) {
        revealed = true;
        foil = foil.map(() => 0);
        ctx.sfx.play("win");
        const p = ctx.config.palette;
        sparks.burst(ctx.rng, W / 2, FOIL.y + FOIL.h / 2, [p.primary, p.accent, "#ffffff"], 50, 260);
      }
    },
    draw(g, ctx) {
      const p = ctx.config.palette;
      backdrop(g, p.background, [p.primary, p.accent], ctx.elapsed);
      tile3d(g, CARD.x, CARD.y, CARD.w, CARD.h, p.primary, { radius: 22, edge: 10 });
      // Ticket notches on both sides.
      g.fillStyle = withAlpha(p.background, 0.9);
      for (const side of [CARD.x, CARD.x + CARD.w]) {
        g.beginPath();
        g.arc(side, CARD.y + CARD.h - 40, 12, 0, Math.PI * 2);
        g.fill();
      }
      drawPrize(g, ctx);
      drawFoil(g, ctx);
      g.strokeStyle = withAlpha("#ffffff", 0.5);
      g.lineWidth = 2;
      roundRect(g, FOIL.x, FOIL.y, FOIL.w, FOIL.h, 12);
      g.stroke();
      const label = `${Math.round(meter() * 100)}%`;
      g.fillStyle = p.primaryInk;
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.font = fitFont(g, label, 120, 22, ctx.font);
      g.fillText(label, W / 2, CARD.y + CARD.h - 27);
      sparks.draw(g);
      drawCoin(g, ctx);
    },
    pointer(event: PointerInfo, ctx) {
      if (revealed) return;
      const point = { x: event.x, y: event.y };
      if (event.phase === "down") {
        moved = false;
        stroke += 1;
        strokes += 1;
        last = point;
        coin = point;
        rub(point.x, point.y, ctx);
        ctx.sfx.play("tap");
      } else if (event.phase === "move" && last) {
        moved ||= Math.hypot(point.x - last.x, point.y - last.y) > 4;
        rubLine(last, point, ctx);
        last = point;
        coin = point;
      } else {
        // Tap-only play (feature 23): a tap without a swipe clears a wider spot right through.
        if (last && !moved) {
          const before = brush;
          brush = before * TAP_DAB;
          stroke += 1;
          rub(last.x, last.y, ctx, layers);
          brush = before;
        }
        last = null;
        coin = null;
      }
    },
    progress: () => ({ score: Math.round(meter() * 10), goal: 10 }),
    outcome(ctx): Outcome {
      if (revealed) return revealedFor >= CELEBRATE_S ? "won" : "playing";
      return ctx.elapsed >= timeLimit ? "lost" : "playing";
    },
    timeUp() {
      foil = foil.map(() => 0);
      return "lost";
    },
    debugState: () => ({
      card: { ...FOIL },
      clear: Number(clearShare().toFixed(3)),
      needed,
      layers,
      brush,
      strokes,
      revealed,
      timeLimit,
    }),
  };
}

if (typeof window !== "undefined" && (window as { R2P_CONFIG?: unknown }).R2P_CONFIG) {
  void startGame(createScratch);
}
