"""Exact replays of tested runs, recorded as frames for the gameplay Reel (feature 33).

Game time moves only when the harness advances it, so the commands a player sent are the
run itself: sending them again to a fresh page plays the same game, step for step. The
publish step replays the tester's winning run at twice the pixel density and keeps a frame
for every ``1 / fps`` of game time.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

from reel2play.gates.thresholds import SCREENS
from reel2play.playtest.session import Harness

GAME_COMMANDS = frozenset({"start", "restart", "tap", "drag", "advance"})
RECORD_FPS = 20
RECORD_SCALE = 2.0
END_CARD_SETTLE_MS = 900

Command = dict[str, Any]


class TracingHarness:
    """Passes every command through and keeps the ones that change the game."""

    def __init__(self, inner: Harness) -> None:
        self._inner = inner
        self._commands: list[Command] = []

    def call(self, cmd: str, **args: Any) -> dict[str, Any]:
        if cmd in GAME_COMMANDS:
            self._commands.append({"cmd": cmd, **args})
        return self._inner.call(cmd, **args)

    def close(self) -> None:
        self._inner.close()

    def take(self) -> list[Command]:
        """The commands since the last take: one run's replay."""
        commands, self._commands = self._commands, []
        return commands


@dataclass(frozen=True)
class Frame:
    t: float
    jpeg: bytes


@dataclass
class Recording:
    intro: Frame
    end: Frame
    frames: list[Frame] = field(default_factory=list)
    won: bool = False
    seconds: float = 0.0


def frames_in(reply: dict[str, Any]) -> list[Frame]:
    return [Frame(float(f["t"]), base64.b64decode(f["jpeg_b64"])) for f in reply.get("frames", [])]


def send(harness: Harness, command: Command) -> dict[str, Any]:
    args = {key: value for key, value in command.items() if key != "cmd"}
    return harness.call(str(command["cmd"]), **args)


def record_run(
    harness: Harness,
    html_b64: str,
    replays: list[list[Command]],
    index: int,
    *,
    fps: int = RECORD_FPS,
    scale: float = RECORD_SCALE,
) -> Recording:
    """Replay runs ``0..index`` in a fresh page and record run ``index``.

    Earlier runs are replayed too, because each restart moves the game to the next seed.
    """
    width, height = SCREENS["phone"]
    harness.call("open", html_b64=html_b64, width=width, height=height, scale=scale)
    [intro] = frames_in(harness.call("settle", ms=400))
    for commands in replays[:index]:
        for command in commands:
            send(harness, command)
    harness.call("record", fps=fps)
    frames: list[Frame] = []
    for command in replays[index]:
        frames.extend(frames_in(send(harness, command)))
    harness.call("stop_recording")
    [end] = frames_in(harness.call("settle", ms=END_CARD_SETTLE_MS))
    state = harness.call("state")
    return Recording(
        intro=intro,
        end=end,
        frames=frames,
        won=state["outcome"] == "won",
        seconds=round(float(state["elapsed"]), 2),
    )
