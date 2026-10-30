/**
 * Tap to reveal: the product stands on a turntable while glowing spots light up on it, one
 * after another. Tap a spot before it fades to learn something about the product; find
 * nearly all of them to win. Original artwork drawn in code: a soft turntable and spark rings.
 */

import {
  backdrop,
  darken,
  drawProduct,
  fitFont,
  type GameContext,
  H,
  lighten,
  type Outcome,
  type PointerInfo,
  param,
  roundRect,
  softShadow,
  Sparks,
  startGame,
  type TemplateGame,
  W,
  withAlpha,
} from "../../engine/src/index";

const STAGE = { cx: W / 2, cy: 330, w: 270, h: 300 };
const TAP_RADIUS = 34;
const FIRST_SPOT_S = 2.0; // the turntable turns once before the first spot

export interface Spot {
  x: number;
  y: number;
  /** Game time it lights up. */
  at: number;
  fact: string;
  state: "waiting" | "lit" | "found" | "missed";
  /** Seconds left showing its fact after it was found. */
  showing: number;
}

/** Where the product is drawn, so spots can sit on it. */
function productRect(ctx: GameContext): { x: number; y: number; w: number; h: number } {
  const img = ctx.images.product;
  const scale = Math.min(STAGE.w / img.width, STAGE.h / img.height);
  const w = img.width * scale;
  const h = img.height * scale;
  return { x: STAGE.cx - w / 2, y: STAGE.cy - h / 2, w, h };
}

/**
 * Points on the product itself: opaque pixels of the cut-out, spread apart. Falls back to a
 * ring around the centre when the image cannot be read.
 */
export function spotPoints(ctx: GameContext, count: number): { x: number; y: number }[] {
  const rect = productRect(ctx);
  const img = ctx.images.product;
  const candidates: { x: number; y: number }[] = [];
  try {
    const canvas = document.createElement("canvas");
    const step = Math.max(1, Math.round(Math.max(img.width, img.height) / 48));
    canvas.width = img.width;
    canvas.height = img.height;
    const c = canvas.getContext("2d");
    if (c) {
      c.drawImage(img, 0, 0);
      const data = c.getImageData(0, 0, img.width, img.height).data;
      for (let y = step; y < img.height - step; y += step) {
        for (let x = step; x < img.width - step; x += step) {
          if ((data[(y * img.width + x) * 4 + 3] ?? 0) > 200) {
            candidates.push({ x: rect.x + (x / img.width) * rect.w, y: rect.y + (y / img.height) * rect.h });
          }
        }
      }
    }
  } catch {
    // An unreadable image keeps the ring below.
  }
  const chosen: { x: number; y: number }[] = [];
  let spacing = Math.min(rect.w, rect.h) / 3;
  while (chosen.length < count && candidates.length > 0 && spacing > 8) {
    const pool = candidates.filter((p) => chosen.every((q) => Math.hypot(p.x - q.x, p.y - q.y) >= spacing));
    if (pool.length === 0) {
      spacing *= 0.8;
      continue;
    }
    chosen.push(ctx.rng.pick(pool));
  }
  for (let i = chosen.length; i < count; i++) {
    const angle = (i / count) * Math.PI * 2;
    chosen.push({ x: STAGE.cx + Math.cos(angle) * 70, y: STAGE.cy + Math.sin(angle) * 80 });
  }
  return chosen;
}

/** Words for the spots: the game's facts, or what the game already knows about the offer. */
function factsFor(ctx: GameContext): string[] {
  const given = (ctx.config.content?.facts ?? []).filter((f) => f.trim());
  if (given.length) return given;
  const t = ctx.config.text;
  return [t.productName, t.offer, t.price].filter((f): f is string => Boolean(f));
}

