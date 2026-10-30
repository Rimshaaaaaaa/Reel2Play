/**
 * Colour picker: shoppers come to the counter, each wishing for the product in a colour.
 * Tap the swatch that matches their wish; the product changes colour on its stand and the
 * shopper skips away happy. Serve them all before the time is up. Original characters drawn
 * in code: round "Puffs" with a little sprout on top, each a different soft shape.
 */

import {
  backdrop,
  darken,
  type GameContext,
  lighten,
  type Outcome,
  parseHex,
  type PointerInfo,
  param,
  recoloured,
  roundRect,
  softShadow,
  Sparks,
  startGame,
  type TemplateGame,
  tile3d,
  toHex,
  W,
  withAlpha,
} from "../../engine/src/index";

const SWATCH_Y = 560;
const SWATCH_R = 25;
const STAND = { cx: W / 2, cy: 410 };
const ARRIVE_S = 1.0;
const HAPPY_S = 1.4;

interface Shopper {
  wish: number;
  /** Seconds since the shopper arrived; negative while still walking in. */
  t: number;
  happyFor: number;
  frown: number;
  shape: number;
  tone: string;
}

/** `hex` with its hue turned by `degrees`, keeping lightness and saturation. */
export function turnHue(hex: string, degrees: number): string {
  const { r, g, b } = parseHex(hex);
  const [R, G, B] = [r / 255, g / 255, b / 255];
  const max = Math.max(R, G, B);
  const min = Math.min(R, G, B);
  const l = (max + min) / 2;
  const d = max - min;
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  let h = 0;
  if (d !== 0) {
    if (max === R) h = ((G - B) / d) % 6;
    else if (max === G) h = (B - R) / d + 2;
    else h = (R - G) / d + 4;
  }
  h = (h * 60 + degrees + 360) % 360;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const [r1, g1, b1] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x]
    : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return toHex({ r: (r1 + m) * 255, g: (g1 + m) * 255, b: (b1 + m) * 255 });
}

/** Five swatches from the shop's colours and their neighbours on the colour wheel. */
export function swatches(ctx: GameContext): string[] {
  const p = ctx.config.palette;
  return [p.primary, p.accent, turnHue(p.primary, 140), turnHue(p.accent, -120), turnHue(p.primary, 215)];
}

export function swatchCentre(index: number): { x: number; y: number } {
  return { x: W / 2 + (index - 2) * 64, y: SWATCH_Y };
}

