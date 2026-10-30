import { expect, test } from "@playwright/test";
import path from "node:path";

const SAMPLE = path.resolve(import.meta.dirname, "../../fixtures/synthetic/synthetic-test-pattern.mp4");

test("a shop uploads a Reel and gets a tested, published game", async ({ page, context }) => {
  test.setTimeout(360_000);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your Reel, as a 20-second game" })).toBeVisible();
  await page.getByLabel("Shop name").fill("Synthetic Test Shop");
  await page.getByLabel("WhatsApp number for orders").fill("923001234567");
  await page.getByLabel(/^Price/).fill("Rs 1,999");
  await page.getByLabel(/Video or photos/).setInputFiles(SAMPLE);
  const submit = page.getByRole("button", { name: "Make my game" });
  await expect(submit).toBeDisabled();
  await page.getByRole("checkbox", { name: /mine to use for ads/ }).check();
  await submit.click();
  await expect(page.getByRole("heading", { name: "What the director found" })).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.getByText("Rs 1,999")).toBeVisible();
  const game = page.frameLocator('iframe[title="Your game"]');
  await expect(game.locator('[data-r2p="play"]')).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText("Built with Muse Spark Open")).toBeVisible();
  // The play-tester plays it three times on a phone and checks a tablet before reporting.
  await expect(page.getByRole("heading", { name: "Tested and ready" })).toBeVisible({
    timeout: 180_000,
  });
  await expect(page.getByText("Shows your offer and price")).toBeVisible();
  await expect(page.getByRole("link", { name: "See what the tester saw" })).toBeVisible();

  // Published: the short link, the gameplay Reel and the captions.
  await expect(page.getByRole("heading", { name: "Your game is live" })).toBeVisible({
    timeout: 240_000,
  });
  await expect(page.getByLabel("Gameplay Reel")).toBeVisible();
  await expect(page.locator("#caption-panel")).toContainText("/g/");
  // The share card's own button comes first; the other shapes have theirs further down.
  const link = await page.getByRole("link", { name: "Open game" }).first().getAttribute("href");
  expect(link).toMatch(/\/g\/[A-Za-z0-9]{7}$/);

  // The hosted game page plays on its own, with the offer on the end card.
  const hosted = await context.newPage();
  await hosted.goto(link!);
  await expect(hosted.locator('[data-r2p="play"]')).toBeVisible();
  await hosted.locator('[data-r2p="play"]').click();
  await hosted.evaluate(() => {
    const game = globalThis as unknown as { __r2p: { advance(seconds: number): void } };
    game.__r2p.advance(31);
  });
  await expect(hosted.locator('[data-r2p="offer"]')).toBeVisible();
  await expect(hosted.locator('[data-r2p="cta"]')).toHaveAttribute("href", /^https:\/\/wa\.me\//);

  // Feature 36 and 37: the counter poster and the website embed come with every game.
  await expect(page.getByRole("link", { name: "Download poster (PDF)" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy code" })).toBeVisible();

  // The why panel reads the audit trail, and the studio keeps this browser's games.
  await page.getByText("Why the agents decided this").click();
  await expect(page.getByText(/Audit trail intact/)).toBeVisible();
  await page.getByRole("link", { name: "Studio" }).click();
  await expect(page.getByRole("heading", { name: "Synthetic Test Shop" })).toBeVisible();
  await expect(page.getByText("Live", { exact: true }).last()).toBeVisible();
});

test("a judge tries a sample and watches the safety check stop it", async ({ page }) => {
  await page.goto("/try");
  const card = page.locator("li", { has: page.getByRole("heading", { name: "A product we never advertise" }) });
  await expect(card.getByText("Synthetic sample")).toBeVisible();
  await card.getByRole("button", { name: /Make a game from/ }).click();
  await expect(page).toHaveURL(/\/ads\//, { timeout: 30_000 });
  await expect(page.getByText(/We cannot make game ads for alcohol/).first()).toBeVisible({
    timeout: 45_000,
  });
  await expect(page.getByText("Synthetic sample")).toBeVisible();
});

test("a rejected upload explains why", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Shop name").fill("Synthetic Test Shop");
  await page.getByLabel("WhatsApp number for orders").fill("123");
  await page.getByLabel(/Video or photos/).setInputFiles(SAMPLE);
  await page.getByRole("checkbox", { name: /mine to use for ads/ }).check();
  await page.getByRole("button", { name: "Make my game" }).click();
  await expect(page.getByRole("alert")).toContainText("10 to 15 digits");
});

test("the import page says when no Facebook app is connected", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Import a post" }).click();
  await expect(page.getByRole("heading", { name: "Import a post" })).toBeVisible();
  await expect(page.getByText("Importing is not set up here yet")).toBeVisible();
  await page.getByRole("link", { name: "Upload the video file" }).click();
  await expect(page.getByRole("heading", { name: "Your Reel, as a 20-second game" })).toBeVisible();
});
