/** Drawing helpers for the tactile look: raised tiles, soft shadows, sparkles. */

import { darken, lighten, withAlpha } from "./color";
import type { Images } from "./game";
import type { Rng } from "./random";

/** Logical play-field size (portrait 9:16); the stage scales it to the screen. */
export const W = 360;
export const H = 640;

type G = CanvasRenderingContext2D;

export function roundRect(g: G, x: number, y: number, w: number, h: number, r: number): void {
  const radius = Math.min(r, w / 2, h / 2);
  g.beginPath();
  g.moveTo(x + radius, y);
  g.arcTo(x + w, y, x + w, y + h, radius);
  g.arcTo(x + w, y + h, x, y + h, radius);
  g.arcTo(x, y + h, x, y, radius);
  g.arcTo(x, y, x + w, y, radius);
  g.closePath();
}

export function softShadow(g: G, cx: number, cy: number, rx: number, ry: number, alpha = 0.22): void {
  const gradient = g.createRadialGradient(cx, cy, 0, cx, cy, rx);
  gradient.addColorStop(0, `rgba(20, 22, 35, ${alpha})`);
  gradient.addColorStop(1, "rgba(20, 22, 35, 0)");
  g.save();
  g.fillStyle = gradient;
  g.translate(cx, cy);
  g.scale(1, ry / rx);
  g.beginPath();
  g.arc(0, 0, rx, 0, Math.PI * 2);
  g.translate(-cx, -cy);
  g.fill();
  g.restore();
}

export interface TileStyle {
  radius?: number;
  /** Height of the visible bottom edge, in logical pixels. */
  edge?: number;
  /** Raise the face (selected or pressed states). */
  lift?: number;
}

/** A raised tile: a darker bottom edge, a gently lit face, and a bright top lip. */
export function tile3d(g: G, x: number, y: number, w: number, h: number, color: string,
  style: TileStyle = {}): void {
  const radius = style.radius ?? 14;
  const edge = style.edge ?? 6;
  const lift = style.lift ?? 0;
  softShadow(g, x + w / 2, y + h + edge, w * 0.55, 8 + lift, 0.18 + lift * 0.02);
  g.fillStyle = darken(color, 0.28);
  roundRect(g, x, y + edge - lift, w, h, radius);
  g.fill();
  const face = g.createLinearGradient(0, y - lift, 0, y + h - lift);
  face.addColorStop(0, lighten(color, 0.14));
  face.addColorStop(1, color);
  g.fillStyle = face;
  roundRect(g, x, y - lift, w, h, radius);
  g.fill();
  g.strokeStyle = withAlpha("#ffffff", 0.35);
  g.lineWidth = 1.5;
  g.beginPath();
  g.moveTo(x + radius, y - lift + 1.5);
  g.lineTo(x + w - radius, y - lift + 1.5);
  g.stroke();
}

/** Draw an image centred on (cx, cy), scaled to fit inside maxW × maxH. */
export function drawFit(g: G, image: CanvasImageSource & { width: number; height: number },
  cx: number, cy: number, maxW: number, maxH: number): { w: number; h: number } {
  const scale = Math.min(maxW / image.width, maxH / image.height);
  const w = image.width * scale;
  const h = image.height * scale;
  g.drawImage(image, cx - w / 2, cy - h / 2, w, h);
  return { w, h };
}

/** One picture of the product: a frame of its animation, or the still cut-out. */
export interface ProductPicture {
  image: CanvasImageSource;
  sx: number;
  sy: number;
  sw: number;
  sh: number;
}

/**
 * The product at a moment of game time. With an animation (feature 7) the frames play
 * forwards then backwards, so the loop has no jump; game time keeps replays exact.
 */
export function productPicture(images: Images, elapsed: number): ProductPicture {
  const moving = images.productFrames;
  if (!moving || moving.frames < 2) {
    const still = images.product;
    return { image: still, sx: 0, sy: 0, sw: still.width, sh: still.height };
  }
  const cycle = moving.frames * 2 - 2;
  const step = Math.floor(Math.max(0, elapsed) * moving.fps) % cycle;
  const index = step < moving.frames ? step : cycle - step;
  const sw = moving.image.width / moving.frames;
  return { image: moving.image, sx: index * sw, sy: 0, sw, sh: moving.image.height };
}

/**
 * Draw a product centred on (cx, cy), scaled to fit inside maxW × maxH. `which` 0 is the main
 * product (moving when it has an animation); 1 and up are the shop's other products.
 */
export function drawProduct(g: G, images: Images, elapsed: number, cx: number, cy: number,
  maxW: number, maxH: number, which = 0): { w: number; h: number } {
  const other = which > 0 ? images.more[which - 1] : undefined;
  const picture = other
    ? { image: other, sx: 0, sy: 0, sw: other.width, sh: other.height }
    : productPicture(images, elapsed);
  const scale = Math.min(maxW / picture.sw, maxH / picture.sh);
  const w = picture.sw * scale;
  const h = picture.sh * scale;
  g.drawImage(picture.image, picture.sx, picture.sy, picture.sw, picture.sh, cx - w / 2, cy - h / 2,
    w, h);
  return { w, h };
}

