import { expect, type Page, test } from "@playwright/test";
import {
  advance,
  EXAMPLE_MECHANIC,
  gameHtml,
  movingProduct,
  openGame,
  startManual,
  tapAt,
  testConfig,
  tier,
} from "./harness";
import {
  idle,
  playCatch,
  playColours,
  playCustom,
  playMemory,
  playPuzzle,
  playQuiz,
  playRunner,
  playScratch,
  playSpots,
  playStack,
} from "./players";

const MAX_BYTES = 2 * 1024 * 1024;
const players: Record<string, (page: Page) => Promise<void>> = {
  catch: playCatch,
  runner: playRunner,
  puzzle: playPuzzle,
  memory: playMemory,
  scratch: playScratch,
  spots: playSpots,
  stack: playStack,
  quiz: playQuiz,
  colours: playColours,
};

for (const template of Object.keys(players)) {
  test.describe(template, () => {
    test("loads fast, with no errors and no network", async ({ page }) => {
      const watch = await openGame(page, testConfig(template));
      const firstFrame = await page.evaluate(() => window.__r2p!.firstFrameMs());
      expect(firstFrame).not.toBeNull();
      expect(firstFrame!).toBeLessThan(2000);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Catch the Sneaker!");
      expect(watch.errors).toEqual([]);
      expect(watch.requests).toEqual([]);
    });

    test("stays under 2 MB as one HTML file", () => {
      expect(Buffer.byteLength(gameHtml(testConfig(template)))).toBeLessThan(MAX_BYTES);
    });

    test("can be won by a scripted player, then ends on the offer", async ({ page }) => {
      const config = testConfig(template);
      const watch = await openGame(page, config);
      await startManual(page);
      await players[template]!(page);
      expect(await page.evaluate(() => window.__r2p!.outcome())).toBe("won");
      const seconds = await page.evaluate(() => window.__r2p!.elapsed());
      expect(seconds).toBeLessThanOrEqual(30);
      expect(seconds).toBeGreaterThanOrEqual(15);
      await expect(page.locator('[data-r2p="result"]')).toHaveText(config.text.win);
      await expect(page.locator('[data-r2p="offer"]')).toHaveText(config.text.offer!);
      await expect(page.locator('[data-r2p="price"]')).toHaveText(config.text.price!);
      await expect(page.locator('[data-r2p="cta"]')).toHaveAttribute("href", config.cta.url);
      await expect(page.getByText("Built with Muse Spark Open")).toBeVisible();
      expect(watch.errors).toEqual([]);
      expect(watch.requests).toEqual([]);
    });

    test("a player who does nothing still ends on the offer", async ({ page }) => {
      const config = testConfig(template);
      await openGame(page, config);
      await startManual(page);
      await idle(page);
      expect(await page.evaluate(() => window.__r2p!.outcome())).toBe("lost");
      await expect(page.locator('[data-r2p="result"]')).toHaveText(config.text.lose);
      await expect(page.locator('[data-r2p="offer"]')).toBeVisible();
      await expect(page.locator('[data-r2p="cta"]')).toBeVisible();
    });
  });
}

test("Urdu games read right to left", async ({ page }) => {
  const config = testConfig("catch", {
    language: "ur",
    direction: "rtl",
    text: { ...testConfig("catch").text, title: "جوتا پکڑیں", ctaLabel: "واٹس ایپ پر آرڈر کریں" },
  });
  await openGame(page, config);
  await expect(page.locator(".r2p")).toHaveAttribute("dir", "rtl");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("جوتا پکڑیں");
  await expect(page.getByRole("button", { name: "کھیلنے کے لیے ٹیپ کریں" })).toBeVisible();
});

test("replay starts a fresh run", async ({ page }) => {
  await openGame(page, testConfig("runner"));
  await startManual(page);
  await idle(page);
  await page.locator('[data-r2p="replay"]').click();
  expect(await page.evaluate(() => window.__r2p!.phase())).toBe("playing");
  expect(await page.evaluate(() => window.__r2p!.runs())).toBe(2);
});

