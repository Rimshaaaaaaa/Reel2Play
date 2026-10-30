import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const ad = {
  id: "a1",
  video_id: "v1",
  status: "cutting_out",
  step: "cutout",
  error: null,
  is_synthetic: false,
  brief: {
    product: "Canvas sneaker",
    category: "shoes",
    palette: ["#c8243a", "#ffffff"],
    language: "en",
    price: "Rs 2,499",
    offer_text: "20% off this week",
    offer_source: "caption",
  },
  sprites: [{ url: "https://media.test/sprite.png", method: "grabcut", quality: "lower" }],
  template: null,
  build_url: null,
  report: null,
  share: null,
  progress: [
    { at: "2026-10-28T10:00:00Z", actor: "system", action: "ad.created", message: "Video received." },
    { at: "2026-10-28T10:00:01Z", actor: "director", action: "analysis.done", message: "Found Canvas sneaker." },
    { at: "2026-10-28T10:00:02Z", actor: "system", action: "pipeline.stopped", message: "All steps built so far are done." },
  ],
};

const gates = [
  { gate: "loads_fast", label: "Opens quickly", passed: true, message: "First frame in 300 ms.", screenshot_url: null },
  { gate: "offer_shown", label: "Shows your offer and price", passed: true, message: "Offer and price are on the end card.", screenshot_url: "https://media.test/end.png" },
];

const report = {
  passed: true,
  language: "en",
  rounds: 0,
  summary: "We played your game three times on a small phone and on a tablet.",
  next_step: "Share the game link with your customers on WhatsApp.",
  gates,
  screenshots: { "phone-played-end": "https://media.test/end.png" },
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
  is_synthetic: false,
  ad_id: null,
};

function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

async function fillForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Shop name"), "Ali Shoes");
  await user.type(screen.getByLabelText("WhatsApp number for orders"), "923001234567");
  await user.type(screen.getByLabelText(/^Price/), "Rs 2,499");
  const file = new File(["fake"], "reel.mp4", { type: "video/mp4" });
  await user.upload(screen.getByLabelText(/Video or photos/), file);
}

