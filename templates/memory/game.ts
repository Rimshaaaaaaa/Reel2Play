/**
 * Memory match: cards lie face down on raised 3D tiles. Flip two at a time to find the pairs:
 * the shop's products, or the product in the shop's colours. Every card is shown for a moment
 * at the start. Original artwork drawn in code: each card back carries a little folded-ribbon
 * badge in the shop's colour.
 */

import {
  backdrop,
  darken,
  drawFit,
  drawProduct,
  type GameContext,
  lighten,
  mix,
  type Outcome,
  type PointerInfo,
  param,
  recoloured,
  roundRect,
  Sparks,
  startGame,
  type TemplateGame,
  tile3d,
  W,
  withAlpha,
} from "../../engine/src/index";

const AREA = { x: 22, y: 128, w: 316, h: 448 };
const GAP = 12;
const FLIP_S = 0.22;
const CELEBRATE_S = 0.8;

export interface Card {
  face: number;
  x: number;
  y: number;
  w: number;
  h: number;
  up: boolean;
  matched: boolean;
  /** Seconds left in the flip animation. */
  turning: number;
}

/** Card positions for `count` cards: three or four across, the last row centred. */
export function layout(count: number): { x: number; y: number; w: number; h: number }[] {
  const cols = count % 3 === 0 ? 3 : 4;
  const rows = Math.ceil(count / cols);
  const w = Math.min((AREA.w - GAP * (cols - 1)) / cols, 96);
  const h = Math.min((AREA.h - GAP * (rows - 1)) / rows, w * 1.18);
  const top = AREA.y + (AREA.h - (rows * h + (rows - 1) * GAP)) / 2;
  return Array.from({ length: count }, (_, i) => {
    const row = Math.floor(i / cols);
    const inRow = Math.min(cols, count - row * cols);
    const left = (W - (inRow * w + (inRow - 1) * GAP)) / 2;
    return { x: left + (i % cols) * (w + GAP), y: top + row * (h + GAP), w, h };
  });
}

/** Colours that tell the pairs apart, all from the shop's palette. */
function faceColours(ctx: GameContext): string[] {
  const p = ctx.config.palette;
  return [
    p.primary,
    p.accent,
    mix(p.primary, p.accent, 0.5),
    darken(p.primary, 0.3),
    lighten(p.accent, 0.25),
    mix(p.ink, p.primary, 0.35),
  ];
}

