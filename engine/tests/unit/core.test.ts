import { describe, expect, it, vi } from "vitest";
import { recipe, Sfx } from "../../src/audio";
import { contrast, darken, lighten, luminance, mix, parseHex, toHex, withAlpha } from "../../src/color";
import { readConfig } from "../../src/config";
import { productPicture, Sparks } from "../../src/draw";
import type { Images } from "../../src/game";
import { directionFor, fontStack, words } from "../../src/i18n";
import { param } from "../../src/index";
import { challengeIntro, challengeLink, challengeText, readChallenge } from "../../src/challenge";
import { createPlatform, pageAnalytics, playSource } from "../../src/platform";
import { createRng } from "../../src/random";
import { toLogical } from "../../src/runtime";
import { buildUi } from "../../src/ui";
import { shuffled } from "../../../templates/puzzle/game";
import { testConfig } from "./config";

describe("colour", () => {
  it("parses, mixes and shades", () => {
    expect(parseHex("#c8243a")).toEqual({ r: 200, g: 36, b: 58 });
    expect(toHex({ r: 300, g: -4, b: 15.6 })).toBe("#ff0010");
    expect(mix("#000000", "#ffffff", 0.5)).toBe("#808080");
    expect(lighten("#000000", 1)).toBe("#ffffff");
    expect(darken("#ffffff", 1)).toBe("#000000");
    expect(withAlpha("#ff0000", 2)).toBe("rgba(255, 0, 0, 1)");
    expect(() => parseHex("red")).toThrow(/rrggbb/);
  });

  it("measures contrast the WCAG way", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 0);
    expect(contrast("#777777", "#777777")).toBe(1);
    expect(luminance("#ffffff")).toBeCloseTo(1);
  });
});

describe("random", () => {
  it("is repeatable for a seed", () => {
    const a = createRng(42);
    const b = createRng(42);
    expect([a.next(), a.next()]).toEqual([b.next(), b.next()]);
    const r = createRng(1);
    for (let i = 0; i < 50; i++) {
      const n = r.int(2, 4);
      expect(n).toBeGreaterThanOrEqual(2);
      expect(n).toBeLessThanOrEqual(4);
    }
    expect(r.shuffle([1, 2, 3, 4]).sort()).toEqual([1, 2, 3, 4]);
    expect(() => r.pick([])).toThrow();
    expect(createRng(0).next()).toBeGreaterThanOrEqual(0);
  });
});

describe("puzzle shuffle", () => {
  it("moves exactly the asked number of tiles and is never solved", () => {
    const rng = createRng(9);
    for (const misplaced of [2, 4, 7, 9, 20]) {
      const tiles = shuffled(misplaced, (n) => rng.int(0, n - 1));
      const wrong = tiles.filter((piece, cell) => piece !== cell).length;
      expect(wrong).toBe(Math.min(9, Math.max(2, misplaced)));
      expect([...tiles].sort()).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8]);
    }
  });
});

describe("words and fonts", () => {
  it("has Urdu and English interface words", () => {
    expect(words("ur").play).toMatch(/ٹیپ/);
    expect(words("en").play).toBe("Tap to play");
    expect(directionFor("ur")).toBe("rtl");
    expect(directionFor("en")).toBe("ltr");
    expect(fontStack("ur")).toMatch(/Nastaliq/);
  });
});

describe("config and params", () => {
  it("rejects missing or incomplete configs", () => {
    expect(() => readConfig(undefined)).toThrow(/no game config/);
    expect(() => readConfig({ version: 2 })).toThrow(/incomplete/);
    expect(readConfig(testConfig()).template).toBe("catch");
    expect(param({ goal: 8 }, "goal")).toBe(8);
    expect(() => param({}, "goal")).toThrow(/goal/);
  });
});

