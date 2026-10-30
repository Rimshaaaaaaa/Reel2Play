"""Play-test harness: runs one game page in headless Chromium and answers JSON commands.

This file runs on its own (standard library and Playwright only): locally as a subprocess
in development and CI, and inside a Modal Sandbox with networking blocked in production
(feature 57). It reads one JSON command per line on stdin and writes one JSON reply per
line on stdout.

Every request the page makes after loading is blocked and recorded; the page gets no
network at all.

Game time moves only when the harness says so (the engine's manual clock, switched on
before the first tap), so a run is a fixed list of commands and replays exactly. While
recording, each ``advance`` also returns frames sampled every ``1 / fps`` of game time,
for the gameplay Reel (feature 33).
"""

from __future__ import annotations

import base64
import json
import sys
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

END_CARD_PARTS = ("result", "offer", "price", "coupon", "cta", "replay")
TICK_S = 1 / 60  # the engine's fixed step; advances are split only on whole ticks
ADVANCE_JS = "(s) => { window.__r2p.advance(s); return window.__r2p.phase() === 'playing'; }"
TEXT_STYLE_JS = """
() => {
  const pick = (el) => {
    const s = getComputedStyle(el);
    let node = el, bg = 'rgba(0, 0, 0, 0)';
    while (node && (bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent')) {
      bg = getComputedStyle(node).backgroundColor; node = node.parentElement;
    }
    return { text: el.textContent.trim(), color: s.color, background: bg,
             size: parseFloat(s.fontSize) };
  };
  const card = document.querySelector('[data-r2p="end"]');
  if (!card) return [];
  return [...card.querySelectorAll('h1,h2,p,a,button,strong')]
    .filter((el) => el.textContent.trim()).map(pick);
}
"""


