/**
 * Seasonal themes (feature 22): Ramzan, Eid, 14 August, wedding season and winter sale.
 * Decorations are drawn in code over the top corners and edges of the play field, kept small
 * and see-through so they never hide what the player needs. The greeting on the cards comes
 * from here too, in the game's language, so a model never words it.
 */

import { withAlpha } from "./color";
import { W } from "./draw";
import type { Language } from "./config";

export type Theme = "none" | "ramzan" | "eid" | "independence_day" | "wedding_season" | "winter_sale";

export const GREETINGS: Record<Exclude<Theme, "none">, Record<Language, string>> = {
  ramzan: { en: "Ramzan Kareem", ur: "رمضان کریم" },
  eid: { en: "Eid Mubarak", ur: "عید مبارک" },
  independence_day: { en: "Happy Independence Day", ur: "یومِ آزادی مبارک" },
  wedding_season: { en: "Wedding season", ur: "شادیوں کا موسم" },
  winter_sale: { en: "Winter sale", ur: "سردیوں کی سیل" },
};

export function greeting(theme: Theme | undefined, language: Language): string | null {
  return theme && theme !== "none" ? GREETINGS[theme][language] : null;
}

type G = CanvasRenderingContext2D;
const TOP = 58; // just under the timer and score

function crescent(g: G, x: number, y: number, r: number, colour: string): void {
  g.save();
  g.fillStyle = colour;
  g.beginPath();
  g.arc(x, y, r, 0, Math.PI * 2);
  g.arc(x + r * 0.42, y - r * 0.18, r * 0.82, 0, Math.PI * 2, true);
  g.fill("evenodd");
  g.restore();
}

function star(g: G, x: number, y: number, r: number, colour: string, points = 5): void {
  g.fillStyle = colour;
  g.beginPath();
  for (let i = 0; i < points * 2; i++) {
    const radius = i % 2 === 0 ? r : r * 0.45;
    const a = (i / (points * 2)) * Math.PI * 2 - Math.PI / 2;
    g.lineTo(x + Math.cos(a) * radius, y + Math.sin(a) * radius);
  }
  g.closePath();
  g.fill();
}

function lantern(g: G, x: number, y: number, t: number, glow: string, body: string): void {
  const sway = Math.sin(t * 1.6 + x) * 0.08;
  g.save();
  g.translate(x, TOP - 6);
  g.rotate(sway);
  g.strokeStyle = withAlpha(body, 0.7);
  g.lineWidth = 1.5;
  g.beginPath();
  g.moveTo(0, 0);
  g.lineTo(0, y - TOP);
  g.stroke();
  g.translate(0, y - TOP);
  const light = g.createRadialGradient(0, 14, 2, 0, 14, 26);
  light.addColorStop(0, withAlpha(glow, 0.55));
  light.addColorStop(1, withAlpha(glow, 0));
  g.fillStyle = light;
  g.fillRect(-26, -12, 52, 52);
  g.fillStyle = body;
  g.beginPath();
  g.moveTo(-5, 0);
  g.lineTo(5, 0);
  g.lineTo(11, 10);
  g.lineTo(9, 24);
  g.lineTo(-9, 24);
  g.lineTo(-11, 10);
  g.closePath();
  g.fill();
  g.fillStyle = withAlpha(glow, 0.9);
  g.fillRect(-6, 9, 12, 12);
  g.fillStyle = body;
  g.fillRect(-1, 9, 2, 12);
  g.beginPath();
  g.moveTo(-4, 24);
  g.lineTo(4, 24);
  g.lineTo(0, 31);
  g.fill();
  g.restore();
}

function bunting(g: G, colours: string[], t: number): void {
  const y = TOP + 2;
  g.strokeStyle = withAlpha("#01411c", 0.6);
  g.lineWidth = 1.5;
  g.beginPath();
  g.moveTo(0, y);
  g.quadraticCurveTo(W / 2, y + 18, W, y);
  g.stroke();
  const flags = 11;
  for (let i = 0; i < flags; i++) {
    const s = (i + 0.5) / flags;
    const x = s * W;
    const sag = 18 * 4 * s * (1 - s) * 0.5;
    const flutter = Math.sin(t * 3 + i) * 1.5;
    g.fillStyle = colours[i % colours.length] ?? "#ffffff";
    g.beginPath();
    g.moveTo(x - 11, y + sag);
    g.lineTo(x + 11, y + sag);
    g.lineTo(x + flutter, y + sag + 20);
    g.closePath();
    g.fill();
    g.strokeStyle = withAlpha("#01411c", 0.35);
    g.lineWidth = 1;
    g.stroke();
  }
}