describe("UploadPage", () => {
  it("shows the attribution and the shop sign", async () => {
    const user = userEvent.setup();
    renderApp();
    expect(screen.getByText("Built with Muse Spark Open")).toBeInTheDocument();
    expect(screen.getByText("Your shop")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Shop name"), "Ali Shoes");
    expect(screen.getAllByText("Ali Shoes").length).toBeGreaterThan(0);
  });

  it("needs the rights confirmation before sending", async () => {
    const user = userEvent.setup();
    renderApp();
    await fillForm(user);
    const button = screen.getByRole("button", { name: "Make my game" });
    expect(button).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /mine to use for ads/ }));
    expect(button).toBeEnabled();
  });

  it("asks for an order contact", async () => {
    const user = userEvent.setup();
    renderApp();
    await user.type(screen.getByLabelText("Shop name"), "Ali Shoes");
    await user.upload(
      screen.getByLabelText(/Video or photos/),
      new File(["x"], "a.jpg", { type: "image/jpeg" }),
    );
    await user.click(screen.getByRole("checkbox", { name: /mine to use for ads/ }));
    await user.click(screen.getByRole("button", { name: "Make my game" }));
    expect(screen.getByRole("alert")).toHaveTextContent("WhatsApp number or a shop link");
  });

  it("uploads, then follows the agents until they stop", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(201, video))
      .mockResolvedValueOnce(jsonResponse(200, { ...video, status: "ready", ad_id: "a1" }))
      .mockResolvedValueOnce(jsonResponse(200, ad));
    const user = userEvent.setup();
    renderApp();
    await fillForm(user);
    await user.click(screen.getByRole("checkbox", { name: /mine to use for ads/ }));
    await user.click(screen.getByRole("button", { name: "Make my game" }));
    expect(await screen.findByText("Preparing your video")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toMatch(/\/api\/uploads$/);
    const form = (init as RequestInit).body as FormData;
    expect(form.get("shop_name")).toBe("Ali Shoes");
    expect(form.get("price")).toBe("Rs 2,499");
    expect(form.get("rights_confirmed")).toBe("true");
    expect(
      await screen.findByText("What the director found", {}, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(screen.getByText("Found Canvas sneaker.")).toBeInTheDocument();
    expect(screen.getByText("Done so far")).toBeInTheDocument();
    expect(screen.getByText("(read from the video's text)")).toBeInTheDocument();
    expect(screen.getByAltText("Your product, cut out")).toHaveAttribute(
      "src",
      "https://media.test/sprite.png",
    );
    expect(screen.getByText(/edges may be rough/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("shows the reason when the video cannot be used", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(201, video))
      .mockResolvedValueOnce(
        jsonResponse(200, { ...video, status: "failed", error: "the video is 300s" }),
      );
    const user = userEvent.setup();
    renderApp();
    await fillForm(user);
    await user.click(screen.getByRole("checkbox", { name: /mine to use for ads/ }));
    await user.click(screen.getByRole("button", { name: "Make my game" }));
    expect(await screen.findByText("the video is 300s", {}, { timeout: 3000 })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Choose another video" }));
    expect(screen.getByRole("button", { name: "Make my game" })).toBeInTheDocument();
  });

  it("shows the API's message when the upload is rejected", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(422, { detail: "Only MP4, MOV or WebM videos" }),
    );
    const user = userEvent.setup();
    renderApp();
    await fillForm(user);
    await user.click(screen.getByRole("checkbox", { name: /mine to use for ads/ }));
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Make my game" }));
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Only MP4");
  });

  it("explains when the API cannot be reached", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new TypeError("network"));
    const user = userEvent.setup();
    renderApp();
    await fillForm(user);
    await user.click(screen.getByRole("checkbox", { name: /mine to use for ads/ }));
    await user.click(screen.getByRole("button", { name: "Make my game" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach Reel2Play");
  });

  it("plays the built game in the phone frame", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(201, video))
      .mockResolvedValueOnce(jsonResponse(200, { ...video, status: "ready", ad_id: "a1" }))
      .mockResolvedValueOnce(
        jsonResponse(200, { ...ad, template: "catch", build_url: "https://media.test/game.html" }),
      );
    const user = userEvent.setup();
    renderApp();
    await fillForm(user);
    await user.click(screen.getByRole("checkbox", { name: /mine to use for ads/ }));
    await user.click(screen.getByRole("button", { name: "Make my game" }));
    const frame = await screen.findByTitle("Your game", {}, { timeout: 3000 });
    expect(frame).toHaveAttribute("src", "https://media.test/game.html");
    expect(frame.getAttribute("sandbox")).toContain("allow-scripts");
  });

  async function showAd(body: unknown) {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(201, video))
      .mockResolvedValueOnce(jsonResponse(200, { ...video, status: "ready", ad_id: "a1" }))
      .mockResolvedValueOnce(jsonResponse(200, body));
    const user = userEvent.setup();
    renderApp();
    await fillForm(user);
    await user.click(screen.getByRole("checkbox", { name: /mine to use for ads/ }));
    await user.click(screen.getByRole("button", { name: "Make my game" }));
  }

  it("shows the test report with every check", async () => {
    const progress = [
      ...ad.progress.slice(0, 2),
      { at: "2026-10-28T10:01:00Z", actor: "tester", action: "gate.passed", message: "First frame in 300 ms." },
      { at: "2026-10-28T10:01:01Z", actor: "tester", action: "test.passed", message: "All 13 gates passed." },
      ad.progress[2],
    ];
    await showAd({ ...ad, status: "testing", report, progress });
    const title = await screen.findByRole("heading", { name: "Tested and ready" }, { timeout: 3000 });
    const section = title.closest("section");
    expect(section).toHaveAttribute("lang", "en");
    expect(screen.getByText("Opens quickly")).toBeInTheDocument();
    expect(screen.getByText("Shows your offer and price")).toBeInTheDocument();
    expect(screen.queryByText("First frame in 300 ms.")).not.toBeInTheDocument();
    expect(screen.getByText("All 13 gates passed.")).toBeInTheDocument();
    expect(screen.getByText(report.next_step)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See what the tester saw" })).toHaveAttribute(
      "href",
      "https://media.test/end.png",
    );
  });

  it("shares a published game: link, Reel, captions and Meta files", async () => {
    const share = {
      link: "https://r2p.example/g/AbC1234",
      preview_url: "https://media.test/preview.jpg",
      reel_url: "https://media.test/reel.mp4",
      reel_seconds: 13.6,
      lead_in_url: "https://media.test/lead-in.mp4?sig=1",
      meta_html_url: "https://media.test/playable.html?sig=1",
      meta_zip_url: "https://media.test/playable.zip?sig=1",
      captions: {
        instagram: "Catch them all!\n\n#sneakers",
        facebook: "Play our game.\n\nPlay: https://r2p.example/g/AbC1234",
        whatsapp_status: "Play and win\nhttps://r2p.example/g/AbC1234",
        hashtags: ["sneakers"],
        language: "en",
        written_by: "model",
      },
      published_at: "2026-10-28T10:02:00Z",
    };
    await showAd({ ...ad, status: "published", report, share });
    expect(
      await screen.findByRole("heading", { name: "Your game is live" }, { timeout: 3000 }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How your game was made" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "r2p.example/g/AbC1234" })).toHaveAttribute(
      "href",
      share.link,
    );
    const user = userEvent.setup(); // installs a test clipboard
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    await user.click(screen.getByRole("button", { name: "Copy link" }));
    expect(writeText).toHaveBeenCalledWith(share.link);
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
    expect(screen.getByLabelText("Gameplay Reel")).toHaveAttribute("src", share.reel_url);
    expect(screen.getByText(/14 seconds, recorded from the tester's winning run/)).toBeInTheDocument();
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Play and win");
    await user.click(screen.getByRole("tab", { name: "Instagram" }));
    expect(screen.getByRole("tab", { name: "Instagram" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Catch them all!");
    await user.click(screen.getByRole("button", { name: "Copy caption" }));
    expect(writeText).toHaveBeenLastCalledWith(share.captions.instagram);
    expect(screen.getByRole("link", { name: "Playable as a ZIP" })).toHaveAttribute(
      "href",
      share.meta_zip_url,
    );
  });

  it("explains a game that needs a person, in Urdu", async () => {
    const failing = {
      ...report,
      passed: false,
      language: "ur",
      rounds: 3,
      summary: "ہم نے تین بار ٹھیک کرنے کی کوشش کی۔",
      next_step: "ہماری ٹیم دیکھے گی۔",
      gates: [
        gates[0],
        {
          gate: "offer_shown",
          label: "آپ کی آفر اور قیمت دکھاتی ہے",
          passed: false,
          message: "The critic could not read the offer or the price.",
          screenshot_url: "https://media.test/bad.png",
        },
      ],
    };
    await showAd({ ...ad, status: "needs_person", report: failing });
    const title = await screen.findByRole(
      "heading",
      { name: "یہ گیم ہماری ٹیم دیکھے گی" },
      { timeout: 3000 },
    );
    expect(title.closest("section")).toHaveAttribute("dir", "rtl");
    expect(screen.getByText("The critic could not read the offer or the price.")).toHaveAttribute(
      "dir",
      "ltr",
    );
    expect(screen.getByRole("link", { name: "ٹیسٹر نے کیا دیکھا" })).toHaveAttribute(
      "href",
      "https://media.test/bad.png",
    );
  });

  it("shows a failed ad's reason", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(201, video))
      .mockResolvedValueOnce(jsonResponse(200, { ...video, status: "ready", ad_id: "a1" }))
      .mockResolvedValueOnce(
        jsonResponse(200, {
          ...ad,
          status: "failed",
          error: "the product could not be cut out",
          brief: null,
          progress: ad.progress.slice(0, 2),
        }),
      );
    const user = userEvent.setup();
    renderApp();
    await fillForm(user);
    await user.click(screen.getByRole("checkbox", { name: /mine to use for ads/ }));
    await user.click(screen.getByRole("button", { name: "Make my game" }));
    expect(await screen.findByRole("alert", {}, { timeout: 3000 })).toHaveTextContent(
      "could not be cut out",
    );
  });

  it("has a not-found page", () => {
    renderApp("/nowhere");
    expect(screen.getByText("Page not found")).toBeInTheDocument();
  });

  it("sends a chosen voice note with the video", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(422, { detail: "stop here" }),
    );
    const user = userEvent.setup();
    renderApp();
    await fillForm(user);
    const note = new File(["voice"], "note.m4a", { type: "audio/mp4" });
    await user.upload(screen.getByLabelText(/audio file/), note);
    expect(screen.getByLabelText("Your voice note")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /mine to use for ads/ }));
    await user.click(screen.getByRole("button", { name: "Make my game" }));
    const form = (fetchMock.mock.calls[0]![1] as RequestInit).body as FormData;
    expect((form.get("voice_note") as File).name).toBe("note.m4a");
    expect(await screen.findByRole("alert")).toHaveTextContent("stop here");
    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(screen.queryByLabelText("Your voice note")).not.toBeInTheDocument();
  });

  it("records a voice note where the browser can", async () => {
    const stopTrack = vi.fn();
    const stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream;
    class FakeRecorder extends EventTarget {
      state = "inactive";
      mimeType = "audio/webm";
      stream = stream;
      start() {
        this.state = "recording";
      }
      stop() {
        this.state = "inactive";
        const data = new Event("dataavailable") as Event & { data: Blob };
        data.data = new Blob(["sound"], { type: "audio/webm" });
        this.dispatchEvent(data);
        this.dispatchEvent(new Event("stop"));
      }
    }
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    });
    const user = userEvent.setup();
    renderApp();
    await user.click(screen.getByRole("button", { name: "Record a voice note" }));
    expect(await screen.findByText(/Recording 0:0/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stop" }));
    expect(await screen.findByLabelText("Your voice note")).toBeInTheDocument();
    expect(stopTrack).toHaveBeenCalled();
    vi.unstubAllGlobals();
    Reflect.deleteProperty(navigator, "mediaDevices");
  });

  it("says when the microphone cannot be used", async () => {
    vi.stubGlobal("MediaRecorder", class {});
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockRejectedValue(new Error("denied")) },
    });
    const user = userEvent.setup();
    renderApp();
    await user.click(screen.getByRole("button", { name: "Record a voice note" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("microphone is not available");
    vi.unstubAllGlobals();
    Reflect.deleteProperty(navigator, "mediaDevices");
  });

  it("asks whether several photos are different products", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(422, { detail: "stop here" }),
    );
    const user = userEvent.setup();
    renderApp();
    await user.type(screen.getByLabelText("Shop name"), "Ali Shoes");
    await user.type(screen.getByLabelText("WhatsApp number for orders"), "923001234567");
    await user.upload(screen.getByLabelText(/Video or photos/), [
      new File(["a"], "a.jpg", { type: "image/jpeg" }),
      new File(["b"], "b.jpg", { type: "image/jpeg" }),
    ]);
    await user.click(screen.getByLabelText(/different products/));
    await user.click(screen.getByLabelText(/invent a new kind of game/));
    await user.click(screen.getByLabelText(/mine to use for ads/));
    await user.click(screen.getByRole("button", { name: "Make my game" }));
    const form = (fetchMock.mock.calls[0]![1] as RequestInit).body as FormData;
    expect(form.get("catalog")).toBe("true");
    expect(form.get("lab")).toBe("true");
    expect(form.getAll("files")).toHaveLength(2);
  });
});