describe("platform", () => {
  it("hosted pages link out and count events without personal data", () => {
    const beacon = vi.fn(() => true);
    Object.defineProperty(navigator, "sendBeacon", { value: beacon, configurable: true });
    const hosted = createPlatform(
      testConfig({ analytics: { endpoint: "https://api.test/e", adId: "ad1", variant: "A" } }),
    );
    expect(hosted.ctaHref).toMatch(/^https:\/\/wa\.me\//);
    hosted.onCta();
    hosted.track("finish", { seconds: 18.2, won: true });
    expect(beacon).toHaveBeenCalledTimes(2);
    const silent = createPlatform(testConfig());
    silent.track("play");
    expect(beacon).toHaveBeenCalledTimes(2);
  });

  it("hosted pages may name the analytics endpoint in a meta tag", () => {
    const beacon = vi.fn(() => true);
    Object.defineProperty(navigator, "sendBeacon", { value: beacon, configurable: true });
    expect(pageAnalytics()).toBeNull();
    const tag = document.createElement("meta");
    tag.name = "r2p-analytics";
    tag.content = JSON.stringify({ endpoint: "https://api.test/api/events", adId: "ad9" });
    document.head.append(tag);
    expect(pageAnalytics()).toEqual({ endpoint: "https://api.test/api/events", adId: "ad9", variant: "A" });
    createPlatform(testConfig()).track("finish", { seconds: 17.4, won: true });
    const [url, blob] = beacon.mock.calls[0] as unknown as [string, Blob];
    expect(url).toBe("https://api.test/api/events");
    expect(blob.type).toBe("text/plain");
    tag.content = "not json";
    expect(pageAnalytics()).toBeNull();
    tag.remove();
  });

  it("marks plays from the counter poster and website embeds, and nothing else", () => {
    expect(playSource("?from=qr")).toBe("qr");
    expect(playSource("?layout=landscape&from=embed")).toBe("embed");
    expect(playSource("?from=someone@example.com")).toBeNull();
    expect(playSource("")).toBeNull();
  });

  it("asks for one unique win code per visit and keeps the shared code when offline", async () => {
    const analytics = {
      endpoint: "https://api.test/api/events",
      adId: "ad1",
      variant: "B",
      coupons: "https://api.test/api/coupons",
    };
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ code: "R2P-AB12-CD34" })));
    vi.stubGlobal("fetch", fetcher);
    const hosted = createPlatform(testConfig({ analytics }));
    expect(await hosted.winCode()).toBe("R2P-AB12-CD34");
    expect(await hosted.winCode()).toBe("R2P-AB12-CD34");
    expect(fetcher).toHaveBeenCalledOnce();
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(analytics.coupons);
    expect(JSON.parse(String(init.body))).toEqual({ ad: "ad1", variant: "B" });
    expect(init.credentials).toBe("omit");

    vi.stubGlobal("fetch", vi.fn(async () => new Response('{"code":"<b>no</b>"}')));
    expect(await createPlatform(testConfig({ analytics })).winCode()).toBeNull();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("busy", { status: 429 })));
    expect(await createPlatform(testConfig({ analytics })).winCode()).toBeNull();
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("offline"); }));
    expect(await createPlatform(testConfig({ analytics })).winCode()).toBeNull();
    const noCoupons = { ...analytics, coupons: undefined };
    expect(await createPlatform(testConfig({ analytics: noCoupons })).winCode()).toBeNull();
    expect(await createPlatform(testConfig({ platform: "meta" })).winCode()).toBeNull();
    vi.unstubAllGlobals();
  });

  it("Meta playables only call FbPlayableAd.onCTAClick", () => {
    const onCTAClick = vi.fn();
    (globalThis as { FbPlayableAd?: unknown }).FbPlayableAd = { onCTAClick };
    const meta = createPlatform(testConfig({ platform: "meta" }));
    expect(meta.ctaHref).toBeNull();
    meta.onCta();
    meta.track("play");
    expect(onCTAClick).toHaveBeenCalledOnce();
  });
});

