/**
 * New mechanic (feature 24, Later): the director invents a mechanic and writes it as a small
 * script. Code checked the script before it reached this page (plain arithmetic, its own
 * functions and the `api` below; no globals, no network, no eval, which the page's
 * Content-Security-Policy forbids anyway), and the play-tester played it in the sandbox
 * before anyone else could. The builder puts the script in its own <script> block, which
 * defines window.__r2pMechanic; this template runs it on the shared engine: the clock, the
 * HUD, sounds, captions, the end card and the offer are the same as every template's.
 *
 * The script defines setup(api) → state, update(state, api, dt), draw(state, api), and
 * optionally tap(state, api, x, y), drag(state, api, x, y) and hint(state, api) → [x, y]
 * (where a skilled player would tap now; only the scripted play-tester uses it).
 */

import {
  backdrop,
  drawProduct,
  type GameContext,
  H,
  type Outcome,
  type PointerInfo,
  param,
  roundRect,
  type SfxName,
  softShadow,
  Sparks,
  startGame,
  type TemplateGame,
  tile3d,
  W,
  withAlpha,
} from "../../engine/src/index";

type State = unknown;

export interface Mechanic {
  setup(api: MechanicApi): State;
  update(state: State, api: MechanicApi, dt: number): void;
  draw(state: State, api: MechanicApi): void;
  tap?(state: State, api: MechanicApi, x: number, y: number): void;
  drag?(state: State, api: MechanicApi, x: number, y: number): void;
  hint?(state: State, api: MechanicApi): unknown;
}

type Colour = "primary" | "accent" | "ink" | "muted" | "surface" | "background";

export interface MechanicApi {
  readonly W: number;
  readonly H: number;
  readonly time: number;
  readonly timeLeft: number;
  readonly score: number;
  readonly goal: number;
  rng(): number;
  addScore(points: number): void;
  win(): void;
  lose(): void;
  product(x: number, y: number, size: number): void;
  circle(x: number, y: number, r: number, colour: Colour): void;
  ring(x: number, y: number, r: number, colour: Colour, width: number): void;
  rect(x: number, y: number, w: number, h: number, colour: Colour, radius: number): void;
  tile(x: number, y: number, w: number, h: number, colour: Colour): void;
  text(words: string, x: number, y: number, size: number, colour: Colour): void;
  burst(x: number, y: number): void;
  sound(name: "tap" | "catch" | "miss" | "coin" | "bump"): void;
}

const SOUNDS: readonly SfxName[] = ["tap", "catch", "miss", "coin", "bump"];
const CELEBRATE_S = 0.9;
const finite = (value: unknown, fallback = 0): number =>
  typeof value === "number" && Number.isFinite(value) ? value : fallback;

export function loadMechanic(): Mechanic | null {
  const found = (globalThis as { __r2pMechanic?: Partial<Mechanic> }).__r2pMechanic;
  if (!found || typeof found.setup !== "function" || typeof found.update !== "function" ||
    typeof found.draw !== "function") return null;
  return found as Mechanic;
}

