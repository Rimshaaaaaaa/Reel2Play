import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const card = (id: string, name: string) => ({
  id,
  name,
  description: `${name}, a synthetic description.`,
  control: "Tap",
  good_for: ["other"],
  designer: "Reel2Play",
  demo_url: `https://api.test/templates/${id}/demo`,
});

afterEach(() => vi.restoreAllMocks());

describe("template marketplace", () => {
  it("shows every template with its designer and plays a demo in the phone", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(200, [card("catch", "Catch"), card("quiz", "Quiz")]),
    );
    render(
      <MemoryRouter initialEntries={["/templates"]}>
        <App />
      </MemoryRouter>,
    );
    const quiz = (await screen.findByRole("heading", { name: "Quiz" })).closest("li")!;
    expect(within(quiz).getByText("By Reel2Play")).toBeVisible();
    const user = userEvent.setup();
    await user.click(within(quiz).getByRole("button", { name: "Play the demo" }));
    const frame = screen.getByTitle("Quiz demo");
    expect(frame).toHaveAttribute("src", "https://api.test/templates/quiz/demo");
    expect(frame).toHaveAttribute("sandbox", "allow-scripts");
    expect(screen.getByRole("link", { name: "Game templates" })).toHaveAttribute("href", "/templates");
  });

  it("sends a designer's template and shows what code found", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(200, []))
      .mockResolvedValueOnce(
        jsonResponse(201, {
          id: "sub1",
          template_id: "kite",
          status: "checks_failed",
          problems: ["game.ts uses network calls (fetch), which games may not"],
          review_note: null,
          created_at: "2026-10-28T10:00:00Z",
          token: "tok",
        }),
      );
    render(
      <MemoryRouter initialEntries={["/templates"]}>
        <App />
      </MemoryRouter>,
    );
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Your name or studio"), "Synthetic Studio");
    await user.type(screen.getByLabelText(/How we reach you/), "studio@example.com");
    await user.upload(screen.getByLabelText("template.json"), new File(["{}"], "template.json", { type: "application/json" }));
    await user.upload(screen.getByLabelText("game.ts"), new File(["x"], "game.ts", { type: "text/plain" }));
    const send = screen.getByRole("button", { name: "Send the template" });
    expect(send).toBeDisabled();
    await user.click(screen.getByLabelText(/I made this template/));
    await user.click(send);
    expect(await screen.findByText(/Not sent for review/)).toBeVisible();
    expect(screen.getByText(/network calls \(fetch\)/)).toBeVisible();
    const body = fetchMock.mock.calls[1]![1]!.body as FormData;
    expect(body.get("designer_name")).toBe("Synthetic Studio");
    expect(body.get("license_confirmed")).toBe("true");
  });
});
