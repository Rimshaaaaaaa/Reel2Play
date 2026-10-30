/**
 * Stack: gift boxes in the shop's colours slide in above the pile. Tap to drop each one; the
 * part that hangs over the edge is trimmed off, and a box that misses the pile falls. Build
 * the pile to the goal and the product lands on top. Original artwork drawn in code: ribboned
 * boxes with a lid line, and a soft camera that rises with the pile.
 */

import {
  backdrop,
  darken,
  drawProduct,
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
  tile3d,
  W,
  withAlpha,
} from "../../engine/src/index";

const BASE_Y = 560;
const LAYER_H = 36;
const START_W = 210;
const MIN_OVERLAP = 18;
const PERFECT = 5;
const CELEBRATE_S = 1.2; // the product lands on top before the end card

export interface Layer {
  x: number;
  w: number;
}

interface Falling {
  x: number;
  y: number;
  w: number;
  vy: number;
  spin: number;
  angle: number;
  colour: number;
}

export function createStack(): TemplateGame {
  let pile: Layer[] = [];
  let moving: (Layer & { dir: number }) | null = null;
  let waitFor = 0;
  let speed = 180;
  let goal = 8;
  let entryGap = 0.6;
  let fell = false;
  let done = false;
  let doneFor = 0;
  let landed = 0;
  let camera = 0;
  let perfects = 0;
  let falling: Falling[] = [];
  const sparks = new Sparks();

  const topY = (count: number) => BASE_Y - count * LAYER_H;

  const spawn = () => {
    const top = pile[pile.length - 1] as Layer;
    const fromLeft = pile.length % 2 === 1;
    moving = { x: fromLeft ? -top.w : W, w: top.w, dir: fromLeft ? 1 : -1 };
  };

  const colourFor = (index: number, ctx: GameContext) => {
    const p = ctx.config.palette;
    return index % 2 === 0 ? p.primary : p.accent;
  };

  const drawBox = (g: CanvasRenderingContext2D, x: number, y: number, w: number, index: number,
    ctx: GameContext) => {
    const colour = colourFor(index, ctx);
    tile3d(g, x, y, w, LAYER_H - 6, colour, { radius: 7, edge: 6 });
    // A lid line, and a ribbon down the middle when the box is wide enough.
    g.fillStyle = withAlpha(darken(colour, 0.25), 0.55);
    g.fillRect(x + 4, y + 9, w - 8, 2);
    if (w > 26) {
      const ribbon = index % 2 === 0 ? ctx.config.palette.accent : ctx.config.palette.primary;
      g.fillStyle = withAlpha(lighten(ribbon, 0.1), 0.9);
      g.fillRect(x + w / 2 - 5, y, 10, LAYER_H - 6);
    }
  };

  return {
    id: "stack",
    init(ctx) {
      const d = ctx.config.difficulty;
      speed = param(d, "slide_speed");
      goal = Math.round(param(d, "goal"));
      entryGap = param(d, "entry_gap");
      pile = [{ x: (W - START_W) / 2, w: START_W }];
      moving = null;
      waitFor = entryGap;
      fell = false;
      done = false;
      doneFor = 0;
      landed = 0;
      camera = 0;
      perfects = 0;
      falling = [];
    },
    update(dt) {
      sparks.update(dt);
      if (done) doneFor += dt;
      for (const piece of falling) {
        piece.vy += 900 * dt;
        piece.y += piece.vy * dt;
        piece.angle += piece.spin * dt;
      }
      falling = falling.filter((piece) => piece.y < H + 200 - camera);
      const wanted = Math.max(0, (pile.length - 7) * LAYER_H);
      camera += (wanted - camera) * Math.min(1, dt * 4);
      if (fell || done) return;
      if (!moving) {
        waitFor -= dt;
        if (waitFor <= 0) spawn();
        return;
      }
      moving.x += moving.dir * speed * dt;
      // It turns back at the far edge and keeps sliding until the player drops it.
      if (moving.x + moving.w > W + moving.w * 0.25 && moving.dir > 0) moving.dir = -1;
      if (moving.x < -moving.w * 0.25 && moving.dir < 0) moving.dir = 1;
    },
    draw(g, ctx) {
      const p = ctx.config.palette;
      backdrop(g, p.background, [p.primary, p.accent], ctx.elapsed);
      g.save();
      g.translate(0, camera);
      softShadow(g, W / 2, BASE_Y + 34, 150, 14, 0.25);
      tile3d(g, 40, BASE_Y, W - 80, 30, darken(p.surface, 0.12), { radius: 10, edge: 8 });
      pile.slice(1).forEach((layer, i) => drawBox(g, layer.x, topY(i + 1), layer.w, i + 1, ctx));
      if (moving) drawBox(g, moving.x, topY(pile.length), moving.w, pile.length, ctx);
      for (const piece of falling) {
        g.save();
        g.translate(piece.x + piece.w / 2, piece.y + LAYER_H / 2);
        g.rotate(piece.angle);
        drawBox(g, -piece.w / 2, -LAYER_H / 2, piece.w, piece.colour, ctx);
        g.restore();
      }
      if (!done) {
        // Where the pile has to reach: a dashed line and the product waiting, faintly.
        const goalY = topY(goal + 1) + LAYER_H - 6;
        g.strokeStyle = withAlpha(p.ink, 0.25);
        g.lineWidth = 2;
        g.setLineDash([8, 8]);
        g.beginPath();
        g.moveTo(40, goalY);
        g.lineTo(W - 40, goalY);
        g.stroke();
        g.setLineDash([]);
        g.globalAlpha = 0.28 + Math.sin(ctx.elapsed * 2.4) * 0.06;
        drawProduct(g, ctx.images, ctx.elapsed, W / 2, goalY - 50, 110, 96);
        g.globalAlpha = 1;
      }
      if (done) {
        const top = pile[pile.length - 1] as Layer;
        const drop = Math.max(0, 1 - doneFor / 0.35);
        const y = topY(pile.length) - 10 - drop * 160;
        drawProduct(g, ctx.images, ctx.elapsed, top.x + top.w / 2, y - 40, 110, 96);
      }
      sparks.draw(g);
      g.restore();
      // The goal as a row of small boxes at the top.
      for (let i = 0; i < goal; i++) {
        g.fillStyle = i < landed ? colourFor(i + 1, ctx) : withAlpha(p.ink, 0.12);
        roundRect(g, W / 2 - goal * 11 + i * 22 + 3, 112, 16, 12, 3);
        g.fill();
      }
    },
    pointer(event: PointerInfo, ctx) {
      if (event.phase !== "down" || !moving || fell || done) return;
      const top = pile[pile.length - 1] as Layer;
      const left = Math.max(top.x, moving.x);
      const right = Math.min(top.x + top.w, moving.x + moving.w);
      const overlap = right - left;
      const p = ctx.config.palette;
      const y = topY(pile.length);
      if (overlap < MIN_OVERLAP) {
        falling.push({ x: moving.x, y, w: moving.w, vy: 0, spin: moving.dir * 2.5, angle: 0, colour: pile.length });
        moving = null;
        fell = true;
        ctx.sfx.play("miss");
        return;
      }
      let placed: Layer;
      if (Math.abs(moving.x - top.x) <= PERFECT) {
        placed = { x: top.x, w: top.w };
        perfects += 1;
        sparks.burst(ctx.rng, top.x + top.w / 2, y, [p.accent, "#ffffff"], 18, 200);
        ctx.sfx.play("coin");
      } else {
        placed = { x: left, w: overlap };
        const offcut = moving.w - overlap;
        const offX = moving.x < top.x ? moving.x : right;
        falling.push({ x: offX, y, w: offcut, vy: -60, spin: moving.dir * 3, angle: 0, colour: pile.length });
        ctx.sfx.play("catch");
      }
      pile.push(placed);
      landed += 1;
      moving = null;
      if (landed >= goal) {
        done = true;
        ctx.sfx.play("win");
        sparks.burst(ctx.rng, placed.x + placed.w / 2, y - 40, [p.primary, p.accent, "#ffffff"], 50, 280);
      } else {
        waitFor = entryGap;
      }
    },
    progress: () => ({ score: landed, goal }),
    outcome(): Outcome {
      if (done) return doneFor >= CELEBRATE_S ? "won" : "playing";
      return fell ? "lost" : "playing";
    },
    debugState: () => {
      const top = pile[pile.length - 1] as Layer;
      return {
        top: { ...top },
        moving: moving ? { x: moving.x, w: moving.w, dir: moving.dir } : null,
        landed,
        goal,
        perfects,
        fell,
        speed,
      };
    },
  };
}

if (typeof window !== "undefined" && (window as { R2P_CONFIG?: unknown }).R2P_CONFIG) {
  void startGame(createStack);
}