export function createMemory(): TemplateGame {
  let cards: Card[] = [];
  let open: number[] = [];
  let resolveIn = 0;
  let peekLeft = 2;
  let flipBack = 0.8;
  let timeLimit = 28;
  let turns = 0;
  let wonFor = 0;
  const sparks = new Sparks();

  const matched = () => cards.filter((c) => c.matched).length / 2;
  const pairs = () => cards.length / 2;

  const flip = (card: Card, up: boolean) => {
    if (card.up !== up) {
      card.up = up;
      card.turning = FLIP_S;
    }
  };

  const drawBack = (g: CanvasRenderingContext2D, card: Card, ctx: GameContext) => {
    const p = ctx.config.palette;
    const cx = card.x + card.w / 2;
    const cy = card.y + card.h / 2;
    g.save();
    roundRect(g, card.x + 5, card.y + 5, card.w - 10, card.h - 10, 10);
    g.clip();
    // Soft diagonal stripes in the shop's colour.
    g.strokeStyle = withAlpha(lighten(p.primary, 0.35), 0.35);
    g.lineWidth = 6;
    for (let d = -card.h; d < card.w + card.h; d += 16) {
      g.beginPath();
      g.moveTo(card.x + d, card.y);
      g.lineTo(card.x + d - card.h, card.y + card.h);
      g.stroke();
    }
    g.restore();
    // The ribbon badge: two folded tails under a round seal.
    g.fillStyle = darken(p.accent, 0.15);
    for (const side of [-1, 1]) {
      g.beginPath();
      g.moveTo(cx + side * 4, cy + 4);
      g.lineTo(cx + side * 14, cy + 24);
      g.lineTo(cx + side * 8, cy + 20);
      g.lineTo(cx + side * 2, cy + 26);
      g.closePath();
      g.fill();
    }
    g.fillStyle = p.accent;
    g.beginPath();
    g.arc(cx, cy, 13, 0, Math.PI * 2);
    g.fill();
    g.strokeStyle = withAlpha("#ffffff", 0.7);
    g.lineWidth = 2;
    g.beginPath();
    g.arc(cx, cy, 8, 0, Math.PI * 2);
    g.stroke();
  };

  const drawFace = (g: CanvasRenderingContext2D, card: Card, ctx: GameContext) => {
    const colour = faceColours(ctx)[card.face % 6] ?? ctx.config.palette.primary;
    const more = ctx.images.more.length;
    const which = card.face <= more ? card.face : 0;
    const cx = card.x + card.w / 2;
    const cy = card.y + card.h / 2;
    const glow = g.createRadialGradient(cx, cy, 4, cx, cy, card.w * 0.62);
    glow.addColorStop(0, withAlpha(colour, 0.55));
    glow.addColorStop(1, withAlpha(colour, 0.12));
    g.fillStyle = glow;
    roundRect(g, card.x + 5, card.y + 5, card.w - 10, card.h - 10, 10);
    g.fill();
    if (card.face > more) {
      // The same product in another of the shop's colours: a variant pair.
      drawFit(g, recoloured(ctx.images.product, colour, 0.85), cx, cy - 4, card.w - 22, card.h - 30);
    } else {
      drawProduct(g, ctx.images, ctx.elapsed, cx, cy - 4, card.w - 22, card.h - 30, which);
    }
    // A colour chip under the product names the pair without words.
    g.fillStyle = colour;
    roundRect(g, cx - 16, card.y + card.h - 19, 32, 8, 4);
    g.fill();
  };

  return {
    id: "memory",
    init(ctx) {
      const d = ctx.config.difficulty;
      const count = Math.round(param(d, "pairs"));
      peekLeft = param(d, "peek_seconds");
      flipBack = param(d, "flip_back");
      timeLimit = param(d, "time_limit");
      const faces = Array.from({ length: count * 2 }, (_, i) => Math.floor(i / 2));
      for (let i = faces.length - 1; i > 0; i--) {
        const j = ctx.rng.int(0, i);
        [faces[i], faces[j]] = [faces[j] as number, faces[i] as number];
      }
      cards = layout(faces.length).map((rect, i) => ({
        ...rect,
        face: faces[i] as number,
        up: true,
        matched: false,
        turning: 0,
      }));
      open = [];
      resolveIn = 0;
      turns = 0;
      wonFor = 0;
    },
    update(dt, ctx) {
      for (const card of cards) card.turning = Math.max(0, card.turning - dt);
      sparks.update(dt);
      if (cards.length > 0 && matched() === pairs()) wonFor += dt;
      if (peekLeft > 0) {
        peekLeft -= dt;
        if (peekLeft <= 0) for (const card of cards) flip(card, false);
        return;
      }
      if (resolveIn > 0) {
        resolveIn -= dt;
        if (resolveIn <= 0) {
          for (const index of open) flip(cards[index] as Card, false);
          open = [];
          ctx.sfx.play("bump");
        }
      }
    },
    draw(g, ctx) {
      const p = ctx.config.palette;
      backdrop(g, p.background, [p.primary, p.accent], ctx.elapsed);
      tile3d(g, AREA.x - 10, AREA.y - 14, AREA.w + 20, AREA.h + 28, darken(p.surface, 0.05), {
        radius: 24,
        edge: 10,
      });
      for (const card of cards) {
        // A flip squeezes the card to a line and opens it again showing the other side.
        const t = card.turning / FLIP_S;
        const squeeze = card.turning > 0 ? Math.abs(Math.cos(t * Math.PI)) : 1;
        const showUp = card.turning > 0 && t > 0.5 ? !card.up : card.up;
        const lift = card.matched ? 0 : showUp ? 5 : 0;
        g.save();
        g.translate(card.x + card.w / 2, 0);
        g.scale(Math.max(0.04, squeeze), 1);
        g.translate(-(card.x + card.w / 2), 0);
        const base = showUp ? p.surface : p.primary;
        tile3d(g, card.x, card.y, card.w, card.h, card.matched ? lighten(p.surface, 0.08) : base, {
          radius: 14,
          edge: 7,
          lift,
        });
        g.translate(0, -lift);
        if (showUp) drawFace(g, card, ctx);
        else drawBack(g, card, ctx);
        if (card.matched) {
          g.strokeStyle = withAlpha(p.accent, 0.9);
          g.lineWidth = 3;
          roundRect(g, card.x + 2, card.y + 2, card.w - 4, card.h - 4, 13);
          g.stroke();
        }
        g.restore();
      }
      if (peekLeft > 0) {
        const share = Math.max(0, peekLeft) / 3;
        g.fillStyle = withAlpha(p.ink, 0.12);
        roundRect(g, 60, AREA.y + AREA.h + 26, 240, 8, 4);
        g.fill();
        g.fillStyle = p.accent;
        roundRect(g, 60, AREA.y + AREA.h + 26, 240 * Math.min(1, share), 8, 4);
        g.fill();
      }
      sparks.draw(g);
    },
    pointer(event: PointerInfo, ctx) {
      if (event.phase !== "down" || peekLeft > 0 || resolveIn > 0) return;
      const index = cards.findIndex(
        (c) => event.x >= c.x && event.x <= c.x + c.w && event.y >= c.y && event.y <= c.y + c.h,
      );
      const card = cards[index];
      if (!card || card.up || card.matched) return;
      flip(card, true);
      open.push(index);
      ctx.sfx.play("tap");
      if (open.length < 2) return;
      turns += 1;
      const [a, b] = open.map((i) => cards[i] as Card) as [Card, Card];
      if (a.face === b.face) {
        a.matched = b.matched = true;
        open = [];
        ctx.sfx.play("coin");
        const p = ctx.config.palette;
        for (const c of [a, b]) {
          sparks.burst(ctx.rng, c.x + c.w / 2, c.y + c.h / 2, [p.primary, p.accent, "#ffffff"], 12);
        }
      } else {
        resolveIn = flipBack;
      }
    },
    progress: () => ({ score: matched(), goal: pairs() }),
    outcome(ctx): Outcome {
      if (cards.length > 0 && matched() === pairs()) return wonFor >= CELEBRATE_S ? "won" : "playing";
      return ctx.elapsed >= timeLimit ? "lost" : "playing";
    },
    timeUp() {
      for (const card of cards) card.up = true;
      return "lost";
    },
    debugState: () => ({
      cards: cards.map(({ face, x, y, w, h, up, matched: done }) => ({ face, x, y, w, h, up, matched: done })),
      peeking: peekLeft > 0,
      busy: resolveIn > 0,
      turns,
      timeLimit,
    }),
  };
}

if (typeof window !== "undefined" && (window as { R2P_CONFIG?: unknown }).R2P_CONFIG) {
  void startGame(createMemory);
}
