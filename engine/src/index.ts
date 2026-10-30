/** Public surface of the engine, imported by every template's game.ts. */

export type { SfxName } from "./audio";
export { contrast, darken, lighten, mix, parseHex, toHex, withAlpha } from "./color";
export type { GameConfig, Palette } from "./config";
export {
  backdrop,
  drawFit,
  drawProduct,
  fitFont,
  H,
  productPicture,
  recoloured,
  roundRect,
  softShadow,
  Sparks,
  tile3d,
  W,
} from "./draw";
export type { ProductPicture } from "./draw";
export type {
  GameContext,
  Images,
  Outcome,
  PointerInfo,
  ProductFrames,
  Progress,
  TemplateFactory,
  TemplateGame,
} from "./game";
export type { Rng } from "./random";
export { startGame } from "./runtime";

/**
 * Read a difficulty parameter. Every value comes from the template's template.json, resolved
 * by the builder; a missing one is a build error, so templates never carry their own copies.
 */
export function param(difficulty: Record<string, number>, name: string): number {
  const value = difficulty[name];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`Reel2Play: difficulty parameter "${name}" is missing`);
  }
  return value;
}