export function createSpots(): TemplateGame {
  let spots: Spot[] = [];
  let life = 3.2;
  let allowedMisses = 1;
  let ended = false;
  const sparks = new Sparks();

  const found = () => spots.filter((s) => s.state === "found").length;
  const missed = () => spots.filter((s) => s.state === "missed").length;

  const drawTurntable = (g: CanvasRenderingContext2D, ctx: GameContext) => {
    const p = ctx.config.palette;
    const y = STAGE.cy + STAGE.h / 2 + 18;
    softShadow(g, STAGE.cx, y + 26, 150, 22, 0.25);
    g.fillStyle = darken(p.surface, 0.22);
    g.beginPath();
    g.ellipse(STAGE.cx, y + 12, 140, 30, 0, 0, Math.PI * 2);
    g.fill();
    const top = g.createLinearGradient(0, y - 30, 0, y + 30);
    top.addColorStop(0, lighten(p.surface, 0.2));
    top.addColorStop(1, darken(p.surface, 0.06));
    g.fillStyle = top;
    g.beginPath();
    g.ellipse(STAGE.cx, y, 140, 30, 0, 0, Math.PI * 2);
    g.fill();
    // Slow marks on the platter show it turning.
    g.strokeStyle = withAlpha(p.primary, 0.35);
    g.lineWidth = 3;
    for (let i = 0; i < 3; i++) {
      const a = ctx.elapsed * 0.8 + (i * Math.PI * 2) / 3;
      g.beginPath();
      g.ellipse(STAGE.cx, y, 118, 24, 0, a, a + 0.5);
      g.stroke();
    }
  };

  const drawSpot = (g: CanvasRenderingContext2D, spot: Spot, ctx: GameContext) => {
    const p = ctx.config.palette;
    if (spot.state === "lit") {
      const age = ctx.elapsed - spot.at;
      const fade = Math.max(0, 1 - age / life);
      const pulse = 1 + Math.sin(age * 8) * 0.12;
      g.fillStyle = withAlpha(p.accent, 0.25 * fade + 0.1);
      g.beginPath();
      g.arc(spot.x, spot.y, 30 * pulse, 0, Math.PI * 2);
      g.fill();
      g.strokeStyle = withAlpha("#ffffff", 0.9);
      g.lineWidth = 3;
      g.beginPath();
      g.arc(spot.x, spot.y, 16 * pulse, 0, Math.PI * 2);
      g.stroke();
      // The time left runs round the ring.
      g.strokeStyle = p.accent;
      g.lineWidth = 4;
      g.beginPath();
      g.arc(spot.x, spot.y, 23, -Math.PI / 2, -Math.PI / 2 + fade * Math.PI * 2);
      g.stroke();
      g.fillStyle = "#ffffff";
      g.beginPath();
      g.arc(spot.x, spot.y, 6, 0, Math.PI * 2);
      g.fill();
    } else if (spot.state === "found") {
      g.fillStyle = p.accent;
      g.beginPath();
      g.arc(spot.x, spot.y, 9, 0, Math.PI * 2);
      g.fill();
      g.strokeStyle = p.accentInk;
      g.lineWidth = 2.5;
      g.beginPath();
      g.moveTo(spot.x - 4, spot.y);
      g.lineTo(spot.x - 1, spot.y + 3.5);
      g.lineTo(spot.x + 4.5, spot.y - 3.5);
      g.stroke();
    }
  };

  const drawFact = (g: CanvasRenderingContext2D, spot: Spot, ctx: GameContext) => {
    if (spot.showing <= 0) return;
    const p = ctx.config.palette;
    const alpha = Math.min(1, spot.showing * 3);
    g.globalAlpha = alpha;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.direction = ctx.config.direction;
    g.font = fitFont(g, spot.fact, 230, 20, ctx.font);
    const width = Math.min(260, g.measureText(spot.fact).width + 36);
    const y = Math.max(110, Math.min(H - 120, spot.y - 56));
    const x = Math.max(width / 2 + 10, Math.min(W - width / 2 - 10, spot.x));
    g.fillStyle = darken(p.primary, 0.25);
    roundRect(g, x - width / 2, y - 19, width, 42, 14);
    g.fill();
    g.fillStyle = p.primary;
    roundRect(g, x - width / 2, y - 22, width, 42, 14);
    g.fill();
    g.fillStyle = p.primaryInk;
    g.fillText(spot.fact, x, y - 1);
    g.globalAlpha = 1;
  };

  return {
    id: "spots",
    init(ctx) {
      const d = ctx.config.difficulty;
      const count = Math.round(param(d, "spots"));
      const every = param(d, "spot_every");
      life = param(d, "spot_life");
      allowedMisses = Math.round(param(d, "allowed_misses"));
      const facts = factsFor(ctx);
      spots = spotPoints(ctx, count).map((point, i) => ({
        ...point,
        at: FIRST_SPOT_S + i * every,
        fact: facts[i % Math.max(1, facts.length)] ?? "",
        state: "waiting",
        showing: 0,
      }));
      ended = false;
    },
    update(dt, ctx) {
      sparks.update(dt);
      for (const spot of spots) {
        spot.showing = Math.max(0, spot.showing - dt);
        if (spot.state === "waiting" && ctx.elapsed >= spot.at) {
          spot.state = "lit";
          ctx.sfx.play("tap");
        } else if (spot.state === "lit" && ctx.elapsed >= spot.at + life) {
          spot.state = "missed";
          ctx.sfx.play("miss");
        }
      }
      ended = spots.every((s) => s.state === "found" || s.state === "missed")
        && spots.every((s) => s.showing <= 0);
    },
    draw(g, ctx) {
      const p = ctx.config.palette;
      backdrop(g, p.background, [p.primary, p.accent], ctx.elapsed);
      drawTurntable(g, ctx);
      const bob = Math.sin(ctx.elapsed * 1.4) * 3;
      g.save();
      g.translate(0, bob);
      drawProduct(g, ctx.images, ctx.elapsed, STAGE.cx, STAGE.cy, STAGE.w, STAGE.h);
      for (const spot of spots) drawSpot(g, spot, ctx);
      g.restore();
      for (const spot of spots) drawFact(g, spot, ctx);
      // One dot per spot along the bottom: found, missed, still to come.
      const gap = 22;
      const left = W / 2 - ((spots.length - 1) * gap) / 2;
      spots.forEach((spot, i) => {
        g.fillStyle = spot.state === "found"
          ? p.accent
          : spot.state === "missed" ? withAlpha(p.ink, 0.25) : withAlpha(p.ink, 0.1);
        g.beginPath();
        g.arc(left + i * gap, H - 70, 7, 0, Math.PI * 2);
        g.fill();
      });
      sparks.draw(g);
    },
    pointer(event: PointerInfo, ctx) {
      if (event.phase !== "down") return;
      const bob = Math.sin(ctx.elapsed * 1.4) * 3;
      const spot = spots.find(
        (s) => s.state === "lit" && Math.hypot(s.x - event.x, s.y + bob - event.y) <= TAP_RADIUS,
      );
      if (!spot) return;
      spot.state = "found";
      spot.showing = 1.8;
      ctx.sfx.play("coin");
      const p = ctx.config.palette;
      sparks.burst(ctx.rng, spot.x, spot.y + bob, [p.primary, p.accent, "#ffffff"], 16, 200);
    },
    progress: () => ({ score: found(), goal: Math.max(1, spots.length - allowedMisses) }),
    outcome(): Outcome {
      if (missed() > allowedMisses) return "lost";
      return ended ? "won" : "playing";
    },
    debugState: () => ({
      spots: spots.map(({ x, y, at, state }) => ({ x, y, at, state })),
      life,
      allowedMisses,
    }),
  };
}

if (typeof window !== "undefined" && (window as { R2P_CONFIG?: unknown }).R2P_CONFIG) {
  void startGame(createSpots);
}
