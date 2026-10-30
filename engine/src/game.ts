/** The contract between the shared runtime and each game template. */

import type { Sfx } from "./audio";
import type { GameConfig } from "./config";
import type { Rng } from "./random";

export interface ProductFrames {
  image: HTMLImageElement;
  frames: number;
  fps: number;
}

export interface Images {
  product: HTMLImageElement;
  productPhoto: HTMLImageElement | null;
  logo: HTMLImageElement | null;
  productFrames: ProductFrames | null;
  /** The shop's other products (feature 11); empty for a single product. */
  more: HTMLImageElement[];
}

export interface GameContext {
  config: GameConfig;
  rng: Rng;
  sfx: Sfx;
  images: Images;
  /** Font stack for the game's language (system fonts only). */
  font: string;
  /** Seconds of game time since play started. */
  elapsed: number;
}

export type PointerPhase = "down" | "move" | "up";

export interface PointerInfo {
  phase: PointerPhase;
  /** Logical coordinates on the 360 × 640 play field. */
  x: number;
  y: number;
}

export type Outcome = "playing" | "won" | "lost";

export interface Progress {
  score: number;
  goal: number;
}

export interface TemplateGame {
  readonly id: string;
  init(ctx: GameContext): void;
  update(dt: number, ctx: GameContext): void;
  draw(g: CanvasRenderingContext2D, ctx: GameContext): void;
  pointer(event: PointerInfo, ctx: GameContext): void;
  progress(): Progress;
  outcome(ctx: GameContext): Outcome;
  /** Called once when the runtime's hard time limit stops the game. */
  timeUp?(ctx: GameContext): Outcome;
  /** Plain data for automated players and the play-tester. */
  debugState(): Record<string, unknown>;
}

export type TemplateFactory = () => TemplateGame;