describe("page", () => {
  it("builds the end card from text nodes only", () => {
    const root = document.createElement("div");
    const config = testConfig();
    config.text.offer = '<img src=x onerror="alert(1)">';
    const ui = buildUi(root, config, createPlatform(config), config.assets.product);
    expect(root.querySelector("img[src=x]")).toBeNull();
    expect(root.querySelector('[data-r2p="offer"]')?.textContent).toBe(config.text.offer);
    expect(root.querySelector('[data-r2p="price"]')?.textContent).toBe("Rs 2,499");
    expect(root.querySelector('[data-r2p="cta"]')?.getAttribute("href")).toBe(config.cta.url);
    expect(root.textContent).toContain("Built with Muse Spark Open");
    ui.setHud(15, 30, 3, 10);
    expect(root.querySelector('[data-r2p="score"]')?.textContent).toBe("3 / 10");
    ui.setHud(30, 30, 4, 0);
    expect(root.querySelector('[data-r2p="score"]')?.textContent).toBe("4");
    ui.showEnd({ won: false, seconds: 30 });
    expect(root.querySelector('[data-r2p="result"]')?.textContent).toBe(config.text.lose);
    const mute = root.querySelector<HTMLButtonElement>(".r2p-mute")!;
    const heard: boolean[] = [];
    root.addEventListener("r2p:mute", (event) => heard.push((event as CustomEvent<boolean>).detail));
    mute.click();
    mute.click();
    expect(heard).toEqual([true, false]);
  });

  it("shows a unique win code on the card and in the order message", () => {
    const root = document.createElement("div");
    const config = testConfig({ coupon: "R2P-7KQD" });
    config.cta.url = "https://wa.me/923001234567?text=Hi!%20My%20code:%20R2P-7KQD";
    const ui = buildUi(root, config, createPlatform(config), config.assets.product);
    ui.showEnd({ won: true, seconds: 18 });
    ui.showCode("R2P-AB12-CD34");
    const coupon = root.querySelector<HTMLElement>('[data-r2p="coupon"]')!;
    expect(coupon.textContent).toContain("R2P-AB12-CD34");
    expect(coupon.dataset.unique).toBe("true");
    expect(root.querySelector('[data-r2p="cta"]')?.getAttribute("href")).toBe(
      "https://wa.me/923001234567?text=Hi!%20My%20code:%20R2P-AB12-CD34",
    );
  });

  it("leaves out empty offer, price and coupon", () => {
    const root = document.createElement("div");
    const config = testConfig({ coupon: null });
    config.text.offer = null;
    config.text.price = null;
    const ui = buildUi(root, config, createPlatform(config), config.assets.product);
    expect(root.querySelector('[data-r2p="offer"]')).toBeNull();
    expect(root.querySelector('[data-r2p="price"]')).toBeNull();
    expect(root.querySelector('[data-r2p="coupon"]')).toBeNull();
    expect(() => ui.showCode("R2P-AB12-CD34")).not.toThrow();
  });

  it("maps screen points to the play field", () => {
    const rect = { left: 10, top: 20, width: 180, height: 320 } as DOMRect;
    expect(toLogical(100, 180, rect)).toEqual({ x: 180, y: 320 });
  });
});