test("the Meta build calls FbPlayableAd.onCTAClick and has no link", async ({ page }) => {
  await openGame(page, testConfig("catch", { platform: "meta" }));
  await page.evaluate(() => {
    (window as unknown as { calls: number }).calls = 0;
    (window as unknown as { FbPlayableAd: unknown }).FbPlayableAd = {
      onCTAClick: () => {
        (window as unknown as { calls: number }).calls += 1;
      },
    };
  });
  await startManual(page);
  await idle(page);
  const cta = page.locator('[data-r2p="cta"]');
  expect(await cta.evaluate((node) => node.tagName)).toBe("BUTTON");
  await cta.click();
  expect(await page.evaluate(() => (window as unknown as { calls: number }).calls)).toBe(1);
});

for (const template of ["catch", "runner"]) {
  test(`${template}: a moving product plays and the game can still be won`, async ({ page }) => {
    const plain = testConfig(template);
    const config = testConfig(template, { assets: { ...plain.assets, productFrames: movingProduct() } });
    const watch = await openGame(page, config);
    await startManual(page);
    await players[template]!(page);
    expect(await page.evaluate(() => window.__r2p!.outcome())).toBe("won");
    expect(watch.errors).toEqual([]);
    expect(watch.requests).toEqual([]);
  });
}

test("catch drops the shop's other products in turn", async ({ page }) => {
  const plain = testConfig("catch");
  const product = plain.assets.product;
  const moreProducts = [
    { image: product, name: "Synthetic sandal" },
    { image: product, name: "Synthetic boot" },
  ];
  const config = testConfig("catch", { assets: { ...plain.assets, moreProducts } });
  const watch = await openGame(page, config);
  await startManual(page);
  await players.catch!(page);
  expect(await page.evaluate(() => window.__r2p!.outcome())).toBe("won");
  expect(watch.errors).toEqual([]);
});

test("sounds show as words, and the CC button turns them off", async ({ page }) => {
  await openGame(page, testConfig("catch"));
  await startManual(page);
  const caption = page.locator('[data-r2p="caption"]');
  await players.catch!(page);
  // The win plays a sound; the caption hides again after a moment of game time.
  await expect(caption).toBeHidden();
  await page.locator('[data-r2p="replay"]').click();
  await page.evaluate(() => window.__r2p!.advance(0.05));
  await expect(caption).toBeHidden();
  await page.locator(".r2p-cc").click();
  await expect(page.locator(".r2p-cc")).toHaveAttribute("aria-pressed", "false");
});

test("a caption appears when the player catches something", async ({ page }) => {
  await openGame(page, testConfig("catch"));
  await startManual(page);
  const caption = page.locator('[data-r2p="caption"]');
  let seen = false;
  for (let i = 0; i < 400 && !seen; i++) {
    const s = await page.evaluate(() => window.__r2p!.state() as { items: { x: number; y: number; kind: string }[]; bagY: number });
    const next = s.items.filter((it) => it.kind === "product" && it.y < s.bagY + 5).sort((a, b) => b.y - a.y)[0];
    if (next) await tapAt(page, next.x, 560);
    await page.evaluate(() => window.__r2p!.advance(0.05));
    seen = await caption.isVisible();
  }
  expect(seen).toBe(true);
  await expect(caption).toHaveText(/Caught!|Oops/);
  await page.evaluate(() => window.__r2p!.advance(1));
  await expect(caption).toBeHidden();
});

test("the scratch card can be cleared with taps alone", async ({ page }) => {
  await openGame(page, testConfig("scratch"));
  await startManual(page);
  const card = (await page.evaluate(() => window.__r2p!.state())) as { card: { x: number; y: number; w: number; h: number } };
  const { x, y, w, h } = card.card;
  let i = 0;
  while ((await page.evaluate(() => window.__r2p!.phase())) === "playing") {
    const cols = 7;
    const rows = 7;
    const cell = i % (cols * rows);
    await tapAt(page, x + ((cell % cols) + 0.5) * (w / cols), y + (Math.floor(cell / cols) + 0.5) * (h / rows));
    await page.evaluate(() => window.__r2p!.advance(0.3));
    i += 1;
  }
  expect(await page.evaluate(() => window.__r2p!.outcome())).toBe("won");
});

