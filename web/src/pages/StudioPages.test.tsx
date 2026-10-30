import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { rememberShop, storedShop, uploadVideo } from "../api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

const stats = {
  plays: 12,
  finishes: 9,
  wins: 6,
  cta_taps: 3,
  median_seconds: 18.4,
  completion: 0.75,
  cta_rate: 0.333,
};

const video = {
  id: "v1",
  shop_id: "s1",
  kind: "video",
  status: "uploaded",
  error: null,
  duration_s: null,
  rights_confirmed: true,
  audio_removed: false,
  is_synthetic: true,
  ad_id: null,
};

afterEach(() => rememberShop(null));

describe("studio", () => {
  it("explains itself to a browser that has made nothing yet", () => {
    renderAt("/studio");
    expect(screen.getByText(/has not made a game yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Studio" })).toHaveClass("active");
  });

  it("shows the shop's games, numbers and brand kit", async () => {
    rememberShop({ id: "s1", key: "k1", name: "Ali Shoes" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(200, {
        id: "s1",
        name: "Ali Shoes",
        language: "en",
        brand_kit: { palette: ["#c8243a", "#1c1a36"], tone: "friendly", logo_url: null },
        ads: [
          {
            id: "a1",
            status: "published",
            template: "catch",
            product: "Canvas sneaker",
            created_at: "2026-10-28T10:00:00Z",
            published_at: "2026-10-28T10:03:00Z",
            link: "https://r2p.example/g/AbC1234",
            preview_url: "https://media.test/preview.jpg",
            stats,
            cost: { calls: 5, usd: 0.02, pkr: 5.6 },
          },
        ],
        totals: { ads: 1, published: 1, plays: 12, cta_taps: 3, pkr: 5.6 },
        memory: ["catch: 1 game, 40 plays, 80% finished, 25% of finishers tapped order, the best so far"],
      }),
    ).mockResolvedValueOnce(
      jsonResponse(200, { issued: 4, redeemed: 1, by_ad: [], recent: [] }),
    );
    renderAt("/studio");
    expect(await screen.findByRole("heading", { name: "Ali Shoes" })).toBeInTheDocument();
    expect(await screen.findByText(/given,/)).toHaveTextContent("4 given, 1 used");
    const memory = screen.getByRole("region", { name: "What works for your shop" });
    expect(within(memory).getByText("Catch")).toBeVisible();
    expect(within(memory).getByText(/80% finished, 25% of finishers tapped order$/)).toBeVisible();
    const [, init] = fetchMock.mock.calls[0]!;
    expect(new Headers(init?.headers).get("X-Shop-Key")).toBe("k1");
    expect(screen.getByText("Order taps").nextElementSibling).toHaveTextContent("3");
    expect(screen.getByRole("link", { name: "Canvas sneaker" })).toHaveAttribute("href", "/ads/a1");
    expect(screen.getByText("Live", { selector: ".status-chip" })).toHaveAttribute(
      "data-status",
      "published",
    );
    expect(screen.getByText(/12 plays, 75% finished, 3 order taps, Rs 5.6/)).toBeInTheDocument();
    expect(screen.getByTitle("#c8243a")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Forget this browser" }));
    expect(storedShop()).toBeNull();
    expect(screen.getByText(/has not made a game yet/)).toBeInTheDocument();
  });

  it("forgets a key the server no longer knows", async () => {
    rememberShop({ id: "s1", key: "old", name: "Ali Shoes" });
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(401, { detail: "no" }));
    renderAt("/studio");
    expect(await screen.findByText(/has not made a game yet/)).toBeInTheDocument();
    expect(storedShop()).toBeNull();
  });
});

describe("studio keys on upload", () => {
  const fields = {
    shopName: "Ali Shoes",
    whatsappNumber: "923001234567",
    shopUrl: "",
    price: "",
    offer: "",
    language: "auto" as const,
    rightsConfirmed: true,
    files: [new File(["x"], "a.mp4", { type: "video/mp4" })],
    voiceNote: null,
  };

  it("keeps the key from the first upload and sends it with the next", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(201, { ...video, shop_key: "secret-key" }))
      .mockResolvedValueOnce(jsonResponse(201, { ...video, shop_key: null }));
    await uploadVideo(fields);
    expect(storedShop()).toEqual({ id: "s1", key: "secret-key", name: "Ali Shoes" });
    await uploadVideo(fields);
    const [, second] = fetchMock.mock.calls[1]!;
    expect(new Headers(second?.headers).get("X-Shop-Key")).toBe("secret-key");
    expect((second!.body as FormData).get("shop_id")).toBe("s1");
  });

  it("starts a new shop when the stored one is refused", async () => {
    rememberShop({ id: "gone", key: "old", name: "Old" });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(403, { detail: "not linked" }))
      .mockResolvedValueOnce(jsonResponse(201, { ...video, shop_key: "new-key" }));
    await uploadVideo(fields);
    const [, retry] = fetchMock.mock.calls[1]!;
    expect((retry!.body as FormData).get("shop_id")).toBeNull();
    expect(storedShop()?.key).toBe("new-key");
  });
});