const recolours = new WeakMap<object, Map<string, HTMLCanvasElement>>();

/**
 * The image recoloured to `colour`, keeping its own light and shade ("color" blending) and
 * its transparent edges. `strength` 1 is a full recolour; less keeps some original colour.
 * Results are cached per image and colour, so drawing them every frame is cheap.
 */
export function recoloured(image: HTMLImageElement | HTMLCanvasElement, colour: string,
  strength = 1): HTMLCanvasElement {
  let byColour = recolours.get(image);
  if (!byColour) {
    byColour = new Map();
    recolours.set(image, byColour);
  }
  const key = `${colour}/${strength}`;
  const cached = byColour.get(key);
  if (cached) return cached;
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, image.width);
  canvas.height = Math.max(1, image.height);
  const c = canvas.getContext("2d");
  if (c) {
    c.drawImage(image, 0, 0);
    c.globalCompositeOperation = "color";
    c.globalAlpha = strength;
    c.fillStyle = colour;
    c.fillRect(0, 0, canvas.width, canvas.height);
    c.globalAlpha = 1;
    c.globalCompositeOperation = "destination-in";
    c.drawImage(image, 0, 0);
  }
  byColour.set(key, canvas);
  return canvas;
}

/** Largest font size (up to `size`) at which `text` fits in `maxWidth`. */
export function fitFont(g: G, text: string, maxWidth: number, size: number, family: string,
  weight = 800): string {
  let current = size;
  do {
    g.font = `${weight} ${current}px ${family}`;
    if (g.measureText(text).width <= maxWidth) break;
    current -= 1;
  } while (current > 10);
  return g.font;
}

interface Spark {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  size: number;
  color: string;
}

/** Short bursts of confetti-like sparks for catches, coupons and wins. */
export class Sparks {
  private items: Spark[] = [];

  burst(rng: Rng, x: number, y: number, colors: readonly string[], count = 14, speed = 160): void {
    for (let i = 0; i < count; i++) {
      const angle = rng.range(0, Math.PI * 2);
      const v = rng.range(speed * 0.4, speed);
      this.items.push({
        x, y, vx: Math.cos(angle) * v, vy: Math.sin(angle) * v - speed * 0.4,
        life: rng.range(0.45, 0.9), size: rng.range(2.5, 5.5), color: rng.pick(colors),
      });
    }
  }

  update(dt: number): void {
    for (const s of this.items) {
      s.x += s.vx * dt;
      s.y += s.vy * dt;
      s.vy += 520 * dt;
      s.life -= dt;
    }
    this.items = this.items.filter((s) => s.life > 0);
  }

  draw(g: G): void {
    for (const [index, s] of this.items.entries()) {
      if (calm && index % 3 !== 0) continue;
      g.globalAlpha = Math.min(1, s.life * 2);
      g.fillStyle = s.color;
      roundRect(g, s.x - s.size / 2, s.y - s.size / 2, s.size, s.size * 0.7, 1.5);
      g.fill();
    }
    g.globalAlpha = 1;
  }

  get count(): number {
    return this.items.length;
  }
}

let calm = false;

/**
 * Less motion for players who ask their phone for it (feature 23): the backdrop stays still
 * and bursts show fewer sparks. Random numbers are drawn exactly as before, so the game
 * itself plays the same.
 */
export function setCalm(on: boolean): void {
  calm = on;
}

/** The shared scene backdrop: a neutral gradient with soft, slowly drifting brand tints. */
export function backdrop(g: G, background: string, tints: readonly string[], now: number): void {
  const time = calm ? 0 : now;
  const sky = g.createLinearGradient(0, 0, 0, H);
  sky.addColorStop(0, lighten(background, 0.35));
  sky.addColorStop(1, background);
  g.fillStyle = sky;
  g.fillRect(0, 0, W, H);
  const blobs = [
    { x: 70, y: 120, r: 90, speed: 0.35 },
    { x: 300, y: 230, r: 120, speed: -0.25 },
    { x: 160, y: 420, r: 140, speed: 0.2 },
  ];
  blobs.forEach((blob, index) => {
    const color = tints[index % tints.length] ?? background;
    const x = blob.x + Math.sin(time * blob.speed + index) * 18;
    const glow = g.createRadialGradient(x, blob.y, 0, x, blob.y, blob.r);
    glow.addColorStop(0, withAlpha(color, 0.22));
    glow.addColorStop(1, withAlpha(color, 0));
    g.fillStyle = glow;
    g.fillRect(x - blob.r, blob.y - blob.r, blob.r * 2, blob.r * 2);
  });
}