export function createCustom(): TemplateGame {
  const mechanic = loadMechanic();
  let state: State = null;
  let score = 0;
  let goal = 10;
  let timeLimit = 25;
  let result: Outcome = "playing";
  let endedFor = 0;
  let problem: string | null = null;
  let g: CanvasRenderingContext2D | null = null;
  let current: GameContext | null = null;
  const sparks = new Sparks();

  const colourOf = (name: Colour): string => {
    const p = (current as GameContext).config.palette;
    return { primary: p.primary, accent: p.accent, ink: p.ink, muted: p.muted, surface: p.surface,
      background: p.background }[name] ?? p.ink;
  };

  const api: MechanicApi = {
    W,
    H,
    get time() { return current?.elapsed ?? 0; },
    get timeLeft() { return Math.max(0, timeLimit - (current?.elapsed ?? 0)); },
    get score() { return score; },
    get goal() { return goal; },
    rng: () => (current as GameContext).rng.next(),
    addScore(points) {
      if (result !== "playing") return;
      score = Math.max(0, Math.min(goal, score + Math.round(finite(points))));
    },
    win() { if (result === "playing") { result = "won"; current?.sfx.play("win"); } },
    lose() { if (result === "playing") result = "lost"; },
    product(x, y, size) {
      if (!g || !current) return;
      const s = Math.max(8, Math.min(220, finite(size, 60)));
      softShadow(g, finite(x), finite(y) + s * 0.45, s * 0.4, s * 0.08, 0.18);
      drawProduct(g, current.images, current.elapsed, finite(x), finite(y), s, s);
    },
    circle(x, y, r, colour) {
      if (!g) return;
      g.fillStyle = colourOf(colour);
      g.beginPath();
      g.arc(finite(x), finite(y), Math.max(0, Math.min(400, finite(r))), 0, Math.PI * 2);
      g.fill();
    },
    ring(x, y, r, colour, width) {
      if (!g) return;
      g.strokeStyle = colourOf(colour);
      g.lineWidth = Math.max(1, Math.min(20, finite(width, 3)));
      g.beginPath();
      g.arc(finite(x), finite(y), Math.max(0, Math.min(400, finite(r))), 0, Math.PI * 2);
      g.stroke();
    },
    rect(x, y, w, h, colour, radius) {
      if (!g) return;
      g.fillStyle = colourOf(colour);
      roundRect(g, finite(x), finite(y), Math.max(0, finite(w)), Math.max(0, finite(h)),
        Math.max(0, finite(radius)));
      g.fill();
    },
    tile(x, y, w, h, colour) {
      if (!g) return;
      tile3d(g, finite(x), finite(y), Math.max(4, finite(w)), Math.max(4, finite(h)), colourOf(colour),
        { radius: 8, edge: 6 });
    },
    text(words, x, y, size, colour) {
      if (!g || !current) return;
      g.fillStyle = colourOf(colour);
      g.font = `800 ${Math.max(8, Math.min(48, finite(size, 18)))}px ${current.font}`;
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.fillText(String(words).slice(0, 40), finite(x), finite(y));
    },
    burst(x, y) {
      if (!current) return;
      const p = current.config.palette;
      sparks.burst(current.rng, finite(x), finite(y), [p.primary, p.accent, "#ffffff"], 16, 200);
    },
    sound(name) {
      if (current && SOUNDS.includes(name)) current.sfx.play(name);
    },
  };

  /** Run one call into the mechanic; a mistake in it ends the game and is reported. */
  const safely = <T>(call: () => T): T | undefined => {
    if (problem) return undefined;
    try {
      return call();
    } catch (error) {
      problem = error instanceof Error ? error.message : String(error);
      result = "lost";
      console.error(`Reel2Play mechanic: ${problem}`);
      return undefined;
    }
  };

  return {
    id: "custom",
    init(ctx) {
      current = ctx;
      goal = Math.round(param(ctx.config.difficulty, "goal"));
      timeLimit = param(ctx.config.difficulty, "time_limit");
      score = 0;
      result = "playing";
      endedFor = 0;
      problem = mechanic ? null : "the mechanic script is missing";
      if (!mechanic) console.error("Reel2Play mechanic: the mechanic script is missing");
      state = mechanic ? safely(() => mechanic.setup(api)) ?? null : null;
    },
    update(dt, ctx) {
      current = ctx;
      sparks.update(dt);
      if (result !== "playing") {
        endedFor += dt;
        return;
      }
      if (mechanic) safely(() => mechanic.update(state, api, dt));
      if (score >= goal) api.win();
    },
    draw(context, ctx) {
      current = ctx;
      g = context;
      const p = ctx.config.palette;
      backdrop(context, p.background, [p.primary, p.accent], ctx.elapsed);
      if (mechanic) safely(() => mechanic.draw(state, api));
      sparks.draw(context);
      if (problem) {
        context.fillStyle = withAlpha(p.ink, 0.7);
        context.fillRect(0, H / 2 - 20, W, 40);
      }
      g = null;
    },
    pointer(event: PointerInfo, ctx) {
      current = ctx;
      if (!mechanic || result !== "playing") return;
      if (event.phase === "down" && mechanic.tap) {
        const tap = mechanic.tap;
        safely(() => tap(state, api, event.x, event.y));
      } else if (event.phase === "move" && mechanic.drag) {
        const drag = mechanic.drag;
        safely(() => drag(state, api, event.x, event.y));
      }
    },
    progress: () => ({ score, goal }),
    outcome(ctx) {
      if (result === "won") return endedFor >= CELEBRATE_S ? "won" : "playing";
      if (result === "lost") return "lost";
      return ctx.elapsed >= timeLimit ? "lost" : "playing";
    },
    timeUp: () => (score >= goal ? "won" : "lost"),
    debugState() {
      const hint = mechanic?.hint && result === "playing"
        ? safely(() => (mechanic.hint as NonNullable<Mechanic["hint"]>)(state, api))
        : null;
      const point = Array.isArray(hint) && hint.length === 2 ? [finite(hint[0]), finite(hint[1])] : null;
      return { score, goal, timeLimit, hint: point, problem };
    },
  };
}

if (typeof window !== "undefined" && (window as { R2P_CONFIG?: unknown }).R2P_CONFIG) {
  void startGame(createCustom);
}