describe("try it", () => {
  it("lists labelled samples and opens the ad page once the game starts", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse(200, [
          {
            key: "sneaker",
            title: "Canvas sneaker",
            about: "A shoe shop's Reel.",
            language: "en",
            synthetic: true,
            source: "Drawn with ffmpeg",
            video_url: "https://api.test/api/samples/sneaker/video",
          },
        ]),
      )
      .mockResolvedValueOnce(jsonResponse(201, video))
      .mockResolvedValueOnce(jsonResponse(200, { ...video, ad_id: "a9" }))
      .mockResolvedValue(jsonResponse(404, { detail: "ad not found" }));
    renderAt("/try");
    const card = (await screen.findByRole("heading", { name: "Canvas sneaker" })).closest("li")!;
    expect(within(card).getByText("Synthetic sample")).toHaveAttribute("title", "Drawn with ffmpeg");
    const user = userEvent.setup();
    await user.click(within(card).getByRole("button", { name: "Make a game from Canvas sneaker" }));
    expect(await screen.findByRole("heading", { name: "Game not found" }, { timeout: 3000 })).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[1]!;
    expect(String(url)).toMatch(/\/api\/try$/);
    expect(init?.body).toBe(JSON.stringify({ sample: "sneaker" }));
  });

  it("says when too many games are being made", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse(200, [
          {
            key: "cake",
            title: "Cake",
            about: "A bakery.",
            language: "en",
            synthetic: true,
            source: "ffmpeg",
            video_url: "https://api.test/v",
          },
        ]),
      )
      .mockResolvedValueOnce(jsonResponse(429, { detail: "A few games are being made right now." }));
    renderAt("/try");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Make a game from Cake" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A few games are being made");
    expect(screen.getByRole("button", { name: "Make a game from Cake" })).toBeEnabled();
  });
});

describe("gallery and comparison", () => {
  it("shows an empty gallery with a way forward", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(200, []));
    renderAt("/gallery");
    expect(await screen.findByText(/fills up as the evaluation runs/)).toBeInTheDocument();
  });

  it("lists playable games", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(200, [
        {
          id: "a1",
          product: "Strawberry cake",
          category: "bakery_food",
          language: "en",
          template: "catch",
          link: "https://r2p.example/g/Cake123",
          preview_url: "https://media.test/p.jpg",
          published_at: null,
          stats,
        },
      ]),
    );
    renderAt("/gallery");
    expect(await screen.findByRole("link", { name: "Strawberry cake" })).toHaveAttribute(
      "href",
      "https://r2p.example/g/Cake123",
    );
    expect(screen.getByText(/bakery food, catch, 12 plays, 75% finished/)).toBeInTheDocument();
  });

  it("shows two unlabelled ads and keeps only the pick", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse(200, {
          ad_id: "a1",
          game_url: "https://r2p.example/g/AbC1234",
          still: {
            image_url: "https://media.test/frame.jpg",
            product: "Canvas sneaker",
            offer: "20% off",
            price: "Rs 2,499",
            language: "en",
          },
          game_side: "right",
        }),
      )
      .mockResolvedValueOnce(jsonResponse(204, null));
    renderAt("/compare");
    const first = await screen.findByRole("region", { name: "Ad 1" });
    expect(within(first).getByText("Canvas sneaker")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Ad 2" })).getByTitle("Ad 2")).toHaveAttribute(
      "src",
      "https://r2p.example/g/AbC1234",
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Ad 2" }));
    expect(await screen.findByRole("heading", { name: "Thank you" })).toBeInTheDocument();
    const [, init] = fetchMock.mock.calls[1]!;
    expect(JSON.parse(String(init?.body))).toEqual({ ad_id: "a1", choice: "game", game_side: "right" });
  });
});