function marigolds(g: G, t: number): void {
  const y = TOP;
  for (let i = 0; i <= 18; i++) {
    const s = i / 18;
    const x = s * W;
    const sag = 26 * 4 * s * (1 - s);
    const r = 6 + (i % 3 === 0 ? 1.5 : 0);
    g.fillStyle = i % 2 === 0 ? "#f59e0b" : "#fbbf24";
    g.beginPath();
    g.arc(x, y + sag + Math.sin(t * 2 + i) * 0.8, r, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = withAlpha("#b45309", 0.7);
    g.beginPath();
    g.arc(x, y + sag, r * 0.35, 0, Math.PI * 2);
    g.fill();
  }
  for (const x of [14, W - 14]) {
    for (let j = 0; j < 4; j++) {
      g.fillStyle = j % 2 === 0 ? "#f97316" : "#fbbf24";
      g.beginPath();
      g.arc(x, y + 14 + j * 12, 5, 0, Math.PI * 2);
      g.fill();
    }
  }
}

function snowflake(g: G, x: number, y: number, r: number): void {
  g.strokeStyle = withAlpha("#60a5fa", 0.75);
  g.lineWidth = 1.4;
  for (let i = 0; i < 3; i++) {
    const a = (i * Math.PI) / 3;
    g.beginPath();
    g.moveTo(x - Math.cos(a) * r, y - Math.sin(a) * r);
    g.lineTo(x + Math.cos(a) * r, y + Math.sin(a) * r);
    g.stroke();
  }
}

/** The theme's decorations, drawn over a frame of the game. */
export function drawTheme(g: G, theme: Theme | undefined, t: number, accent: string): void {
  if (!theme || theme === "none") return;
  g.save();
  switch (theme) {
    case "ramzan": {
      crescent(g, 26, TOP + 18, 11, "#f2c14e");
      star(g, 48, TOP + 10, 3.5, withAlpha("#fff3c4", 0.6 + Math.sin(t * 3) * 0.3));
      star(g, W - 70, TOP + 16, 3, withAlpha("#fff3c4", 0.6 + Math.sin(t * 2.4 + 1) * 0.3));
      lantern(g, W - 30, TOP + 40, t, "#ffd36b", "#1f5f5b");
      lantern(g, W - 62, TOP + 22, t + 1, "#ffd36b", "#7a3e8e");
      break;
    }
    case "eid": {
      crescent(g, W - 30, TOP + 18, 12, "#f2c14e");
      star(g, W - 54, TOP + 10, 4, "#f2c14e");
      for (let i = 0; i < 13; i++) {
        const x = 18 + i * 25;
        const sag = Math.sin((i / 12) * Math.PI) * 10;
        const on = Math.floor(t * 4 + i) % 3 !== 0;
        g.fillStyle = withAlpha(i % 2 === 0 ? accent : "#f2c14e", on ? 0.95 : 0.35);
        g.beginPath();
        g.ellipse(x, TOP + 6 + sag, 3.5, 5, 0, 0, Math.PI * 2);
        g.fill();
      }
      break;
    }
    case "independence_day": {
      bunting(g, ["#01411c", "#ffffff"], t);
      crescent(g, 24, TOP + 42, 10, "#01411c");
      star(g, 34, TOP + 37, 4, "#01411c");
      break;
    }
    case "wedding_season": {
      marigolds(g, t);
      break;
    }
    case "winter_sale": {
      for (let i = 0; i < 12; i++) {
        const x = ((i * 67 + t * (8 + (i % 4) * 3)) % (W + 20)) - 10;
        const y = (i * 53 + t * (24 + (i % 3) * 9)) % 560 + 50;
        snowflake(g, x, y, 3 + (i % 3));
      }
      g.fillStyle = withAlpha("#93c5fd", 0.8);
      for (let x = 6; x < W; x += 22) {
        const drop = 8 + ((x * 7) % 9);
        g.beginPath();
        g.moveTo(x - 5, TOP - 6);
        g.lineTo(x + 5, TOP - 6);
        g.lineTo(x, TOP - 6 + drop);
        g.closePath();
        g.fill();
      }
      break;
    }
  }
  g.restore();
}