export function createColours(): TemplateGame {
  let colours: string[] = [];
  let queue: Shopper[] = [];
  let served = 0;
  let goal = 5;
  let timeLimit = 28;
  let showing: string | null = null;
  const sparks = new Sparks();

  const current = () => queue[0];

  const newShopper = (ctx: GameContext, previous: number | null): Shopper => {
    let wish = ctx.rng.int(0, colours.length - 1);
    if (wish === previous) wish = (wish + 1 + ctx.rng.int(0, colours.length - 2)) % colours.length;
    const p = ctx.config.palette;
    const tones = [lighten(p.surface, 0.05), "#f2e3d3", "#dfe8f2", "#ecdff0", "#e3efe2"];
    return { wish, t: -ARRIVE_S, happyFor: 0, frown: 0, shape: ctx.rng.int(0, 2), tone: ctx.rng.pick(tones) };
  };

  const drawShopper = (g: CanvasRenderingContext2D, shopper: Shopper, ctx: GameContext) => {
    const p = ctx.config.palette;
    const arriving = Math.min(1, (shopper.t + ARRIVE_S) / ARRIVE_S);
    const leaving = shopper.happyFor > 0 ? Math.min(1, shopper.happyFor / HAPPY_S) : 0;
    const x = W / 2 + (1 - arriving) * 220 - leaving * 260;
    const hop = shopper.happyFor > 0 ? Math.abs(Math.sin(shopper.happyFor * 12)) * 18 : 0;
    const shake = shopper.frown > 0 ? Math.sin(shopper.frown * 40) * 6 : 0;
    const y = 238 - hop;
    const w = [96, 110, 88][shopper.shape] ?? 96;
    const h = [104, 92, 112][shopper.shape] ?? 104;
    softShadow(g, x, 300, 58, 10, 0.22);
    g.fillStyle = darken(shopper.tone, 0.18);
    roundRect(g, x - w / 2 + shake, y - h / 2 + 6, w, h, 40);
    g.fill();
    g.fillStyle = shopper.tone;
    roundRect(g, x - w / 2 + shake, y - h / 2, w, h, 40);
    g.fill();
    // The sprout on top, in the shop's colour.
    g.strokeStyle = darken(p.primary, 0.1);
    g.lineWidth = 4;
    g.beginPath();
    g.moveTo(x + shake, y - h / 2);
    g.quadraticCurveTo(x + 4 + shake, y - h / 2 - 16, x + 14 + shake, y - h / 2 - 20);
    g.stroke();
    g.fillStyle = p.primary;
    g.beginPath();
    g.ellipse(x + 16 + shake, y - h / 2 - 22, 9, 5, -0.5, 0, Math.PI * 2);
    g.fill();
    // Face: eyes, cheeks and a mouth that smiles when served and wobbles when wrong.
    const ex = 15;
    g.fillStyle = p.ink;
    for (const side of [-1, 1]) {
      g.beginPath();
      g.ellipse(x + side * ex + shake, y - 8, 5, shopper.happyFor > 0 ? 2.5 : 6, 0, 0, Math.PI * 2);
      g.fill();
      g.fillStyle = withAlpha("#ff8a8a", 0.45);
      g.beginPath();
      g.ellipse(x + side * (ex + 12) + shake, y + 6, 7, 4, 0, 0, Math.PI * 2);
      g.fill();
      g.fillStyle = p.ink;
    }
    g.strokeStyle = p.ink;
    g.lineWidth = 3;
    g.beginPath();
    if (shopper.frown > 0) g.arc(x + shake, y + 20, 8, Math.PI * 1.15, Math.PI * 1.85);
    else g.arc(x + shake, y + 8, 9, Math.PI * 0.15, Math.PI * 0.85);
    g.stroke();
    // The wish: a speech bubble with the colour they want.
    if (arriving >= 1 && shopper.happyFor === 0) {
      const bx = x + w / 2 + 6;
      const by = y - h / 2 - 8;
      g.fillStyle = "#ffffff";
      roundRect(g, bx - 4, by - 30, 70, 50, 18);
      g.fill();
      g.beginPath();
      g.moveTo(bx + 4, by + 16);
      g.lineTo(bx - 10, by + 30);
      g.lineTo(bx + 18, by + 18);
      g.fill();
      g.fillStyle = colours[shopper.wish] ?? p.primary;
      g.beginPath();
      g.arc(bx + 31, by - 5, 15, 0, Math.PI * 2);
      g.fill();
      g.strokeStyle = withAlpha(p.ink, 0.15);
      g.lineWidth = 2;
      g.stroke();
    }
  };

  return {
    id: "colours",
    init(ctx) {
      const d = ctx.config.difficulty;
      goal = Math.round(param(d, "shoppers"));
      timeLimit = param(d, "time_limit");
      colours = swatches(ctx);
      queue = [newShopper(ctx, null)];
      served = 0;
      showing = null;
    },
    update(dt, ctx) {
      sparks.update(dt);
      const shopper = current();
      if (!shopper) return;
      shopper.t += dt;
      shopper.frown = Math.max(0, shopper.frown - dt);
      if (shopper.happyFor > 0) {
        shopper.happyFor += dt;
        if (shopper.happyFor >= HAPPY_S) {
          queue.shift();
          if (served < goal) queue.push(newShopper(ctx, shopper.wish));
        }
      }
    },
    draw(g, ctx) {
      const p = ctx.config.palette;
      backdrop(g, p.background, [p.primary, p.accent], ctx.elapsed);
      const shopper = current();
      if (shopper) drawShopper(g, shopper, ctx);
      // The counter and the product on its stand.
      tile3d(g, 24, 318, W - 48, 34, darken(p.surface, 0.1), { radius: 12, edge: 8 });
      softShadow(g, STAND.cx, STAND.cy + 76, 90, 12, 0.25);
      tile3d(g, STAND.cx - 70, STAND.cy + 54, 140, 22, darken(p.surface, 0.18), { radius: 10, edge: 6 });
      const img = showing ? recoloured(ctx.images.product, showing, 0.9) : ctx.images.product;
      const scale = Math.min(170 / img.width, 130 / img.height);
      g.drawImage(img, STAND.cx - (img.width * scale) / 2, STAND.cy + 50 - img.height * scale,
        img.width * scale, img.height * scale);
      colours.forEach((colour, i) => {
        const c = swatchCentre(i);
        g.fillStyle = darken(colour, 0.3);
        g.beginPath();
        g.arc(c.x, c.y + 5, SWATCH_R, 0, Math.PI * 2);
        g.fill();
        const face = g.createRadialGradient(c.x - 8, c.y - 10, 2, c.x, c.y, SWATCH_R);
        face.addColorStop(0, lighten(colour, 0.3));
        face.addColorStop(1, colour);
        g.fillStyle = face;
        g.beginPath();
        g.arc(c.x, c.y, SWATCH_R, 0, Math.PI * 2);
        g.fill();
        if (colour === showing) {
          g.strokeStyle = p.ink;
          g.lineWidth = 3;
          g.beginPath();
          g.arc(c.x, c.y, SWATCH_R + 5, 0, Math.PI * 2);
          g.stroke();
        }
      });
      // Served shoppers as small hearts.
      for (let i = 0; i < goal; i++) {
        const x = W / 2 - (goal - 1) * 13 + i * 26;
        g.fillStyle = i < served ? p.accent : withAlpha(p.ink, 0.12);
        g.beginPath();
        g.arc(x - 4, 116, 5, 0, Math.PI * 2);
        g.arc(x + 4, 116, 5, 0, Math.PI * 2);
        g.moveTo(x - 9, 118);
        g.lineTo(x, 128);
        g.lineTo(x + 9, 118);
        g.fill();
      }
      sparks.draw(g);
    },
    pointer(event: PointerInfo, ctx) {
      if (event.phase !== "down") return;
      const index = colours.findIndex((_, i) => {
        const c = swatchCentre(i);
        return Math.hypot(event.x - c.x, event.y - c.y) <= SWATCH_R + 8;
      });
      if (index < 0) return;
      showing = colours[index] ?? null;
      ctx.sfx.play("tap");
      const shopper = current();
      if (!shopper || shopper.t < 0 || shopper.happyFor > 0) return;
      if (index === shopper.wish) {
        shopper.happyFor = 0.001;
        served += 1;
        ctx.sfx.play("coin");
        const p = ctx.config.palette;
        sparks.burst(ctx.rng, STAND.cx, STAND.cy, [showing ?? p.primary, p.accent, "#ffffff"], 24, 220);
      } else {
        shopper.frown = 0.5;
        ctx.sfx.play("bump");
      }
    },
    progress: () => ({ score: served, goal }),
    outcome(ctx): Outcome {
      if (served >= goal && queue.length === 0) return "won";
      return ctx.elapsed >= timeLimit ? "lost" : "playing";
    },
    debugState: () => {
      const shopper = current();
      return {
        served,
        goal,
        wish: shopper && shopper.t >= 0 && shopper.happyFor === 0 ? shopper.wish : null,
        swatches: colours.map((_, i) => swatchCentre(i)),
        timeLimit,
      };
    },
  };
}

if (typeof window !== "undefined" && (window as { R2P_CONFIG?: unknown }).R2P_CONFIG) {
  void startGame(createColours);
}