test("a seasonal theme greets the player in the game's language", async ({ page }) => {
  await openGame(page, testConfig("catch", { theme: "eid" }));
  await expect(page.locator('[data-r2p="intro"] .r2p-occasion')).toHaveText("Eid Mubarak");
  await openGame(page, testConfig("catch", { theme: "independence_day", language: "ur", direction: "rtl" }));
  await expect(page.locator('[data-r2p="intro"] .r2p-occasion')).toHaveText("یومِ آزادی مبارک");
  await startManual(page);
  await idle(page);
  await expect(page.locator('[data-r2p="end"] .r2p-occasion')).toBeVisible();
});

for (const [layout, width, height] of [["square", 540, 540], ["landscape", 960, 540]] as const) {
  test(`the ${layout} page puts the offer beside the game`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    const watch = await openGame(page, testConfig("catch", { layout }));
    await expect(page.locator(".r2p")).toHaveAttribute("data-layout", layout);
    const side = await page.locator('[data-r2p="side"]').boundingBox();
    const stage = await page.locator(".r2p-stage").boundingBox();
    expect(side && stage).toBeTruthy();
    expect(stage!.height).toBeGreaterThan(height * 0.85);
    expect(Math.abs(stage!.width / stage!.height - 9 / 16)).toBeLessThan(0.01);
    expect(side!.x + side!.width).toBeLessThanOrEqual(stage!.x + 1);
    await expect(page.locator('[data-r2p="side"]')).toContainText("20% off this week");
    await startManual(page);
    await players.catch!(page);
    await expect(page.locator('[data-r2p="cta"]')).toBeVisible();
    expect(watch.errors).toEqual([]);
  });
}

test("the Meta playable is always portrait", async ({ page }) => {
  await openGame(page, testConfig("catch", { layout: "landscape", platform: "meta" }));
  await expect(page.locator(".r2p")).toHaveAttribute("data-layout", "portrait");
});

test("a phone asking for less motion still plays the same game", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const watch = await openGame(page, testConfig("catch"));
  await startManual(page);
  await players.catch!(page);
  expect(await page.evaluate(() => window.__r2p!.outcome())).toBe("won");
  expect(watch.errors).toEqual([]);
});

test("a hosted win gets its own code, on the card and in the order message", async ({ page }) => {
  const asked: string[] = [];
  await page.route("https://api.test/**", async (route) => {
    const url = route.request().url();
    if (url.endsWith("/api/coupons")) {
      asked.push(route.request().postData() ?? "");
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        headers: { "Access-Control-Allow-Origin": "*" },
        body: JSON.stringify({ code: "R2P-AB12-CD34" }),
      });
    } else {
      await route.fulfill({ status: 204, headers: { "Access-Control-Allow-Origin": "*" } });
    }
  });
  const config = testConfig("catch", {
    cta: { kind: "whatsapp", url: "https://wa.me/923001234567?text=Hi%20My%20code:%20R2PTEST" },
    analytics: {
      endpoint: "https://api.test/api/events",
      adId: "ad-1",
      variant: "A",
      coupons: "https://api.test/api/coupons",
    },
  });
  await openGame(page, config);
  await startManual(page);
  await playCatch(page);
  expect(await page.evaluate(() => window.__r2p!.outcome())).toBe("won");
  const coupon = page.locator('[data-r2p="coupon"]');
  await expect(coupon).toContainText("R2P-AB12-CD34");
  await expect(coupon).toHaveAttribute("data-unique", "true");
  const href = await page.locator('[data-r2p="cta"]').getAttribute("href");
  expect(href).toContain("R2P-AB12-CD34");
  expect(href).not.toContain(config.coupon!);
  expect(asked).toHaveLength(1);
  expect(JSON.parse(asked[0]!)).toEqual({ ad: "ad-1", variant: "A" });
});

