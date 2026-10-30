import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AdOut, ReportOut, ShareOut } from "../api";
import { AbTest } from "./AbTest";
import { ShareCard } from "./ShareCard";
import { TestReport } from "./TestReport";

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
  square_link: "https://r2p.test/g/abc1234?layout=square",
  landscape_link: "https://r2p.test/g/abc1234?layout=landscape",
  square_reel_url: "https://media.test/reel-square.mp4",
  wide_reel_url: "https://media.test/reel-wide.mp4",
};

const ad = { id: "a1", shop_id: "s1", variant: "A", share } as unknown as AdOut;

const version = (variant: string, status: string, plays = 0) => ({
  id: `id-${variant}`,
  variant,
  status,
  template: variant === "A" ? "catch" : "memory",
  link: `https://r2p.test/g/${variant}`,
  stats: { plays, completion: plays ? 0.8 : null, cta_rate: plays ? 0.2 : null },
});

describe("other shapes", () => {
  it("offers the square and landscape game and Reels", () => {
    render(<ShareCard share={share} />);
    expect(screen.getByText("Other shapes")).toBeVisible();
    const reels = screen.getAllByRole("link", { name: "Download Reel" });
    expect(reels.map((a) => a.getAttribute("href"))).toEqual([
      "https://media.test/reel-square.mp4",
      "https://media.test/reel-wide.mp4",
    ]);
  });
});

describe("A/B test", () => {
  beforeEach(() => window.localStorage.clear());

  it("lets the shop that made the game start a test", async () => {
    window.localStorage.setItem("r2p.shop", JSON.stringify({ id: "s1", key: "k1", name: "S" }));
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse(200, { link: null, versions: [version("A", "published")], leader: null, verdict: "x" }),
      )
      .mockResolvedValueOnce(
        jsonResponse(201, {
          link: "https://r2p.test/v/xyz9876",
          versions: [version("A", "published", 30), version("B", "published", 30), version("C", "published", 30)],
          leader: "B",
          verdict: "Version B gets the most order taps per finished game.",
        }),
      );
    const user = userEvent.setup();
    render(<AbTest ad={ad} />);
    await user.click(await screen.findByRole("button", { name: "Make two more versions" }));
    expect(await screen.findByText("Version B gets the most order taps per finished game.")).toBeVisible();
    const [, init] = fetchMock.mock.calls[1]!;
    expect((init as RequestInit).headers).toEqual({ "X-Shop-Key": "k1" });
    expect(screen.getByText("r2p.test/v/xyz9876")).toBeVisible();
    expect(screen.getAllByText("Memory match")).toHaveLength(2);
  });

  it("asks other browsers to open it where the game was made", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(200, { link: null, versions: [version("A", "published")], leader: null, verdict: "x" }),
    );
    render(<AbTest ad={ad} />);
    expect(await screen.findByText(/browser that made the game/)).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("report warnings", () => {
  it("lists what the shop should look at", () => {
    const report: ReportOut = {
      passed: true,
      language: "en",
      rounds: 0,
      summary: "All good.",
      next_step: "Share it.",
      gates: [],
      screenshots: {},
      warnings: ["No price is shown. Shoppers often ask the price first; add it next time."],
    };
    render(<TestReport report={report} />);
    expect(screen.getByText("Worth checking")).toBeVisible();
    expect(screen.getByText(/No price is shown/)).toBeVisible();
  });
});
