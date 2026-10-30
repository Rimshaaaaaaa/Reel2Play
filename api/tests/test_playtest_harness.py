"""The play-test harness in a real headless Chromium, and where it runs (feature 57)."""

from __future__ import annotations

import base64
import io
import json
import sys
import types
from collections.abc import Iterator
from typing import Any

import pytest
from PIL import Image

from reel2play.builder.templates import load_templates
from reel2play.playtest.drivers import AgentDriver, ScriptedDriver
from reel2play.playtest.replay import TracingHarness, record_run
from reel2play.playtest.session import (
    HarnessError,
    LineChannel,
    LocalHarness,
    ModalHarness,
    SandboxUnavailableError,
    modal_configured,
    open_harness,
)
from reel2play.publish.meta import check_playable
from reel2play.settings import AppEnv, Settings, get_settings
from tests.helpers import game_html


@pytest.fixture(scope="module")
def harness() -> Iterator[LocalHarness]:
    local = LocalHarness()
    yield local
    local.close()


def pace_of(template: str) -> float:
    return load_templates(get_settings().templates_dir)[template].tester_pace_seconds


def b64(html: bytes) -> str:
    return base64.b64encode(html).decode()


def test_open_play_and_measure(harness: LocalHarness) -> None:
    opened = harness.call(
        "open", html_b64=b64(game_html("catch")), width=360, height=640, throttle=4
    )
    assert opened["phase"] == "intro"
    assert 0 <= opened["first_frame_ms"] < 2000
    shot = Image.open(io.BytesIO(base64.b64decode(harness.call("screenshot")["png_b64"])))
    assert shot.size == (360, 640)
    state = harness.call("start")
    assert state["phase"] == "playing"
    assert state["template"] == "catch"
    harness.call("tap", x=100, y=560)
    harness.call("drag", x1=100, y1=560, x2=250, y2=560)
    before = harness.call("state")["elapsed"]
    later = harness.call("advance", seconds=1.0)
    assert later["elapsed"] - before == pytest.approx(1.0, abs=0.02)
    assert harness.call("to_screen", x=180, y=320) == {"ok": True, "x": 180, "y": 320}
    ended = harness.call("advance", seconds=31)
    assert ended["phase"] == "ended"
    card = harness.call("end_card")
    assert card["visible"]
    assert card["parts"]["price"]["text"] == "Rs 2,499"
    assert card["styles"]
    cta = harness.call("click_cta")
    assert cta["href"].startswith("https://wa.me/923001234567")
    assert "Sneaker" in cta["message"]
    assert cta["popups"]
    log = harness.call("log")
    assert log["requests"] == []
    assert log["navigations"] == []
    restarted = harness.call("restart")
    assert restarted["runs"] == 2


def test_harness_reports_problems(harness: LocalHarness) -> None:
    page = (
        b"<html><body><script>fetch('https://example.com/x'); console.error('boom');"
        b"</script></body></html>"
    )
    with pytest.raises(HarnessError, match="open"):
        harness.call("open", html_b64=b64(page), width=360, height=640)
    log = harness.call("log")
    assert any("example.com" in url for url in log["requests"])
    assert any("boom" in error for error in log["console_errors"])
    with pytest.raises(HarnessError, match="no_such_command"):
        harness.call("no_such_command")


@pytest.mark.parametrize("template", ["catch", "runner", "puzzle"])
def test_scripted_runs_win_and_replay_exactly(template: str) -> None:
    """Each template is won, and its runs replay frame for frame (feature 33)."""
    page = b64(game_html(template))
    local = LocalHarness()
    try:
        local.call("open", html_b64=page, width=360, height=640, throttle=4)
        tracer = TracingHarness(local)
        runs, replays = [], []
        for index in range(2):
            runs.append(ScriptedDriver(pace_of(template)).play(tracer, index))
            replays.append(tracer.take())
        recordings = [record_run(local, page, replays, i, fps=10, scale=1) for i in range(2)]
    finally:
        local.close()
    assert any(run.won for run in runs)
    assert all(15 <= run.seconds <= 30 for run in runs if run.won)
    assert all(run.final_png for run in runs)
    assert runs[0].gameplay_png is not None
    assert all(run.driver == "scripted" for run in runs)
    assert replays[0][0]["cmd"] == "start"
    assert replays[1][0]["cmd"] == "restart"
    for run, recording in zip(runs, recordings, strict=True):
        assert (recording.won, recording.seconds) == (run.won, run.seconds)
        times = [frame.t for frame in recording.frames]
        assert times == sorted(times)
        assert len(times) == pytest.approx(run.seconds * 10, abs=3)
        frame = Image.open(io.BytesIO(recording.frames[0].jpeg))
        assert (frame.format, frame.size) == ("JPEG", (360, 640))
        assert recording.intro.jpeg != recording.end.jpeg


def test_meta_playable_calls_fb_and_stays_offline(harness: LocalHarness) -> None:
    check = check_playable(harness, b64(game_html("runner", platform="meta")))
    assert check.cta_calls == 1
    assert check.problems == []
    hosted = check_playable(harness, b64(game_html("runner")))
    assert hosted.cta_calls == 0
    assert "the game tried to open another page" in hosted.problems


