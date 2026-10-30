import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { agencyBrand, chooseBrand, rememberAgency, storedAgency } from "../api";

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

const me = { id: "m1", name: "Sara", role: "owner", you: true };
const agency = (extra: Record<string, unknown> = {}) => ({
  id: "g1",
  name: "Synthetic Agency",
  you: me,
  members: [me, { id: "m2", name: "Hina", role: "viewer", you: false }],
  brands: [{ id: "s1", name: "Synthetic Bakes", games: 2, live: 1, plays: 40, cta_taps: 6 }],
  ...extra,
});

afterEach(() => {
  rememberAgency(null);
  chooseBrand(null);
  vi.restoreAllMocks();
});

describe("agency workspace", () => {
  it("starts a workspace and keeps its key in this browser", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(201, { key: "agency_k1", agency: agency({ brands: [] }) }))
      .mockResolvedValueOnce(jsonResponse(200, agency({ brands: [] })));
    renderAt("/agency");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Agency name"), "Synthetic Agency");
    await user.type(screen.getByLabelText(/Your name, as the team/), "Sara");
    await user.click(screen.getByRole("button", { name: "Start the workspace" }));
    expect(await screen.findByRole("heading", { name: "Synthetic Agency" })).toBeVisible();
    expect(storedAgency()?.key).toBe("agency_k1");
    const [, init] = fetchMock.mock.calls[0]!;
    expect(JSON.parse(String(init?.body))).toEqual({ name: "Synthetic Agency", your_name: "Sara" });
  });

  it("an owner sees brands, invites people, and makes a game for a brand", async () => {
    rememberAgency({ key: "agency_k1", name: "Synthetic Agency" });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(200, agency()))
      .mockResolvedValueOnce(jsonResponse(201, { code: "INV1", role: "editor", expires_at: "x" }));
    renderAt("/agency");
    const card = (await screen.findByRole("heading", { name: "Synthetic Bakes" })).closest("li")!;
    expect(within(card).getByText("Order taps").nextElementSibling).toHaveTextContent("6");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Make an invite link" }));
    expect(await screen.findByText(/agency\?invite=INV1/)).toBeVisible();
    expect(new Headers(fetchMock.mock.calls[1]![1]?.headers).get("X-Agency-Key")).toBe("agency_k1");
    expect(screen.getByLabelText("Role of Hina")).toHaveValue("viewer");

    await user.click(within(card).getByRole("button", { name: "Make a game" }));
    expect(agencyBrand()).toEqual({ shopId: "s1", name: "Synthetic Bakes", agencyKey: "agency_k1" });
    expect(await screen.findByText(/Making a game for/)).toBeVisible();
    expect(screen.getByLabelText("Shop name")).toHaveValue("Synthetic Bakes");
    await user.click(screen.getByRole("button", { name: "Use my own shop" }));
    expect(agencyBrand()).toBeNull();
  });

  it("a brand's game is sent with the agency key, not a shop key", async () => {
    chooseBrand({ shopId: "s1", name: "Synthetic Bakes", agencyKey: "agency_k1" });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(422, { detail: "stop here" }));
    renderAt("/");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("WhatsApp number for orders"), "923001234567");
    await user.upload(screen.getByLabelText(/Video or photos/), new File(["v"], "v.mp4", { type: "video/mp4" }));
    await user.click(screen.getByRole("checkbox", { name: /mine to use for ads/ }));
    await user.click(screen.getByRole("button", { name: "Make my game" }));
    expect(await screen.findByText("stop here")).toBeVisible();
    const [, init] = fetchMock.mock.calls[0]!;
    expect(new Headers(init?.headers).get("X-Agency-Key")).toBe("agency_k1");
    expect(new Headers(init?.headers).get("X-Shop-Key")).toBeNull();
    expect((init!.body as FormData).get("shop_id")).toBe("s1");
  });

  it("a viewer cannot make games or invite", async () => {
    rememberAgency({ key: "agency_v", name: "Synthetic Agency" });
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(200, agency({ you: { id: "m2", name: "Hina", role: "viewer", you: true } })),
    );
    renderAt("/agency");
    expect(await screen.findByRole("heading", { name: "Synthetic Bakes" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Make a game" })).toBeNull();
    expect(screen.queryByText("Invite someone")).toBeNull();
    expect(screen.queryByText("Add a brand")).toBeNull();
  });

  it("forgets a key the server no longer knows", async () => {
    rememberAgency({ key: "agency_old", name: "Gone" });
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(401, { detail: "no" }));
    renderAt("/agency");
    expect(await screen.findByRole("heading", { name: "Agency workspace" })).toBeVisible();
    expect(storedAgency()).toBeNull();
  });
});