test.describe("a new mechanic (feature 24)", () => {
  const custom = () =>
    testConfig("custom", {
      difficulty: tier("custom"),
      content: { facts: [], quiz: [], mechanic: EXAMPLE_MECHANIC },
    });

  test("runs the checked script, can be won by its hint, and stays offline", async ({ page }) => {
    const config = custom();
    const watch = await openGame(page, config);
    await startManual(page);
    await playCustom(page);
    expect(await page.evaluate(() => window.__r2p!.outcome())).toBe("won");
    const seconds = await page.evaluate(() => window.__r2p!.elapsed());
    expect(seconds).toBeGreaterThanOrEqual(15);
    expect(seconds).toBeLessThanOrEqual(30);
    await expect(page.locator('[data-r2p="offer"]')).toHaveText(config.text.offer!);
    await expect(page.getByText("Built with Muse Spark Open")).toBeVisible();
    expect(watch.errors).toEqual([]);
    expect(watch.requests).toEqual([]);
    // The page took the Function constructor away before the script ran.
    expect(await page.evaluate(() => (() => 0).constructor)).toBeUndefined();
  });

  // The pipeline seeds each game from its ad id, so the example must fit 15 to 30 s on any
  // seed and every tier, not only on the fixed seed of the other tests.
  for (const level of ["easy", "normal", "hard"] as const) {
    test(`the ${level} tier is won in 15 to 30 s on every seed`, async ({ page }) => {
      for (const seed of [1, 42, 2026, 31337, 2147483646]) {
        await openGame(
          page,
          testConfig("custom", {
            seed,
            difficulty: tier("custom", level),
            content: { facts: [], quiz: [], mechanic: EXAMPLE_MECHANIC },
          }),
        );
        await startManual(page);
        await playCustom(page);
        const run = await page.evaluate(() => ({
          outcome: window.__r2p!.outcome(),
          seconds: window.__r2p!.elapsed(),
        }));
        expect(run.outcome, `seed ${seed}`).toBe("won");
        expect(run.seconds, `seed ${seed}`).toBeGreaterThanOrEqual(15);
        expect(run.seconds, `seed ${seed}`).toBeLessThanOrEqual(30);
      }
    });
  }

  test("a mistake in the script ends the game and is reported", async ({ page }) => {
    const broken = EXAMPLE_MECHANIC.replace("state.wait -= dt;", "state.missing.wait -= dt;");
    const watch = await openGame(
      page,
      testConfig("custom", { difficulty: tier("custom"), content: { mechanic: broken } }),
    );
    await startManual(page);
    await advance(page, 0.2);
    expect(await page.evaluate(() => window.__r2p!.outcome())).toBe("lost");
    expect(watch.errors.join(" ")).toContain("Reel2Play mechanic");
  });
});

test("a published game lets a winner challenge a friend, with only the score", async ({ page }) => {
  const config = testConfig("catch", {
    analytics: { endpoint: "https://api.test/api/events", adId: "ad-1", variant: "A" },
  });
  const sent: string[] = [];
  await page.route("https://api.test/**", async (route) => {
    sent.push(route.request().postData() ?? "");
    await route.fulfill({ status: 204, headers: { "Access-Control-Allow-Origin": "*" } });
  });
  await page.route("https://play.test/**", (route) =>
    route.fulfill({ status: 200, contentType: "text/html", body: gameHtml(config) }),
  );
  await page.goto("https://play.test/g/AbC1234?beat=7-10-18.4&from=share");
  await page.waitForFunction(() => window.__r2p?.phase() === "intro");
  await expect(page.locator('[data-r2p="challenge"]')).toHaveText(
    "A friend scored 7 of 10 in 18.4 s. Can you beat it?",
  );
  await startManual(page);
  await playCatch(page);
  const share = page.locator('[data-r2p="share"]');
  await expect(share).toBeVisible();
  const href = decodeURIComponent((await share.getAttribute("href"))!);
  expect(href).toMatch(/^https:\/\/wa\.me\/\?text=I scored 10 of 10 in \d+\.\d s/);
  expect(href).toContain("https://play.test/g/AbC1234?beat=10-10-");
  expect(href).toContain("&from=share");
  expect(sent.some((body) => body.includes('"from":"share"'))).toBe(true);
});