def test_recording_samples_game_time(harness: LocalHarness) -> None:
    harness.call("open", html_b64=b64(game_html("catch")), width=360, height=640, scale=2)
    harness.call("start")
    assert harness.call("record", fps=20) == {"ok": True, "recording": True}
    frames = [f for _ in range(5) for f in harness.call("advance", seconds=0.12)["frames"]]
    times = [f["t"] for f in frames]
    assert times[:2] == [0.05, 0.1]
    assert times == sorted(set(times))
    assert len(times) == 12  # 0.6 s of game time at 20 frames per second
    size = Image.open(io.BytesIO(base64.b64decode(frames[0]["jpeg_b64"]))).size
    assert size == (720, 1280)
    harness.call("stop_recording")
    assert "frames" not in harness.call("advance", seconds=0.1)


def test_agent_driver_plays_with_the_mock_tester() -> None:
    from reel2play.ai.client import Subject, build_ai
    from reel2play.ai.cost import MemoryRecorder
    from reel2play.settings import AIMode

    client = build_ai(Settings(ai_mode=AIMode.MOCK), recorder=MemoryRecorder())
    local = LocalHarness()
    try:
        local.call("open", html_b64=b64(game_html("catch")), width=360, height=640)
        run = AgentDriver(client, Subject(), "Catch the sneakers.").play(local, 0)
    finally:
        local.close()
    assert run.driver == "mock"
    assert run.verdict == {
        "won": False,
        "fun": 4,
        "problems": [],
        "notes": "Simple and clear; the offer shows at the end.",
    }
    assert run.trace[0]["tool"] == "tap"
    assert run.actions >= 2
    assert run.seconds >= 20  # the mock taps blindly, so the time limit ends the run
    assert not run.won


def test_idle_strategy_for_unknown_templates() -> None:
    class FakeHarness:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def call(self, cmd: str, **_: Any) -> dict[str, Any]:
            self.calls.append(cmd)
            if cmd == "state":
                return {"template": "dance_off", "outcome": "lost", "elapsed": 30.0}
            if cmd == "screenshot":
                return {"png_b64": ""}
            if cmd == "advance":
                return {"phase": "ended" if self.calls.count("advance") > 2 else "playing"}
            return {}

        def close(self) -> None:
            return None

    fake = FakeHarness()
    run = ScriptedDriver().play(fake, 1)
    assert fake.calls[0] == "restart"
    assert not run.won


# --- where the harness runs ---------------------------------------------------------------


def test_line_channel_errors() -> None:
    channel = LineChannel(iter([]), lambda _: None, timeout=1)
    with pytest.raises(HarnessError, match="stopped"):
        channel.receive()
    quiet = LineChannel(_never(), lambda _: None, timeout=0.2)
    with pytest.raises(HarnessError, match="did not answer"):
        quiet.receive()
    failing = LineChannel(iter([json.dumps({"ok": False, "error": "bad"})]), lambda _: None, 1)
    with pytest.raises(HarnessError, match="tap: bad"):
        failing.call("tap")


def _never() -> Iterator[str]:
    import time

    time.sleep(5)
    yield ""


def test_production_needs_modal() -> None:
    prod = Settings(app_env=AppEnv.PRODUCTION)
    assert not modal_configured(prod)
    with pytest.raises(SandboxUnavailableError, match="Modal Sandbox"):
        open_harness(prod)


def test_modal_harness_blocks_the_network(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, Any] = {}

    class Stream:
        def __init__(self) -> None:
            self.written: list[str] = []

        def write(self, text: str) -> None:
            self.written.append(text)

        def drain(self) -> None:
            return None

    class Process:
        def __init__(self) -> None:
            self.stdin = Stream()
            self.stdout = iter([json.dumps({"ready": True}), json.dumps({"ok": True, "x": 1})])

    class Sandbox:
        terminated = False

        @classmethod
        def create(cls, **kwargs: Any) -> Sandbox:
            created.update(kwargs)
            return cls()

        def exec(self, *args: Any, **kwargs: Any) -> Process:
            created["exec"] = args
            self.process = Process()
            return self.process

        def terminate(self) -> None:
            Sandbox.terminated = True

    class Image:
        @staticmethod
        def from_registry(name: str) -> Image:
            created["registry"] = name
            return Image()

        def add_local_file(self, local: str, remote: str) -> Image:
            created["file"] = remote
            return self

    fake = types.SimpleNamespace(
        App=types.SimpleNamespace(lookup=lambda name, create_if_missing: f"app:{name}"),
        Image=Image,
        Sandbox=Sandbox,
    )
    monkeypatch.setitem(sys.modules, "modal", fake)
    settings = Settings(modal_token_id="id", modal_token_secret="secret")  # type: ignore[arg-type]
    assert modal_configured(settings)
    harness = open_harness(settings)
    assert isinstance(harness, ModalHarness)
    assert created["block_network"] is True
    assert created["app"] == "app:reel2play-playtest"
    assert created["exec"] == ("python", "/harness/harness.py")
    assert created["registry"].startswith("mcr.microsoft.com/playwright/python:v1.63.0")
    assert harness.call("state") == {"ok": True, "x": 1}
    harness.close()
    assert Sandbox.terminated
