import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const posts = [
  {
    id: "ig:444",
    source: "instagram",
    account: "@synthetic.shoes",
    caption: "Sneaker drop",
    thumbnail_url: "https://scontent.cdninstagram.com/t/444.jpg",
    created_at: "2026-10-20T09:00:00+0000",
    downloadable: true,
  },
  {
    id: "ig:555",
    source: "instagram",
    account: "@synthetic.shoes",
    caption: "",
    thumbnail_url: null,
    created_at: "2026-10-10T09:00:00+0000",
    downloadable: false,
  },
  {
    id: "fb:111:333",
    source: "facebook",
    account: "Synthetic Shoes",
    caption: "New sneakers",
    thumbnail_url: null,
    created_at: null,
    downloadable: true,
  },
];

const video = {
  id: "v1",
  shop_id: "s1",
  kind: "video",
  status: "failed",
  error: "the video is 300s",
  duration_s: null,
  rights_confirmed: true,
  audio_removed: false,
  is_synthetic: false,
  ad_id: null,
  shop_key: "key-1",
};

type Route = (url: string, init?: RequestInit) => Response;

function serve(routes: Record<string, Route>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const path = new URL(url).pathname;
    const route = routes[path];
    if (!route) throw new Error(`unexpected request ${url}`);
    return route(url, init);
  });
}

function Address() {
  const location = useLocation();
  return <output data-testid="address">{location.pathname + location.hash}</output>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <Address />
    </MemoryRouter>,
  );
}

describe("ImportPage", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
  });

  it("says when this server has no Facebook app", async () => {
    serve({ "/api/import/meta/status": () => jsonResponse(200, { enabled: false }) });
    renderAt("/import");
    expect(await screen.findByText("Importing is not set up here yet")).toBeVisible();
    expect(screen.getByRole("link", { name: "Upload the video file" })).toHaveAttribute("href", "/");
  });

  it("starts the Facebook sign-in, and explains a refused one", async () => {
    serve({ "/api/import/meta/status": () => jsonResponse(200, { enabled: true }) });
    renderAt("/import#error=denied");
    const signIn = await screen.findByRole("link", { name: "Continue with Facebook" });
    expect(signIn.getAttribute("href")).toMatch(/\/api\/import\/meta\/start$/);
    expect(screen.getByRole("alert")).toHaveTextContent("Facebook access was not allowed");
    expect(screen.getByTestId("address")).toHaveTextContent(/^\/import$/);
  });

  it("is reachable from the upload page", async () => {
    serve({ "/api/import/meta/status": () => jsonResponse(200, { enabled: true }) });
    const user = userEvent.setup();
    renderAt("/");
    await user.click(screen.getByRole("link", { name: "Import a post" }));
    expect(await screen.findByRole("heading", { name: "Import a post" })).toBeVisible();
  });

  it("lists the owner's videos and imports the chosen one", async () => {
    const fetchMock = serve({
      "/api/import/meta/posts": () => jsonResponse(200, posts),
      "/api/import/meta/use": () => jsonResponse(201, video),
      "/api/videos/v1": () => jsonResponse(200, video),
    });
    const user = userEvent.setup();
    renderAt("/import#session=abc");

    const list = await screen.findByRole("list", { name: "Your videos" });
    expect(screen.getByTestId("address")).toHaveTextContent(/^\/import$/);
    expect(window.sessionStorage.getItem("r2p.import")).toBe("abc");
    const cards = within(list).getAllByRole("listitem");
    expect(cards).toHaveLength(3);
    expect(within(cards[0]!).getByText("Sneaker drop")).toBeVisible();
    expect(within(cards[1]!).getByText(/Instagram keeps this file/)).toBeVisible();
    expect(within(cards[2]!).getByText("Facebook Page")).toBeVisible();

    await user.click(within(cards[0]!).getByRole("button", { name: "Use this video" }));
    expect(within(cards[0]!).getByRole("button", { name: "Chosen" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await user.type(screen.getByLabelText("Shop name"), "Synthetic Shoes");
    const make = screen.getByRole("button", { name: "Make my game" });
    expect(make).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(make);
    expect(screen.getByRole("alert")).toHaveTextContent("WhatsApp number or a shop link");

    await user.type(screen.getByLabelText("WhatsApp number for orders"), "923001234567");
    await user.click(screen.getByRole("button", { name: "Make my game" }));
    expect(await screen.findByText("the video is 300s", {}, { timeout: 3000 })).toBeVisible();

    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/use"))!;
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers["X-Import-Session"]).toBe("abc");
    expect(headers["X-Shop-Key"]).toBeUndefined();
    expect(JSON.parse(String((init as RequestInit).body))).toMatchObject({
      post_id: "ig:444",
      shop_name: "Synthetic Shoes",
      whatsapp_number: "923001234567",
      shop_url: null,
      rights_confirmed: true,
    });
    expect(JSON.parse(window.localStorage.getItem("r2p.shop") ?? "{}")).toMatchObject({
      id: "s1",
      key: "key-1",
    });

    await user.click(screen.getByRole("button", { name: "Pick another post" }));
    expect(screen.getByRole("list", { name: "Your videos" })).toBeVisible();
  });

  it("asks to sign in again when the session has ended", async () => {
    window.sessionStorage.setItem("r2p.import", "old");
    serve({
      "/api/import/meta/posts": () =>
        jsonResponse(401, { detail: "Your Facebook sign-in has ended. Sign in again." }),
      "/api/import/meta/status": () => jsonResponse(200, { enabled: true }),
    });
    renderAt("/import");
    expect(await screen.findByRole("alert")).toHaveTextContent("Sign in again.");
    expect(await screen.findByRole("link", { name: "Continue with Facebook" })).toBeVisible();
    expect(window.sessionStorage.getItem("r2p.import")).toBeNull();
  });

  it("points to the upload when no videos are found", async () => {
    serve({ "/api/import/meta/posts": () => jsonResponse(200, []) });
    renderAt("/import#session=abc");
    expect(await screen.findByText("No videos found")).toBeVisible();
  });
});
