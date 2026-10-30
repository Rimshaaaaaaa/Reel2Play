/**
 * Catch: the shop's product falls; the player slides a shopping bag to catch it and dodges
 * grey "dud" pebbles. Original artwork, drawn in code: a glossy tote bag in the shop's
 * colour and a spiky pebble with a sulky face.
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
  W,
  withAlpha,
} from "../../engine/src/index";

const BAG_Y = 548;
const BAG_W = 104;
const BAG_H = 74;
const ITEM_SIZE = 66;
const FLOOR_Y = 600;
/** A beat to get ready before the first drop; it also keeps a flawless run at 15 s or more. */
const FIRST_DROP_S = 1.7;

interface Item {
  x: number;
  y: number;
  kind: "product" | "dud";
  /** Which of the shop's products falls: 0 is the main one (feature 11). */
  which: number;
  spin: number;
  wobble: number;
}

export function createCatch(): TemplateGame {
  let goal = 10;
  let fallSpeed = 215;
  let spawnEvery = 1;
  let dudShare = 0.25;
  let timeLimit = 22;
  let bagX = W / 2;
  let targetX = W / 2;
  let items: Item[] = [];
  let caught = 0;
  let sinceSpawn = 0;
  let sinceDud = 2; // products since the last dud: at most one dud in any three drops
  let productsDropped = 0;
  let squash = 0;
  let shake = 0;
  const sparks = new Sparks();

  const spawn = (ctx: GameContext) => {
    // Capping the duds keeps a careful player's run inside the time limit on every seed.
    const dud = sinceDud >= 2 && ctx.rng.next() < dudShare;
    sinceDud = dud ? 0 : sinceDud + 1;
    // The shop's products take turns, without touching the random sequence.
    const which = dud ? 0 : productsDropped++ % (1 + ctx.images.more.length);
    items.push({
      x: ctx.rng.range(46, W - 46),
      y: -ITEM_SIZE,
      kind: dud ? "dud" : "product",
      which,
      spin: ctx.rng.range(-0.6, 0.6),
      wobble: ctx.rng.range(0, Math.PI * 2),
    });
  };

  const drawBag = (g: CanvasRenderingContext2D, ctx: GameContext) => {
    const { primary, accent } = ctx.config.palette;
    const x = bagX - BAG_W / 2;
    const stretch = 1 - squash * 0.12;
    const top = BAG_Y - BAG_H * stretch + BAG_H;
    softShadow(g, bagX, BAG_Y + BAG_H + 6, BAG_W * 0.62, 10, 0.25);
    g.save();
    g.lineWidth = 7;
    g.lineCap = "round";
    g.strokeStyle = darken(primary, 0.35);
    for (const offset of [-24, 24]) {
      g.beginPath();
      g.arc(bagX + offset, top + 4, 15, Math.PI, 0);
      g.stroke();
    }
    const body = g.createLinearGradient(x, 0, x + BAG_W, 0);
    body.addColorStop(0, lighten(primary, 0.18));
    body.addColorStop(0.55, primary);
    body.addColorStop(1, darken(primary, 0.2));
    g.fillStyle = darken(primary, 0.4);
    roundRect(g, x - 2, top + 8, BAG_W + 4, BAG_H * stretch, 16);
    g.fill();
    g.fillStyle = body;
    g.beginPath();
    g.moveTo(x + 6, top);
    g.lineTo(x + BAG_W - 6, top);
    g.lineTo(x + BAG_W, top + BAG_H * stretch - 14);
    g.quadraticCurveTo(x + BAG_W, top + BAG_H * stretch, x + BAG_W - 14, top + BAG_H * stretch);
    g.lineTo(x + 14, top + BAG_H * stretch);
    g.quadraticCurveTo(x, top + BAG_H * stretch, x, top + BAG_H * stretch - 14);
    g.closePath();
    g.fill();
    g.fillStyle = accent;
    roundRect(g, x + 10, top + 22, BAG_W - 20, 9, 4.5);
    g.fill();
    g.strokeStyle = withAlpha("#ffffff", 0.45);
    g.lineWidth = 2;
    g.beginPath();
    g.moveTo(x + 14, top + 6);
    g.lineTo(x + 18, top + BAG_H * stretch - 18);
    g.stroke();
    g.restore();
  };

  const drawDud = (g: CanvasRenderingContext2D, item: Item, ctx: GameContext) => {
    const r = ITEM_SIZE * 0.36;
    g.save();
    g.translate(item.x, item.y);
    g.rotate(item.spin * ctx.elapsed);
    g.fillStyle = "#5b5f6b";
    g.beginPath();
    for (let i = 0; i < 18; i++) {
      const angle = (i / 18) * Math.PI * 2;
      const radius = i % 2 === 0 ? r * 1.22 : r;
      g.lineTo(Math.cos(angle) * radius, Math.sin(angle) * radius);
    }
    g.closePath();
    g.fill();
    const shade = g.createRadialGradient(-r * 0.35, -r * 0.4, 2, 0, 0, r);
    shade.addColorStop(0, "#a3a8b4");
    shade.addColorStop(1, "#4a4e59");
    g.fillStyle = shade;
    g.beginPath();
    g.arc(0, 0, r * 0.92, 0, Math.PI * 2);
    g.fill();
    g.rotate(-item.spin * ctx.elapsed);
    g.fillStyle = "#1f2128";
    g.fillRect(-r * 0.42, -r * 0.18, r * 0.24, r * 0.12);
    g.fillRect(r * 0.18, -r * 0.18, r * 0.24, r * 0.12);
    g.strokeStyle = "#1f2128";
    g.lineWidth = 2.4;
    g.beginPath();
    g.arc(0, r * 0.42, r * 0.28, Math.PI * 1.15, Math.PI * 1.85);
    g.stroke();
    g.restore();
  };

  return {
    id: "catch",
    init(ctx) {
      const d = ctx.config.difficulty;
      goal = Math.round(param(d, "goal"));
      fallSpeed = param(d, "fall_speed");
      spawnEvery = param(d, "spawn_every");
      dudShare = param(d, "decoy_share");
      timeLimit = param(d, "time_limit");
      items = [];
      caught = 0;
      productsDropped = 0;
      sinceSpawn = spawnEvery - FIRST_DROP_S;
      bagX = targetX = W / 2;
    },
    update(dt, ctx) {
      sinceSpawn += dt;
      if (sinceSpawn >= spawnEvery) {
        sinceSpawn -= spawnEvery;
        spawn(ctx);
      }
      bagX += (targetX - bagX) * Math.min(1, dt * 14);
      squash = Math.max(0, squash - dt * 4);
      shake = Math.max(0, shake - dt * 3);
      const mouthTop = BAG_Y - 6;
      for (const item of items) {
        item.y += fallSpeed * dt;
        item.wobble += dt * 3;
        const inMouth = Math.abs(item.x - bagX) < BAG_W * 0.5 && item.y > mouthTop && item.y < BAG_Y + 30;
        if (inMouth) {
          item.y = H * 2;
          squash = 1;
          if (item.kind === "product") {
            caught += 1;
            ctx.sfx.play("catch");
            const { primary, accent } = ctx.config.palette;
            sparks.burst(ctx.rng, bagX, BAG_Y, [primary, accent, "#ffffff"]);
          } else {
            caught = Math.max(0, caught - 1);
            shake = 1;
            ctx.sfx.play("bump");
          }
        } else if (item.y > FLOOR_Y + 20 && item.y < H * 2 && item.kind === "product") {
          ctx.sfx.play("miss");
          item.y = H * 2;
        }
      }
      items = items.filter((item) => item.y < H + ITEM_SIZE);
      sparks.update(dt);
    },
    draw(g, ctx) {
      const p = ctx.config.palette;
      g.save();
      if (shake > 0) g.translate(Math.sin(ctx.elapsed * 60) * 4 * shake, 0);
      backdrop(g, p.background, [p.primary, p.accent], ctx.elapsed);
      const floor = g.createLinearGradient(0, FLOOR_Y, 0, H);
      floor.addColorStop(0, p.surface);
      floor.addColorStop(1, darken(p.surface, 0.1));
      g.fillStyle = floor;
      g.fillRect(0, FLOOR_Y, W, H - FLOOR_Y);
      g.fillStyle = withAlpha(p.primary, 0.85);
      g.fillRect(0, FLOOR_Y, W, 5);
      for (const item of items) {
        if (item.kind === "dud") {
          drawDud(g, item, ctx);
          continue;
        }
        g.save();
        g.translate(item.x, item.y);
        g.rotate(Math.sin(item.wobble) * 0.18);
        g.shadowColor = "rgba(15, 18, 30, 0.35)";
        g.shadowBlur = 14;
        g.shadowOffsetY = 8;
        // Each falling product is at its own point of the animation, so they do not move in step.
        drawProduct(g, ctx.images, ctx.elapsed + item.x / 97, 0, 0, ITEM_SIZE, ITEM_SIZE,
          item.which);
        g.restore();
      }
      drawBag(g, ctx);
      sparks.draw(g);
      g.restore();
    },
    pointer(event: PointerInfo) {
      if (event.phase === "up") return;
      targetX = Math.min(W - BAG_W / 2 - 6, Math.max(BAG_W / 2 + 6, event.x));
    },
    progress: () => ({ score: caught, goal }),
    outcome(ctx): Outcome {
      if (caught >= goal) return "won";
      return ctx.elapsed >= timeLimit ? "lost" : "playing";
    },
    debugState: () => ({
      bagX,
      bagY: BAG_Y,
      goal,
      caught,
      timeLimit,
      items: items.filter((i) => i.y < H).map((i) => ({ x: i.x, y: i.y, kind: i.kind })),
    }),
  };
}

if (typeof window !== "undefined" && (window as { R2P_CONFIG?: unknown }).R2P_CONFIG) {
  void startGame(createCatch);
}
