/** Scripted players: simple strategies that play each template through real taps. */
import type { Page } from "@playwright/test";
import { advance, dragAt, pace, tapAt } from "./harness";

type State = Record<string, unknown>;

const state = (page: Page) => page.evaluate(() => window.__r2p!.state() as State);
const phase = (page: Page) => page.evaluate(() => window.__r2p!.phase());

interface Item {
  x: number;
  y: number;
  kind: "product" | "dud";
}

export async function playCatch(page: Page): Promise<void> {
  while ((await phase(page)) === "playing") {
    const s = await state(page);
    const items = s.items as Item[];
    const bagY = s.bagY as number;
    const next = items
      .filter((i) => i.kind === "product" && i.y < bagY + 5)
      .sort((a, b) => b.y - a.y)[0];
    if (next) await tapAt(page, next.x, 560);
    await advance(page, 0.12);
  }
}

interface Crate {
  ahead: number;
  w: number;
}

export async function playRunner(page: Page): Promise<void> {
  while ((await phase(page)) === "playing") {
    const s = await state(page);
    const crates = s.crates as Crate[];
    const due = crates.some((c) => c.ahead > 18 && c.ahead < 70);
    if (due && s.onGround) await tapAt(page, 180, 300);
    await advance(page, 0.04);
  }
}

export async function playPuzzle(page: Page, thinkSeconds = pace("puzzle")): Promise<void> {
  while ((await phase(page)) === "playing") {
    const s = await state(page);
    const tiles = s.tiles as number[];
    const cells = s.cells as { x: number; y: number; w: number; h: number }[];
    const wrong = tiles.findIndex((piece, cell) => piece !== cell);
    if (wrong < 0) {
      await advance(page, 0.1);
      continue;
    }
    const holder = tiles.indexOf(wrong);
    for (const cell of [wrong, holder]) {
      const r = cells[cell]!;
      await tapAt(page, r.x + r.w / 2, r.y + r.h / 2);
      await advance(page, thinkSeconds);
    }
  }
}

interface Card {
  face: number;
  x: number;
  y: number;
  w: number;
  h: number;
  up: boolean;
  matched: boolean;
}

/** Plays like a person: remembers only cards it has seen face up. */
export async function playMemory(page: Page, thinkSeconds = pace("memory")): Promise<void> {
  const seen = new Map<number, number>();
  const tap = async (cards: Card[], index: number) => {
    const c = cards[index]!;
    await tapAt(page, c.x + c.w / 2, c.y + c.h / 2);
    await advance(page, thinkSeconds);
    const after = (await state(page)).cards as Card[];
    seen.set(index, after[index]!.face);
  };
  while ((await phase(page)) === "playing") {
    const s = await state(page);
    const cards = s.cards as Card[];
    if (s.peeking || s.busy || cards.some((c) => c.up && !c.matched)) {
      await advance(page, 0.1);
      continue;
    }
    const open = [...seen].filter(([i]) => !cards[i]!.matched);
    const pair = open.find(([i, face]) => open.some(([j, other]) => j !== i && other === face));
    if (pair) {
      const mate = open.find(([j, face]) => j !== pair[0] && face === pair[1])!;
      await tap(cards, pair[0]);
      await tap(cards, mate[0]);
      continue;
    }
    const unseen = cards.map((_, i) => i).filter((i) => !seen.has(i) && !cards[i]!.matched);
    if (unseen.length === 0) {
      await advance(page, 0.1);
      continue;
    }
    await tap(cards, unseen[0]!);
    const face = seen.get(unseen[0]!)!;
    const known = open.find(([, other]) => other === face);
    await tap(cards, known ? known[0] : unseen[1] ?? unseen[0]!);
  }
}

/** Rubs the card in rows, top to bottom, pass after pass. */
export async function playScratch(page: Page, strokeSeconds = pace("scratch")): Promise<void> {
  const s = await state(page);
  const card = s.card as { x: number; y: number; w: number; h: number };
  const step = (s.brush as number) * 1.5;
  let row = 0;
  while ((await phase(page)) === "playing") {
    const rows = Math.ceil(card.h / step);
    const y = card.y + step / 2 + (row % rows) * step;
    const [x1, x2] = row % 2 === 0 ? [card.x + 4, card.x + card.w - 4] : [card.x + card.w - 4, card.x + 4];
    await dragAt(page, x1, y, x2, y);
    await advance(page, strokeSeconds);
    row += 1;
  }
}

interface Spot {
  x: number;
  y: number;
  state: string;
}

export async function playSpots(page: Page, reactSeconds = pace("spots")): Promise<void> {
  while ((await phase(page)) === "playing") {
    const spots = (await state(page)).spots as Spot[];
    const lit = spots.find((spot) => spot.state === "lit");
    if (lit) {
      await tapAt(page, lit.x, lit.y);
      await advance(page, reactSeconds);
    } else {
      await advance(page, 0.1);
    }
  }
}

export async function playStack(page: Page): Promise<void> {
  while ((await phase(page)) === "playing") {
    const s = await state(page);
    const moving = s.moving as { x: number } | null;
    const top = s.top as { x: number };
    if (moving && Math.abs(moving.x - top.x) <= 3) await tapAt(page, 180, 320);
    await advance(page, 1 / 60);
  }
}

export async function playQuiz(page: Page, thinkSeconds = pace("quiz")): Promise<void> {
  while ((await phase(page)) === "playing") {
    const s = await state(page);
    if (s.step === "answering") {
      await advance(page, thinkSeconds);
      const box = (s.options as { x: number; y: number; w: number; h: number }[])[s.answer as number]!;
      await tapAt(page, box.x + box.w / 2, box.y + box.h / 2);
    }
    await advance(page, 0.1);
  }
}

export async function playColours(page: Page, thinkSeconds = pace("colours")): Promise<void> {
  while ((await phase(page)) === "playing") {
    const s = await state(page);
    if (s.wish !== null && s.wish !== undefined) {
      await advance(page, thinkSeconds);
      const spot = (s.swatches as { x: number; y: number }[])[s.wish as number]!;
      await tapAt(page, spot.x, spot.y);
    }
    await advance(page, 0.1);
  }
}

export async function idle(page: Page): Promise<void> {
  while ((await phase(page)) === "playing") await advance(page, 0.5);
}

/** Feature 24: taps where the mechanic's own hint says a skilled player would. */
export async function playCustom(page: Page): Promise<void> {
  const step = pace("custom");
  for (let i = 0; i < 400; i++) {
    const s = await page.evaluate(() => ({ phase: window.__r2p!.phase(), state: window.__r2p!.state() }));
    if (s.phase !== "playing") return;
    const hint = (s.state as { hint: [number, number] | null }).hint;
    if (hint) await tapAt(page, hint[0], hint[1]);
    await advance(page, step);
  }
}