class Harness:
    def __init__(self, browser: Browser) -> None:
        self.browser = browser
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.console_errors: list[str] = []
        self.requests: list[str] = []
        self.navigations: list[str] = []
        self.popups: list[str] = []
        self.frame_every: float | None = None  # game seconds between frames while recording
        self.since_frame = 0.0

    # --- helpers --------------------------------------------------------------------------

    def _page(self) -> Page:
        if self.page is None:
            raise RuntimeError("no page is open; send 'open' first")
        return self.page

    def _on_console(self, message: Any) -> None:
        if message.type == "error":
            self.console_errors.append(message.text)

    def _on_navigation(self, frame: Any) -> None:
        page = self._page()
        if frame == page.main_frame and frame.url != "about:blank":
            self.navigations.append(frame.url)

    def _block(self, route: Any) -> None:
        """No network at all. Requests from the game page are recorded; a page the order
        button opens is the button working, not the game calling out."""
        if self._from_game(route.request):
            self.requests.append(route.request.url)
        route.abort()

    def _from_game(self, request: Any) -> bool:
        try:
            return self.page is not None and request.frame.page == self.page
        except Exception:  # a popup's first request has no frame yet: not the game's
            return False

    # --- commands -------------------------------------------------------------------------

    def open(
        self,
        html_b64: str,
        width: int,
        height: int,
        throttle: float = 1.0,
        touch: bool = True,
        scale: float = 1.0,
        layout: str | None = None,
    ) -> dict[str, Any]:
        """Open the game at a screen size. Screenshots have ``scale`` pixels per CSS pixel;
        tap and drag points are always in CSS pixels. ``layout`` opens a square or landscape
        page, as ``?layout=`` does on the hosted game."""
        self.close_page()
        self.frame_every = None
        self.context = self.browser.new_context(
            viewport={"width": width, "height": height},
            has_touch=touch,
            device_scale_factor=scale,
        )
        self.context.route("**/*", self._block)
        if layout:
            self.context.add_init_script(f"window.R2P_LAYOUT = {json.dumps(layout)};")
        self.context.on("page", lambda popup: self.popups.append(popup.url))
        page = self.context.new_page()
        self.page = page
        page.on("console", self._on_console)
        page.on("pageerror", lambda error: self.console_errors.append(str(error)))
        page.on("framenavigated", self._on_navigation)
        if throttle > 1:
            cdp = self.context.new_cdp_session(page)
            cdp.send("Emulation.setCPUThrottlingRate", {"rate": throttle})
        started = time.monotonic()
        before = float(page.evaluate("() => performance.now()"))
        page.set_content(base64.b64decode(html_b64).decode("utf-8"), wait_until="load")
        page.wait_for_function(
            "() => window.__r2p && window.__r2p.firstFrameMs() !== null", timeout=15000
        )
        first_frame = float(page.evaluate("() => window.__r2p.firstFrameMs()")) - before
        return {
            "load_ms": round((time.monotonic() - started) * 1000),
            "first_frame_ms": round(first_frame),
            "phase": page.evaluate("() => window.__r2p.phase()"),
        }

    def start(self) -> dict[str, Any]:
        return self._press("play")

    def restart(self) -> dict[str, Any]:
        return self._press("replay")

    def _press(self, button: str) -> dict[str, Any]:
        """Pause the clock first, so no real time leaks into the run, then press."""
        page = self._page()
        page.evaluate("() => window.__r2p.setManual(true)")
        page.locator(f'[data-r2p="{button}"]').tap(timeout=5000)
        return self.state()

    def tap(self, x: float, y: float) -> dict[str, Any]:
        page = self._page()
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.up()
        return {"ok": True}

    def drag(self, x1: float, y1: float, x2: float, y2: float) -> dict[str, Any]:
        page = self._page()
        page.mouse.move(x1, y1)
        page.mouse.down()
        page.mouse.move(x2, y2, steps=6)
        page.mouse.up()
        return {"ok": True}

    def advance(self, seconds: float) -> dict[str, Any]:
        if self.frame_every is None:
            self._page().evaluate("(s) => window.__r2p.advance(s)", seconds)
            return self.state()
        return {**self.state(), "frames": self._advance_recording(seconds)}

    def _advance_recording(self, seconds: float) -> list[dict[str, Any]]:
        """The same advance in whole-tick chunks (so the game steps exactly as it would in one
        call), with a frame each time ``frame_every`` of game time has passed, and one more
        at the moment the game ends."""
        assert self.frame_every is not None
        page = self._page()
        if page.evaluate("() => window.__r2p.phase()") != "playing":
            return []  # the clock is stopped: nothing new to record
        chunk = max(1, round(self.frame_every / TICK_S)) * TICK_S
        frames: list[dict[str, Any]] = []
        left = seconds
        while left > 1e-9:
            step = chunk if left >= chunk - 1e-9 else left
            playing = page.evaluate(ADVANCE_JS, step)
            left -= step
            self.since_frame += step
            if not playing:
                frames.append(self._frame())
                break
            if self.since_frame >= self.frame_every - 1e-9:
                self.since_frame -= self.frame_every  # keep the remainder: fps on average
                frames.append(self._frame())
        return frames

    def _frame(self) -> dict[str, Any]:
        page = self._page()
        jpeg = page.screenshot(type="jpeg", quality=82)
        elapsed = float(page.evaluate("() => window.__r2p.elapsed()"))
        return {"t": round(elapsed, 4), "jpeg_b64": base64.b64encode(jpeg).decode("ascii")}

    def record(self, fps: float) -> dict[str, Any]:
        """From now on, ``advance`` also returns frames, ``fps`` per second of game time."""
        self.frame_every = 1.0 / fps
        self.since_frame = 0.0
        return {"recording": True}

    def stop_recording(self) -> dict[str, Any]:
        self.frame_every = None
        return {"recording": False}

    def state(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = self._page().evaluate(
            "() => ({phase: __r2p.phase(), elapsed: __r2p.elapsed(), outcome: __r2p.outcome(),"
            " runs: __r2p.runs(), state: __r2p.state(), template: __r2p.config.template})"
        )
        return snapshot

    def screenshot(self) -> dict[str, Any]:
        png = self._page().screenshot(type="png")
        return {"png_b64": base64.b64encode(png).decode("ascii")}

    def settle(self, ms: int) -> dict[str, Any]:
        """Let real time pass (the end card's entrance animation), then take a frame."""
        self._page().wait_for_timeout(ms)
        return {"frames": [self._frame()]}

    def to_screen(self, x: float, y: float) -> dict[str, Any]:
        point = self._page().evaluate("([x, y]) => window.__r2p.toScreen(x, y)", [x, y])
        return {"x": point["x"], "y": point["y"]}

    def end_card(self) -> dict[str, Any]:
        page = self._page()
        stage = page.locator(".r2p-stage").bounding_box()
        parts: dict[str, Any] = {}
        for name in END_CARD_PARTS:
            node = page.locator(f'[data-r2p="{name}"]')
            if node.count() == 0:
                continue
            parts[name] = {
                "text": node.inner_text().strip(),
                "box": node.bounding_box(),
                "visible": node.is_visible(),
                "clipped": node.evaluate("el => el.scrollWidth > el.clientWidth + 1"),
                "href": node.get_attribute("href"),
            }
        viewport = page.viewport_size or {"width": 0, "height": 0}
        side = page.locator('[data-r2p="side"]')
        return {
            "stage": stage,
            "viewport": viewport,
            "layout": page.evaluate("() => document.querySelector('.r2p')?.dataset.layout"),
            "side": side.bounding_box() if side.count() else None,
            "parts": parts,
            "styles": page.evaluate(TEXT_STYLE_JS),
            "visible": page.locator('[data-r2p="end"]').is_visible(),
        }

    def click_cta(self) -> dict[str, Any]:
        page = self._page()
        page.evaluate(
            "() => { window.__ctaCalls = 0; window.FbPlayableAd = "
            "{ onCTAClick: () => { window.__ctaCalls += 1; } }; }"
        )
        cta = page.locator('[data-r2p="cta"]')
        href = cta.get_attribute("href")
        before = len(self.popups)
        cta.tap(timeout=5000)
        page.wait_for_timeout(300)
        text = parse_qs(urlparse(href).query).get("text", [""])[0] if href else ""
        return {
            "href": href,
            "popups": self.popups[before:],
            "fb_calls": page.evaluate("() => window.__ctaCalls"),
            "message": text,
            "tag": cta.evaluate("el => el.tagName"),
        }

    def poster(self, html_b64: str) -> dict[str, Any]:
        """Feature 36: print an A4 poster to PDF, and take a picture of it to read the QR
        code back. Its own context, with the network blocked like every game."""
        context = self.browser.new_context(
            viewport={"width": 794, "height": 1123}, device_scale_factor=2
        )
        try:
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            page.set_content(base64.b64decode(html_b64).decode("utf-8"), wait_until="load")
            page.evaluate("() => document.fonts.ready")
            png = page.screenshot(type="png")
            pdf = page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            context.close()
        return {
            "pdf_b64": base64.b64encode(pdf).decode("ascii"),
            "png_b64": base64.b64encode(png).decode("ascii"),
        }

    def log(self) -> dict[str, Any]:
        return {
            "console_errors": self.console_errors,
            "requests": self.requests,
            "navigations": self.navigations,
        }

    def close_page(self) -> None:
        if self.context is not None:
            self.context.close()
        self.context = None
        self.page = None


def serve(stdin: Any = sys.stdin, stdout: Any = sys.stdout) -> None:
    with sync_playwright() as playwright:
        harness = Harness(playwright.chromium.launch(args=["--disable-gpu"]))
        stdout.write(json.dumps({"ready": True}) + "\n")
        stdout.flush()
        for line in stdin:
            if not line.strip():
                continue
            command = json.loads(line)
            name = command.pop("cmd")
            if name == "quit":
                break
            try:
                reply: dict[str, Any] = {"ok": True, **getattr(harness, name)(**command)}
            except Exception as exc:  # report every failure to the caller, keep serving
                reply = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:600]}
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
        harness.close_page()


if __name__ == "__main__":
    serve()
