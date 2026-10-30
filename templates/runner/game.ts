/**
 * Runner: "Pip", a small capsule-shaped courier in the shop's colour, runs to a podium
 * where the product waits. Tap to jump crates and grab coupons; a bump knocks Pip back.
 * All artwork is original and drawn in code.
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

const GROUND_Y = 500;
const HERO_X = 92;
const HERO_W = 42;
const HERO_H = 54;
const GRAVITY = 2300;
const JUMP_SPEED = 860;
const INVULNERABLE_S = 0.9;
const STUN_S = 0.35;

interface Crate {
  x: number;
  w: number;
  h: number;
}

interface Coupon {
  x: number;
  y: number;
  taken: boolean;
}

export function createRunner(): TemplateGame {
  let speed = 220;
  let trackLength = 4800;
  let knockback = 180;
  let distance = 0;
  let heroY = 0;
  let velocity = 0;
  let onGround = true;
  let hurt = 0;
  let stunned = 0;
  let crates: Crate[] = [];
  let coupons: Coupon[] = [];
  let collected = 0;
  let finished = false;
  let stride = 0;
  const sparks = new Sparks();

  const layout = (ctx: GameContext) => {
    const d = ctx.config.difficulty;
    const count = Math.round(param(d, "obstacles"));
    const couponCount = Math.round(param(d, "coupons"));
    const start = 520;
    const end = trackLength - 420;
    const slot = (end - start) / count;
    crates = Array.from({ length: count }, (_, i) => {
      const h = ctx.rng.pick([38, 46, 54]);
      return { x: start + slot * i + ctx.rng.range(slot * 0.15, slot * 0.6), w: ctx.rng.pick([40, 48]), h };
    });
    coupons = Array.from({ length: couponCount }, (_, i) => {
      const x = start + ((end - start) / couponCount) * (i + 0.5);
      const near = crates.some((c) => Math.abs(c.x + c.w / 2 - x) < 70);
      return { x, y: near ? GROUND_Y - 130 : GROUND_Y - ctx.rng.pick([30, 100]), taken: false };
    });
  };

  const drawHero = (g: CanvasRenderingContext2D, ctx: GameContext) => {
    const { primary, accent, ink } = ctx.config.palette;
    const y = GROUND_Y - heroY;
    const squash = onGround ? 1 + Math.sin(stride * 2) * 0.04 : velocity > 0 ? 0.92 : 1.06;
    const blink = hurt > 0 && Math.floor(hurt * 12) % 2 === 0;
    softShadow(g, HERO_X, GROUND_Y + 4, 26 - Math.min(14, heroY / 10), 6, 0.3);
    if (blink) return;
    g.save();
    g.translate(HERO_X, y);
    g.scale(1 / squash, squash);
    const leg = Math.sin(stride) * 9;
    g.fillStyle = darken(primary, 0.45);
    for (const [dx, swing] of [[-9, leg], [9, -leg]] as const) {
      roundRect(g, dx - 5 + (onGround ? swing * 0.4 : 0), -10, 10, 12, 5);
      g.fill();
    }
    const body = g.createLinearGradient(-HERO_W / 2, -HERO_H, HERO_W / 2, 0);
    body.addColorStop(0, lighten(primary, 0.25));
    body.addColorStop(1, darken(primary, 0.15));
    g.fillStyle = darken(primary, 0.35);
    roundRect(g, -HERO_W / 2, -HERO_H - 4, HERO_W, HERO_H, HERO_W / 2);
    g.fill();
    g.fillStyle = body;
    roundRect(g, -HERO_W / 2, -HERO_H - 8, HERO_W, HERO_H, HERO_W / 2);
    g.fill();
    g.fillStyle = ink;
    roundRect(g, -HERO_W / 2 + 6, -HERO_H + 6, HERO_W - 8, 15, 7.5);
    g.fill();
    g.fillStyle = "#ffffff";
    g.beginPath();
    g.arc(4, -HERO_H + 13.5, 3, 0, Math.PI * 2);
    g.arc(13, -HERO_H + 13.5, 3, 0, Math.PI * 2);
    g.fill();
    g.strokeStyle = darken(primary, 0.4);
    g.lineWidth = 2.5;
    g.beginPath();
    g.moveTo(-4, -HERO_H - 8);
    g.lineTo(-8, -HERO_H - 20);
    g.stroke();
    g.fillStyle = accent;
    g.beginPath();
    g.arc(-8, -HERO_H - 22, 4.5, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = withAlpha("#ffffff", 0.4);
    roundRect(g, -HERO_W / 2 + 5, -HERO_H + 26, 5, 18, 2.5);
    g.fill();
    g.fillStyle = accent;
    roundRect(g, -HERO_W / 2 - 6, -30, 12, 18, 4);
    g.fill();
    g.restore();
  };

  const drawCrate = (g: CanvasRenderingContext2D, crate: Crate) => {
    const x = HERO_X + (crate.x - distance);
    if (x < -80 || x > W + 80) return;
    tile3d(g, x, GROUND_Y - crate.h, crate.w, crate.h - 5, "#b9a58a", { radius: 6, edge: 5 });
    g.strokeStyle = withAlpha(darken("#b9a58a", 0.4), 0.7);
    g.lineWidth = 2;
    g.beginPath();
    g.moveTo(x + 6, GROUND_Y - crate.h + 6);
    g.lineTo(x + crate.w - 6, GROUND_Y - 12);
    g.moveTo(x + crate.w - 6, GROUND_Y - crate.h + 6);
    g.lineTo(x + 6, GROUND_Y - 12);
    g.stroke();
  };

  const drawCoupon = (g: CanvasRenderingContext2D, coupon: Coupon, ctx: GameContext) => {
    const x = HERO_X + (coupon.x - distance);
    if (coupon.taken || x < -40 || x > W + 40) return;
    const bob = Math.sin(ctx.elapsed * 4 + coupon.x) * 4;
    const { accent, accentInk } = ctx.config.palette;
    g.save();
    g.translate(x, coupon.y + bob);
    g.rotate(-0.12);
    g.fillStyle = darken(accent, 0.3);
    roundRect(g, -20, -11, 40, 26, 6);
    g.fill();
    g.fillStyle = accent;
    roundRect(g, -20, -14, 40, 26, 6);
    g.fill();
    g.fillStyle = withAlpha(darken(accent, 0.3), 0.6);
    g.beginPath();
    g.arc(-20, -1, 4, -Math.PI / 2, Math.PI / 2);
    g.arc(20, -1, 4, Math.PI / 2, Math.PI * 1.5);
    g.fill();
    g.fillStyle = accentInk;
    g.font = `900 15px ${ctx.font}`;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillText("%", 0, -1);
    g.restore();
  };

  const drawFinish = (g: CanvasRenderingContext2D, ctx: GameContext) => {
    const x = HERO_X + (trackLength - distance);
    if (x > W + 160) return;
    const { primary, surface, ink } = ctx.config.palette;
    for (let i = 0; i < 8; i++) {
      g.fillStyle = i % 2 === 0 ? ink : surface;
      g.fillRect(x - 6, GROUND_Y - 220 + i * 26, 12, 26);
    }
    tile3d(g, x + 26, GROUND_Y - 60, 96, 52, primary, { radius: 12, edge: 8 });
    g.save();
    g.shadowColor = withAlpha(ctx.config.palette.accent, 0.8);
    g.shadowBlur = 24 + Math.sin(ctx.elapsed * 5) * 8;
    drawProduct(g, ctx.images, ctx.elapsed, x + 74, GROUND_Y - 112, 96, 96);
    g.restore();
  };

  const heroBox = () => ({
    left: distance - HERO_W / 2 + 6,
    right: distance + HERO_W / 2 - 6,
    bottom: heroY,
  });

  return {
    id: "runner",
    init(ctx) {
      const d = ctx.config.difficulty;
      speed = param(d, "speed");
      trackLength = speed * param(d, "track_seconds");
      knockback = param(d, "knockback");
      distance = 0;
      heroY = 0;
      velocity = 0;
      onGround = true;
      hurt = 0;
      stunned = 0;
      collected = 0;
      finished = false;
      layout(ctx);
    },
    update(dt, ctx) {
      if (finished) return;
      stunned = Math.max(0, stunned - dt);
      if (stunned <= 0) distance = Math.min(trackLength, distance + speed * dt);
      stride += dt * (onGround ? 14 : 4);
      hurt = Math.max(0, hurt - dt);
      if (!onGround) {
        velocity -= GRAVITY * dt;
        heroY += velocity * dt;
        if (heroY <= 0) {
          heroY = 0;
          velocity = 0;
          onGround = true;
        }
      }
      const box = heroBox();
      for (const crate of crates) {
        const overlaps = box.right > crate.x && box.left < crate.x + crate.w && box.bottom < crate.h - 4;
        if (overlaps && hurt <= 0) {
          hurt = INVULNERABLE_S;
          stunned = STUN_S;
          distance = Math.max(0, distance - knockback);
          ctx.sfx.play("bump");
        }
      }
      for (const coupon of coupons) {
        const heroTop = GROUND_Y - heroY - HERO_H;
        const heroBottom = GROUND_Y - heroY;
        if (!coupon.taken && Math.abs(coupon.x - distance) < 30 && coupon.y > heroTop - 16
          && coupon.y < heroBottom + 10) {
          coupon.taken = true;
          collected += 1;
          ctx.sfx.play("coin");
          sparks.burst(ctx.rng, HERO_X, coupon.y, [ctx.config.palette.accent, "#ffffff"], 10, 120);
        }
      }
      if (distance >= trackLength) {
        finished = true;
        const p = ctx.config.palette;
        sparks.burst(ctx.rng, HERO_X + 70, GROUND_Y - 120, [p.primary, p.accent, "#ffffff"], 40, 260);
      }
      sparks.update(dt);
    },
    draw(g, ctx) {
      const p = ctx.config.palette;
      backdrop(g, p.background, [p.accent, p.primary], ctx.elapsed);
      const hillOffset = (distance * 0.25) % 240;
      g.fillStyle = withAlpha(p.primary, 0.12);
      for (let i = -1; i < 3; i++) {
        g.beginPath();
        g.ellipse(i * 240 - hillOffset + 120, GROUND_Y + 30, 170, 110, 0, Math.PI, 0);
        g.fill();
      }
      const ground = g.createLinearGradient(0, GROUND_Y, 0, H);
      ground.addColorStop(0, p.surface);
      ground.addColorStop(1, darken(p.surface, 0.12));
      g.fillStyle = ground;
      g.fillRect(0, GROUND_Y, W, H - GROUND_Y);
      const stripe = (distance % 60) * -1;
      for (let x = stripe; x < W; x += 60) {
        g.fillStyle = withAlpha(p.primary, 0.75);
        roundRect(g, x, GROUND_Y + 2, 34, 6, 3);
        g.fill();
      }
      const bar = Math.min(1, distance / trackLength);
      g.fillStyle = withAlpha(p.ink, 0.12);
      roundRect(g, 24, GROUND_Y + 70, W - 48, 10, 5);
      g.fill();
      g.fillStyle = p.accent;
      roundRect(g, 24, GROUND_Y + 70, (W - 48) * bar, 10, 5);
      g.fill();
      drawFinish(g, ctx);
      for (const crate of crates) drawCrate(g, crate);
      for (const coupon of coupons) drawCoupon(g, coupon, ctx);
      drawHero(g, ctx);
      sparks.draw(g);
    },
    pointer(event: PointerInfo, ctx) {
      if (event.phase !== "down" || !onGround || finished) return;
      onGround = false;
      velocity = JUMP_SPEED;
      ctx.sfx.play("jump");
    },
    progress: () => ({ score: collected, goal: coupons.length }),
    outcome: (): Outcome => (finished ? "won" : "playing"),
    debugState: () => ({
      distance,
      trackLength,
      speed,
      heroY,
      onGround,
      hurt,
      collected,
      crates: crates.map((c) => ({ ahead: c.x - distance, w: c.w, h: c.h })),
    }),
  };
}

if (typeof window !== "undefined" && (window as { R2P_CONFIG?: unknown }).R2P_CONFIG) {
  void startGame(createRunner);
}
