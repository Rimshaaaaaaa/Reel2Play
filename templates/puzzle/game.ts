/**
 * Puzzle: the product picture on raised 3D tiles, 3 × 3. Tap two tiles to swap them until
 * the picture is whole. A hint glows after a while, and at the time limit the picture
 * solves itself so the player always sees the product.
 */

import {
  backdrop,
  darken,
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

const SIZE = 3;
const BOARD = 300;
const GAP = 6;
const BOARD_X = (W - BOARD) / 2;
const BOARD_Y = 200;
const CELL = (BOARD - GAP * (SIZE - 1)) / SIZE;
const SWAP_S = 0.18;

interface Swap {
  a: number;
  b: number;
  t: number;
}

export function cellRect(index: number): { x: number; y: number; w: number; h: number } {
  const col = index % SIZE;
  const row = Math.floor(index / SIZE);
  return { x: BOARD_X + col * (CELL + GAP), y: BOARD_Y + row * (CELL + GAP), w: CELL, h: CELL };
}

/** A shuffle of 0..8 with exactly `misplaced` tiles out of place (never already solved). */
export function shuffled(misplaced: number, pick: (n: number) => number): number[] {
  const count = Math.max(2, Math.min(SIZE * SIZE, Math.round(misplaced)));
  const positions = Array.from({ length: SIZE * SIZE }, (_, i) => i);
  const chosen: number[] = [];
  while (chosen.length < count) {
    const candidate = positions.splice(pick(positions.length), 1)[0];
    if (candidate !== undefined) chosen.push(candidate);
  }
  const tiles = Array.from({ length: SIZE * SIZE }, (_, i) => i);
  // A single cycle through the chosen cells moves every one of them out of place.
  chosen.forEach((cell, i) => {
    tiles[cell] = chosen[(i + 1) % chosen.length] as number;
  });
  return tiles;
}

export function createPuzzle(): TemplateGame {
  let tiles: number[] = [];
  let selected: number | null = null;
  let swap: Swap | null = null;
  let hintAt = 15;
  let solvedByPlayer = false;
  let autoSolved = false;
  let moves = 0;
  const sparks = new Sparks();

  const correct = () => tiles.filter((piece, cell) => piece === cell).length;
  const solved = () => correct() === SIZE * SIZE;

  const hint = (): { from: number; to: number } | null => {
    const from = tiles.findIndex((piece, cell) => piece !== cell);
    if (from < 0) return null;
    return { from, to: tiles[from] as number };
  };

  const doSwap = (a: number, b: number, ctx: GameContext) => {
    const pieceA = tiles[a] as number;
    tiles[a] = tiles[b] as number;
    tiles[b] = pieceA;
    swap = { a, b, t: SWAP_S };
    moves += 1;
    ctx.sfx.play("swap");
    if (solved()) {
      solvedByPlayer = true;
      const p = ctx.config.palette;
      sparks.burst(ctx.rng, W / 2, BOARD_Y + BOARD / 2, [p.primary, p.accent, "#ffffff"], 50, 280);
    }
  };

  const picture = (ctx: GameContext): HTMLImageElement => ctx.images.productPhoto ?? ctx.images.product;

  const drawPiece = (g: CanvasRenderingContext2D, piece: number, x: number, y: number,
    ctx: GameContext) => {
    const img = picture(ctx);
    const side = Math.min(img.width, img.height);
    const sx = (img.width - side) / 2 + (piece % SIZE) * (side / SIZE);
    const sy = (img.height - side) / 2 + Math.floor(piece / SIZE) * (side / SIZE);
    g.save();
    roundRect(g, x + 3, y + 3, CELL - 6, CELL - 6, 10);
    g.clip();
    g.fillStyle = ctx.config.palette.surface;
    g.fillRect(x, y, CELL, CELL);
    g.drawImage(img, sx, sy, side / SIZE, side / SIZE, x + 3, y + 3, CELL - 6, CELL - 6);
    g.restore();
  };

  return {
    id: "puzzle",
    init(ctx) {
      const d = ctx.config.difficulty;
      hintAt = param(d, "hint_at");
      tiles = shuffled(param(d, "misplaced"), (n) => ctx.rng.int(0, n - 1));
      selected = null;
      swap = null;
      solvedByPlayer = false;
      autoSolved = false;
      moves = 0;
    },
    update(dt) {
      if (swap) {
        swap.t -= dt;
        if (swap.t <= 0) swap = null;
      }
      sparks.update(dt);
    },
    draw(g, ctx) {
      const p = ctx.config.palette;
      backdrop(g, p.background, [p.primary, p.accent], ctx.elapsed);
      tile3d(g, BOARD_X - 14, BOARD_Y - 14, BOARD + 28, BOARD + 28, darken(p.surface, 0.06), {
        radius: 22,
        edge: 10,
      });
      const thumb = 74;
      g.save();
      g.fillStyle = p.surface;
      roundRect(g, W - thumb - 24, 76, thumb, thumb, 12);
      g.fill();
      roundRect(g, W - thumb - 20, 80, thumb - 8, thumb - 8, 9);
      g.clip();
      const img = picture(ctx);
      const side = Math.min(img.width, img.height);
      g.drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side,
        W - thumb - 20, 80, thumb - 8, thumb - 8);
      g.restore();
      const showHint = ctx.elapsed >= hintAt && !solved();
      const tip = showHint ? hint() : null;
      tiles.forEach((piece, cell) => {
        const rect = cellRect(cell);
        let lift = cell === selected ? 6 : 0;
        if (swap && (cell === swap.a || cell === swap.b)) lift = 8 * (swap.t / SWAP_S);
        const home = piece === cell;
        tile3d(g, rect.x, rect.y, rect.w, rect.h, home ? lighten(p.surface, 0.1) : p.surface, {
          radius: 12,
          edge: 6,
          lift,
        });
        drawPiece(g, piece, rect.x, rect.y - lift, ctx);
        if (cell === selected || (tip && (cell === tip.from || cell === tip.to))) {
          g.strokeStyle = cell === selected ? p.primary : withAlpha(p.accent, 0.6 + Math.sin(ctx.elapsed * 6) * 0.4);
          g.lineWidth = 4;
          roundRect(g, rect.x + 2, rect.y - lift + 2, rect.w - 4, rect.h - 4, 11);
          g.stroke();
        }
      });
      sparks.draw(g);
    },
    pointer(event: PointerInfo, ctx) {
      if (event.phase !== "down" || solved()) return;
      const cell = tiles.findIndex((_, index) => {
        const r = cellRect(index);
        return event.x >= r.x && event.x <= r.x + r.w && event.y >= r.y && event.y <= r.y + r.h;
      });
      if (cell < 0) return;
      if (selected === null) {
        selected = cell;
        ctx.sfx.play("tap");
      } else if (selected === cell) {
        selected = null;
      } else {
        doSwap(selected, cell, ctx);
        selected = null;
      }
    },
    progress: () => ({ score: correct(), goal: SIZE * SIZE }),
    outcome: (): Outcome => (solvedByPlayer ? "won" : "playing"),
    timeUp() {
      tiles = Array.from({ length: SIZE * SIZE }, (_, i) => i);
      autoSolved = true;
      return "lost";
    },
    debugState: () => ({
      tiles: [...tiles],
      selected,
      moves,
      solved: solved(),
      autoSolved,
      hintAt,
      cells: tiles.map((_, index) => cellRect(index)),
    }),
  };
}

if (typeof window !== "undefined" && (window as { R2P_CONFIG?: unknown }).R2P_CONFIG) {
  void startGame(createPuzzle);
}
