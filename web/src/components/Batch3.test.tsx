import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AdOut, ShareOut } from "../api";
import { Coupons } from "./Coupons";
import { EasierNote, EasierVersion } from "./EasierVersion";
import { Leads } from "./Leads";
import { ShareCard } from "./ShareCard";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const share: ShareOut = {
  link: "https://r2p.test/g/abc1234",
  preview_url: null,
  reel_url: null,
  reel_seconds: null,
  lead_in_url: null,
  meta_html_url: null,
  meta_zip_url: null,
  captions: null,
  published_at: null,
  poster_url: "https://media.test/poster.pdf?sig=x",
  poster_preview_url: "https://media.test/poster.jpg?sig=x",
  embeds: [
    { shape: "tall", src: "https://r2p.test/g/abc1234?from=embed", code: '<iframe src="tall"></iframe>' },
    {
      shape: "wide",
      src: "https://r2p.test/g/abc1234?layout=landscape&from=embed",
      code: '<iframe src="wide"></iframe>',
    },
  ],
};

afterEach(() => vi.restoreAllMocks());

describe("counter poster and website embed", () => {
  it("offers the A4 poster and both embed shapes", async () => {
    render(<ShareCard share={share} />);
    expect(screen.getByRole("heading", { name: "Counter poster" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Download poster (PDF)" })).toHaveAttribute(
      "href",
      share.poster_url,
    );
    expect(screen.getByAltText(/The counter poster/)).toHaveAttribute("src", share.poster_preview_url);

    expect(screen.getByText('<iframe src="tall"></iframe>')).toBeVisible();
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Wide" }));
    expect(screen.getByRole("tab", { name: "Wide" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(/full-width section/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Copy code" }));
    expect(await navigator.clipboard.readText()).toBe('<iframe src="wide"></iframe>');
    expect(screen.getByRole("button", { name: "Copied" })).toBeVisible();
  });

  it("shows neither when the ad has no poster or embeds", () => {
    render(<ShareCard share={{ ...share, poster_url: null, embeds: [] }} />);
    expect(screen.queryByText("Counter poster")).toBeNull();
    expect(screen.queryByText("Put it on your website")).toBeNull();
  });
});

describe("win codes", () => {
  it("lets the shop use a customer's code once", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(200, { issued: 3, redeemed: 0, by_ad: [], recent: [] }))
      .mockResolvedValueOnce(
        jsonResponse(200, {
          result: "redeemed",
          code: "R2P-K7QD-M2XP",
          message: "Done: R2P-K7QD-M2XP is marked as used.",
          product: "Rose cupcake",
          ad_id: "a1",
          issued_at: null,
          redeemed_at: null,
        }),
      )
      .mockResolvedValueOnce(jsonResponse(200, { issued: 3, redeemed: 1, by_ad: [], recent: [] }))
      .mockResolvedValueOnce(jsonResponse(401, { detail: "This browser is not linked to a shop." }));
    render(<Coupons shopKey="k1" />);
    expect(await screen.findByText(/given,/)).toHaveTextContent("3 given, 0 used");
    const user = userEvent.setup();
    const field = screen.getByLabelText("Customer's code");
    expect(screen.getByRole("button", { name: "Use code" })).toBeDisabled();
    await user.type(field, "r2p k7qd m2xp");
    await user.click(screen.getByRole("button", { name: "Use code" }));
    const answer = await screen.findByRole("status");
    expect(answer).toHaveTextContent("marked as used");
    expect(answer).toHaveAttribute("data-tone", "good");
    expect(await screen.findByText(/given,/)).toHaveTextContent("3 given, 1 used");
    const [url, init] = fetchMock.mock.calls[1]!;
    expect(String(url)).toMatch(/\/api\/shop\/coupons\/redeem$/);
    expect(new Headers(init?.headers).get("X-Shop-Key")).toBe("k1");
    expect(JSON.parse(String(init?.body))).toEqual({ code: "r2p k7qd m2xp" });

    await user.type(field, "R2P-AAAA-BBBB");
    await user.click(screen.getByRole("button", { name: "Use code" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not linked to a shop");
  });
});

describe("easier version", () => {
  const ad = { id: "a1", shop_id: "s1", status: "published", easier_for: null } as unknown as AdOut;
  const hard = {
    hard: true,
    reason: "only 7% of 30 plays reached the end",
    stats: { plays: 30, finishes: 2, wins: 0, completion: 0.067 },
  };

  it("lets the shop play the easier version and choose it", async () => {
    window.localStorage.setItem("r2p.shop", JSON.stringify({ id: "s1", key: "k1", name: "S" }));
    const ready = {
      ...hard,
      version: {
        id: "e1",
        status: "ready",
        state: "ready",
        change: "goal 10 to 8",
        play_url: "https://media.test/e1.html?sig=x",
      },
    };
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(200, ready))
      .mockResolvedValueOnce(
        jsonResponse(202, { ...ready, version: { ...ready.version, state: "using", play_url: null } }),
      );
    render(
      <MemoryRouter>
        <EasierVersion ad={ad} />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: "Players find this game hard" })).toBeVisible();
    expect(screen.getByText(/only 7% of 30 plays reached the end/)).toBeVisible();
    expect(screen.getByRole("img", { name: "Reach the end: 7%" })).toBeInTheDocument();
    expect(screen.getByText(/goal 10 to 8/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Play the easier version" })).toHaveAttribute(
      "href",
      "https://media.test/e1.html?sig=x",
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Use the easier version" }));
    expect(await screen.findByText(/Publishing the easier version/)).toBeVisible();
    const [url, init] = fetchMock.mock.calls[1]!;
    expect(String(url)).toMatch(/\/api\/ads\/a1\/easier\/use$/);
    expect(new Headers(init?.headers).get("X-Shop-Key")).toBe("k1");
    window.localStorage.clear();
  });

  it("stays quiet while players are doing fine, and only the shop can choose", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(200, { hard: false, reason: null, stats: {}, version: null }),
    );
    const { container } = render(
      <MemoryRouter>
        <EasierVersion ad={ad} />
      </MemoryRouter>,
    );
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(container).toBeEmptyDOMElement();

    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(200, {
        ...hard,
        version: { id: "e1", status: "ready", state: "ready", change: null, play_url: null },
      }),
    );
    render(
      <MemoryRouter>
        <EasierVersion ad={{ ...ad, id: "a2" }} />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/in the browser that made the game/)).toBeVisible();
  });

  it("an easier version links back to the game it replaces", () => {
    render(
      <MemoryRouter>
        <EasierNote ad={{ ...ad, easier_for: "a0" } as AdOut} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "this game" })).toHaveAttribute("href", "/ads/a0");
  });
});