describe("score challenge (feature 42)", () => {
  it("reads only plain numbers from the link", () => {
    expect(readChallenge("?beat=7-10-18.4")).toEqual({ score: 7, goal: 10, seconds: 18.4 });
    expect(readChallenge("?beat=11-10-18.4")).toBeNull();
    expect(readChallenge("?beat=7-10-0")).toBeNull();
    expect(readChallenge("?beat=Ali-10-18")).toBeNull();
    expect(readChallenge("?beat=7-10-18.4&name=Ali")).toEqual({ score: 7, goal: 10, seconds: 18.4 });
    expect(readChallenge("")).toBeNull();
  });

  it("builds a link with the score and nothing else", () => {
    const link = challengeLink("https://p.example/g/AbC1234?from=qr&layout=square#x",
      { score: 7, goal: 10, seconds: 18.44 });
    expect(link).toBe("https://p.example/g/AbC1234?layout=square&beat=7-10-18.4&from=share");
    expect(challengeLink("about:blank", { score: 1, goal: 2, seconds: 3 })).toBeNull();
    expect(challengeLink("not a url", { score: 1, goal: 2, seconds: 3 })).toBeNull();
    const c = { score: 7, goal: 10, seconds: 18.4 };
    expect(challengeText("en", "Rose cupcake", c)).toBe(
      "I scored 7 of 10 in 18.4 s in the Rose cupcake game. Can you beat me?",
    );
    expect(challengeIntro("en", c)).toBe("A friend scored 7 of 10 in 18.4 s. Can you beat it?");
    expect(challengeIntro("ur", c)).toContain("18.4");
    expect(challengeText("ur", "کپ کیک", c)).toContain("کپ کیک");
  });

  it("a published page offers the challenge on the end card; a test build does not", () => {
    const beacon = vi.fn(() => true);
    Object.defineProperty(navigator, "sendBeacon", { value: beacon, configurable: true });
    const analytics = { endpoint: "https://api.test/api/events", adId: "ad1", variant: "A" };
    const root = document.createElement("div");
    const config = testConfig({ analytics });
    const ui = buildUi(root, config, createPlatform(config), config.assets.product);
    ui.showEnd({ won: true, seconds: 18.4, score: 10, goal: 10 });
    const share = root.querySelector<HTMLAnchorElement>('[data-r2p="share"]')!;
    expect(share.hidden).toBe(false);
    expect(decodeURIComponent(share.href)).toContain("beat=10-10-18.4&from=share");
    share.click();
    const [, blob] = beacon.mock.calls.at(-1) as unknown as [string, Blob];
    expect(blob).toBeInstanceOf(Blob);

    const offline = document.createElement("div");
    const plain = testConfig();
    buildUi(offline, plain, createPlatform(plain), plain.assets.product).showEnd({
      won: true, seconds: 18, score: 10, goal: 10,
    });
    expect(offline.querySelector<HTMLAnchorElement>('[data-r2p="share"]')!.hidden).toBe(true);
    const meta = testConfig({ platform: "meta" });
    expect(createPlatform(meta).canShare).toBe(false);
  });

  it("a shop that takes sign-ups shows the offers link; nothing else does", () => {
    const tag = document.createElement("meta");
    tag.name = "r2p-optin";
    tag.content = JSON.stringify({ url: "https://wa.me/923001112223?text=JOIN%20K7QDM2" });
    document.head.append(tag);
    const root = document.createElement("div");
    const config = testConfig();
    buildUi(root, config, createPlatform(config), config.assets.product);
    expect(root.querySelector('[data-r2p="optin"]')?.getAttribute("href")).toContain("JOIN");
    expect(createPlatform(testConfig({ platform: "meta" })).optinUrl).toBeNull();
    tag.content = JSON.stringify({ url: "https://evil.example/" });
    expect(createPlatform(config).optinUrl).toBeNull();
    tag.content = "{";
    expect(createPlatform(config).optinUrl).toBeNull();
    tag.remove();
    expect(createPlatform(config).optinUrl).toBeNull();
  });

  it("a friend's challenge shows on the intro card", () => {
    window.history.replaceState(null, "", "/g/AbC1234?beat=7-10-18.4&from=share");
    const analytics = { endpoint: "https://api.test/api/events", adId: "ad1", variant: "A" };
    const root = document.createElement("div");
    const config = testConfig({ analytics });
    buildUi(root, config, createPlatform(config), config.assets.product);
    expect(root.querySelector('[data-r2p="challenge"]')?.textContent).toBe(
      "A friend scored 7 of 10 in 18.4 s. Can you beat it?",
    );
    expect(playSource()).toBe("share");
    window.history.replaceState(null, "", "/");
  });
});

describe("effects", () => {
  it("sparks burst and fade", () => {
    const sparks = new Sparks();
    sparks.burst(createRng(3), 10, 10, ["#ffffff"], 5);
    expect(sparks.count).toBe(5);
    sparks.update(2);
    expect(sparks.count).toBe(0);
  });

  it("every sound has a recipe and stays silent before the first tap", () => {
    for (const name of ["tap", "catch", "miss", "jump", "coin", "swap", "bump", "win", "end"] as const) {
      expect(recipe(name).length).toBeGreaterThan(0);
    }
    const sfx = new Sfx();
    expect(() => sfx.play("win")).not.toThrow();
  });
});

describe("moving product", () => {
  const still = { width: 320, height: 220 } as HTMLImageElement;
  const strip = { width: 600, height: 100 } as HTMLImageElement;

  it("uses the still cut-out without an animation", () => {
    const images: Images = {
      product: still,
      productPhoto: null,
      logo: null,
      productFrames: null,
      more: [],
    };
    expect(productPicture(images, 3)).toEqual({ image: still, sx: 0, sy: 0, sw: 320, sh: 220 });
  });

  it("plays the frames forwards then backwards in game time", () => {
    const images: Images = {
      product: still,
      productPhoto: null,
      logo: null,
      productFrames: { image: strip, frames: 6, fps: 10 },
      more: [],
    };
    const frames = [0, 0.1, 0.25, 0.45, 0.5, 0.6, 0.95, 1.0, 1.05].map(
      (t) => productPicture(images, t).sx / 100,
    );
    expect(frames).toEqual([0, 1, 2, 4, 5, 4, 1, 0, 0]);
    expect(productPicture(images, -1).sx).toBe(0);
    expect(productPicture(images, 0.3)).toMatchObject({ sw: 100, sh: 100, image: strip });
  });
});
