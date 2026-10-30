import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { rememberShop, storedShop } from "../api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

const item = (n: number, extra: Record<string, unknown> = {}) => ({
  video_id: `v${n}`,
  name: n === 1 ? "Rose cupcake" : null,
  price: n === 1 ? "Rs 450" : null,
  video_status: "uploaded",
  ad_id: null,
  status: null,
  template: null,
  link: null,
  preview_url: null,
  ...extra,
});

afterEach(() => {
  rememberShop(null);
  vi.restoreAllMocks();
});

describe("batch mode", () => {
  it("sends one file per product with its own name and price, then shows the set", async () => {
    URL.createObjectURL = vi.fn(() => "blob:preview");
    URL.revokeObjectURL = vi.fn();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse(201, {
          id: "b1",
          shop_id: "s1",
          created_at: "2026-10-28T10:00:00Z",
          items: [item(1), item(2)],
          published: 0,
          finished: 0,
          shop_key: "k-new",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse(200, {
          id: "b1",
          shop_id: "s1",
          created_at: "2026-10-28T10:00:00Z",
          items: [
            item(1, {
              ad_id: "a1",
              status: "published",
              template: "catch",
              link: "https://r2p.test/g/AbC1234",
            }),
            item(2, { ad_id: "a2", status: "testing", name: "Chocolate tart" }),
          ],
          published: 1,
          finished: 1,
          shop_key: null,
        }),
      );
    renderAt("/batch");
    const user = userEvent.setup();
    expect(screen.getByRole("heading", { name: "Games for several products" })).toBeVisible();
    await user.type(screen.getByLabelText("Shop name"), "Synthetic Bakes");
    await user.type(screen.getByLabelText("WhatsApp number for orders"), "923001234567");
    expect(screen.queryByLabelText("Price")).toBeNull(); // each product has its own
    const picker = screen.getByLabelText("Products");
    await user.upload(picker, [
      new File(["a"], "cupcake.jpg", { type: "image/jpeg" }),
      new File(["b"], "tart.mp4", { type: "video/mp4" }),
    ]);
    expect(screen.getByText("2 of 12 products")).toBeVisible();
    await user.type(screen.getByLabelText("Product 1 name"), "Rose cupcake");
    await user.type(screen.getByLabelText("Product 1 price"), "Rs 450");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Make 2 games" }));

    expect(await screen.findByRole("heading", { name: "Your set of 2 games" })).toBeVisible();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toMatch(/\/api\/batches$/);
    const form = init?.body as FormData;
    expect(form.getAll("files")).toHaveLength(2);
    expect(JSON.parse(String(form.get("items")))).toEqual([
      { name: "Rose cupcake", price: "Rs 450", offer: null },
      { name: null, price: null, offer: null },
    ]);
    expect(storedShop()?.key).toBe("k-new");

    expect(await screen.findByText(/1 of 2 live/)).toBeVisible();
    const cards = screen.getAllByRole("listitem");
    expect(within(cards[0]!).getByRole("link", { name: "Open game" })).toHaveAttribute(
      "href",
      "https://r2p.test/g/AbC1234",
    );
    expect(within(cards[0]!).getByText("Catch")).toBeVisible();
    expect(within(cards[1]!).getByText("Testing")).toBeVisible();
    expect(within(cards[1]!).getByRole("link", { name: "See progress" })).toHaveAttribute(
      "href",
      "/ads/a2",
    );
  });

  it("needs two products and lets one be removed", async () => {
    URL.createObjectURL = vi.fn(() => "blob:preview");
    URL.revokeObjectURL = vi.fn();
    renderAt("/batch");
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Products"), [
      new File(["a"], "a.jpg", { type: "image/jpeg" }),
      new File(["b"], "b.jpg", { type: "image/jpeg" }),
    ]);
    await user.click(screen.getByRole("button", { name: "Remove product 2" }));
    expect(screen.getByText("1 of 12 products")).toBeVisible();
    await user.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: "Make the games" })).toBeDisabled();
  });

  it("says when a batch does not exist", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(404, { detail: "batch not found" }));
    renderAt("/batches/nope");
    expect(await screen.findByRole("heading", { name: "Batch not found" })).toBeVisible();
  });
});