describe("offers on WhatsApp", () => {
  it("lets the shop turn sign-ups on and download who agreed", async () => {
    const off = { available: true, enabled: false, code: null, join_link: null, agreed: 0 };
    const on = { ...off, enabled: true, code: "K7QDM2", join_link: "https://wa.me/9230?text=JOIN", agreed: 2 };
    URL.createObjectURL = vi.fn(() => "blob:list");
    URL.revokeObjectURL = vi.fn();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(200, off))
      .mockResolvedValueOnce(jsonResponse(200, on))
      .mockResolvedValueOnce(new Response("whatsapp_number\n+923339998877\n", { status: 200 }));
    render(<Leads shopKey="k1" />);
    const toggle = await screen.findByRole("switch");
    expect(toggle).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Download the list" })).toBeDisabled();
    const user = userEvent.setup();
    await user.click(toggle);
    expect(await screen.findByText("2")).toBeVisible();
    expect(screen.getByRole("switch")).toBeChecked();
    const [, init] = fetchMock.mock.calls[1]!;
    expect(JSON.parse(String(init?.body))).toEqual({ enabled: true });
    await user.click(screen.getByRole("button", { name: "Download the list" }));
    const [url, download] = fetchMock.mock.calls[2]!;
    expect(String(url)).toMatch(/\/api\/shop\/leads\.csv$/);
    expect(new Headers(download?.headers).get("X-Shop-Key")).toBe("k1");
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

  it("says when the server has no WhatsApp yet", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(200, { available: false, enabled: false, code: null, join_link: null, agreed: 0 }),
    );
    render(<Leads shopKey="k1" />);
    expect(await screen.findByText(/needs WhatsApp to be set up/)).toBeVisible();
    expect(screen.getByRole("switch")).toBeDisabled();
  });
});
