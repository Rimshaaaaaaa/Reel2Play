/**
 * Quiz: three quick questions about the product, answered from the shop's own video. Each
 * question shows the product, then three answer tiles; tap one before the bar runs out. Get
 * most of them right to win. Original artwork drawn in code: a quiz-show podium with bulbs.
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

const INTRO_S = 0.8;
const OPTION = { x: 34, y: 400, w: W - 68, h: 54, gap: 14 };

export interface QuizItem {
  question: string;
  options: string[];
  answer: number;
}

type Step = "intro" | "reading" | "answering" | "reveal";

/** Lines of `text` that fit in `width` at the current font. */
export function wrap(g: CanvasRenderingContext2D, text: string, width: number): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/)) {
    const next = line ? `${line} ${word}` : word;
    if (line && g.measureText(next).width > width) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines;
}

export function optionRect(index: number): { x: number; y: number; w: number; h: number } {
  return { x: OPTION.x, y: OPTION.y + index * (OPTION.h + OPTION.gap), w: OPTION.w, h: OPTION.h };
}

export function createQuiz(): TemplateGame {
  let items: QuizItem[] = [];
  let current = 0;
  let step: Step = "intro";
  let stepLeft = INTRO_S;
  let readS = 1.8;
  let answerS = 7;
  let revealS = 2.4;
  let chosen: number | null = null;
  let right = 0;
  let finished = false;
  const sparks = new Sparks();

  const needed = () => Math.max(1, items.length - 1);

  const advanceStep = (ctx: GameContext) => {
    if (step === "intro") {
      step = "reading";
      stepLeft = readS;
    } else if (step === "reading") {
      step = "answering";
      stepLeft = answerS;
    } else if (step === "answering") {
      step = "reveal";
      stepLeft = revealS;
      ctx.sfx.play("miss");
    } else if (current + 1 < items.length) {
      current += 1;
      chosen = null;
      step = "intro";
      stepLeft = INTRO_S;
    } else {
      finished = true;
    }
  };

  const drawPodium = (g: CanvasRenderingContext2D, ctx: GameContext) => {
    const p = ctx.config.palette;
    tile3d(g, 70, 118, W - 140, 150, darken(p.primary, 0.1), { radius: 26, edge: 10 });
    for (let i = 0; i < 9; i++) {
      const on = Math.floor(ctx.elapsed * 6 + i) % 3 === 0;
      g.fillStyle = on ? lighten(p.accent, 0.3) : withAlpha("#ffffff", 0.35);
      g.beginPath();
      g.arc(92 + i * ((W - 184) / 8), 130, 4, 0, Math.PI * 2);
      g.fill();
    }
    drawProduct(g, ctx.images, ctx.elapsed, W / 2, 200, 170, 110);
  };

  return {
    id: "quiz",
    init(ctx) {
      const d = ctx.config.difficulty;
      readS = param(d, "read_seconds");
      answerS = param(d, "answer_seconds");
      revealS = param(d, "reveal_seconds");
      items = (ctx.config.content?.quiz ?? []).filter(
        (q) => q.options.length >= 2 && q.answer >= 0 && q.answer < q.options.length,
      );
      if (items.length === 0) {
        // A safe question the game always knows the answer to.
        const name = ctx.config.text.productName;
        items = [{ question: "Which product is in this game?", options: [name], answer: 0 }];
      }
      current = 0;
      step = "intro";
      stepLeft = INTRO_S;
      chosen = null;
      right = 0;
      finished = false;
    },
    update(dt, ctx) {
      sparks.update(dt);
      if (finished) return;
      stepLeft -= dt;
      if (stepLeft <= 0) advanceStep(ctx);
    },
    draw(g, ctx) {
      const p = ctx.config.palette;
      backdrop(g, p.background, [p.primary, p.accent], ctx.elapsed);
      drawPodium(g, ctx);
      const item = items[current];
      if (!item) return;
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.direction = ctx.config.direction;
      g.fillStyle = p.muted;
      g.font = `700 15px ${ctx.font}`;
      g.fillText(`${current + 1} / ${items.length}`, W / 2, 296);
      if (step !== "intro") {
        g.fillStyle = p.ink;
        g.font = `800 21px ${ctx.font}`;
        const lines = wrap(g, item.question, W - 60).slice(0, 3);
        lines.forEach((line, i) => g.fillText(line, W / 2, 330 + (i - (lines.length - 1) / 2) * 26));
      }
      if (step === "answering" || step === "reveal") {
        item.options.forEach((option, i) => {
          const r = optionRect(i);
          let colour = p.surface;
          if (step === "reveal" && i === item.answer) colour = lighten(p.accent, 0.1);
          else if (step === "reveal" && i === chosen) colour = "#e4e1df";
          tile3d(g, r.x, r.y, r.w, r.h, colour, { radius: 14, edge: 6, lift: chosen === i ? 2 : 0 });
          g.fillStyle = step === "reveal" && i === item.answer ? p.accentInk : p.ink;
          g.font = fitFont(g, option, r.w - 30, 19, ctx.font, 700);
          g.fillText(option, r.x + r.w / 2, r.y + r.h / 2);
        });
      }
      if (step === "answering") {
        const share = Math.max(0, stepLeft / answerS);
        g.fillStyle = withAlpha(p.ink, 0.1);
        roundRect(g, OPTION.x, 372, OPTION.w, 8, 4);
        g.fill();
        g.fillStyle = share < 0.3 ? "#d6453d" : p.primary;
        roundRect(g, OPTION.x, 372, OPTION.w * share, 8, 4);
        g.fill();
      }
      sparks.draw(g);
    },
    pointer(event: PointerInfo, ctx) {
      if (event.phase !== "down" || step !== "answering") return;
      const item = items[current];
      if (!item) return;
      const index = item.options.findIndex((_, i) => {
        const r = optionRect(i);
        return event.x >= r.x && event.x <= r.x + r.w && event.y >= r.y && event.y <= r.y + r.h;
      });
      if (index < 0) return;
      chosen = index;
      step = "reveal";
      stepLeft = revealS;
      if (index === item.answer) {
        right += 1;
        ctx.sfx.play("coin");
        const r = optionRect(index);
        const p = ctx.config.palette;
        sparks.burst(ctx.rng, r.x + r.w / 2, r.y + r.h / 2, [p.primary, p.accent, "#ffffff"], 24, 220);
      } else {
        ctx.sfx.play("bump");
      }
    },
    progress: () => ({ score: right, goal: needed() }),
    outcome(): Outcome {
      if (!finished) return "playing";
      return right >= needed() ? "won" : "lost";
    },
    debugState: () => ({
      current,
      step,
      answer: items[current]?.answer ?? null,
      options: (items[current]?.options ?? []).map((_, i) => optionRect(i)),
      right,
      questions: items.length,
    }),
  };
}

if (typeof window !== "undefined" && (window as { R2P_CONFIG?: unknown }).R2P_CONFIG) {
  void startGame(createQuiz);
}
