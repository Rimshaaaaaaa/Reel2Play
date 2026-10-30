"""Who plays each test run (feature 25).

- AgentDriver: the play-tester model (Muse Glimmer, or Spark Open as failover) plays from
  screenshots, turn by turn on the game's manual clock, with tap, drag and wait tools.
- ScriptedDriver: simple built-in strategies per template. Used only with the mock model,
  so everything runs without keys; its runs are labelled scripted, never as a model's.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, Field

from reel2play.ai.agent import Observation, run_agent
from reel2play.ai.client import AIClient, Subject
from reel2play.ai.messages import Media, MediaKind
from reel2play.ai.tools import Tool, ToolOutput, ToolRegistry
from reel2play.playtest.session import Harness
from reel2play.safety import as_data

DEFAULT_PACE_S = 0.35  # game seconds per tester action, unless the template sets its own
MAX_TURNS = 45


@dataclass
class RunResult:
    index: int
    driver: str
    won: bool
    seconds: float
    actions: int
    trace: list[dict[str, Any]] = field(default_factory=list)
    verdict: dict[str, Any] | None = None
    gameplay_png: bytes | None = None
    final_png: bytes | None = None


class Driver(Protocol):
    name: str

    def play(self, harness: Harness, index: int) -> RunResult: ...


def screenshot(harness: Harness) -> bytes:
    return base64.b64decode(harness.call("screenshot")["png_b64"])


def _begin(harness: Harness, index: int) -> None:
    harness.call("start" if index == 0 else "restart")


def _finish(harness: Harness, result: RunResult) -> RunResult:
    state = harness.call("state")
    result.won = state["outcome"] == "won"
    result.seconds = round(float(state["elapsed"]), 2)
    result.final_png = screenshot(harness)
    return result


# --- scripted strategies (mock mode) -------------------------------------------------------


class ScriptedDriver:
    name = "scripted"

    def __init__(self, pace: float = DEFAULT_PACE_S) -> None:
        self.pace = pace  # used where a person stops to think (the puzzle)

    def play(self, harness: Harness, index: int) -> RunResult:
        _begin(harness, index)
        result = RunResult(index=index, driver=self.name, won=False, seconds=0.0, actions=0)
        template = harness.call("state")["template"]
        strategy = {
            "catch": self._catch,
            "runner": self._runner,
            "puzzle": self._puzzle,
            "memory": self._memory,
            "scratch": self._scratch,
            "spots": self._spots,
            "stack": self._stack,
            "quiz": self._quiz,
            "colours": self._colours,
            "custom": self._custom,
        }.get(template, self._idle)
        strategy(harness, result)
        return _finish(harness, result)

    @staticmethod
    def _tap(harness: Harness, x: float, y: float, result: RunResult) -> None:
        point = harness.call("to_screen", x=x, y=y)
        harness.call("tap", x=point["x"], y=point["y"])
        result.actions += 1

    def _catch(self, harness: Harness, result: RunResult) -> None:
        state = harness.call("advance", seconds=0.0)
        while state["phase"] == "playing":
            game = state["state"]
            products = [i for i in game["items"] if i["kind"] == "product"]
            landing = [i for i in products if i["y"] < game["bagY"] + 5]
            if landing:
                self._tap(harness, max(landing, key=lambda i: i["y"])["x"], 560, result)
            if result.gameplay_png is None and state["elapsed"] > 3:
                result.gameplay_png = screenshot(harness)
            state = harness.call("advance", seconds=0.12)

    def _runner(self, harness: Harness, result: RunResult) -> None:
        state = harness.call("advance", seconds=0.0)
        while state["phase"] == "playing":
            game = state["state"]
            due = any(18 < c["ahead"] < 70 for c in game["crates"])
            if due and game["onGround"]:
                self._tap(harness, 180, 300, result)
            if result.gameplay_png is None and state["elapsed"] > 3:
                result.gameplay_png = screenshot(harness)
            state = harness.call("advance", seconds=0.04)

    def _puzzle(self, harness: Harness, result: RunResult) -> None:
        state = harness.call("advance", seconds=0.0)
        result.gameplay_png = screenshot(harness)
        while state["phase"] == "playing":
            tiles: list[int] = state["state"]["tiles"]
            cells = state["state"]["cells"]
            wrong = next((cell for cell, piece in enumerate(tiles) if piece != cell), None)
            if wrong is None:
                state = harness.call("advance", seconds=0.1)
                continue
            for cell in (wrong, tiles.index(wrong)):
                box = cells[cell]
                self._tap(harness, box["x"] + box["w"] / 2, box["y"] + box["h"] / 2, result)
                state = harness.call("advance", seconds=self.pace)

    def _shot(self, harness: Harness, state: dict[str, Any], result: RunResult) -> None:
        if result.gameplay_png is None and state["elapsed"] > 3:
            result.gameplay_png = screenshot(harness)

    def _tap_box(self, harness: Harness, box: dict[str, float], result: RunResult) -> None:
        self._tap(harness, box["x"] + box["w"] / 2, box["y"] + box["h"] / 2, result)

    def _memory(self, harness: Harness, result: RunResult) -> None:
        """Like a person: remembers only the cards it has seen face up."""
        seen: dict[int, int] = {}

        def flip(index: int) -> dict[str, Any]:
            cards = harness.call("state")["state"]["cards"]
            self._tap_box(harness, cards[index], result)
            state = harness.call("advance", seconds=self.pace)
            seen[index] = state["state"]["cards"][index]["face"]
            self._shot(harness, state, result)
            return state

        state = harness.call("advance", seconds=0.0)
        while state["phase"] == "playing":
            game = state["state"]
            cards = game["cards"]
            if game["peeking"] or game["busy"] or any(c["up"] and not c["matched"] for c in cards):
                state = harness.call("advance", seconds=0.1)
                continue
            open_cards = {i: f for i, f in seen.items() if not cards[i]["matched"]}
            pair = next(
                ((i, j) for i in open_cards for j in open_cards
                 if i < j and open_cards[i] == open_cards[j]),
                None,
            )  # fmt: skip
            if pair:
                flip(pair[0])
                state = flip(pair[1])
                continue
            unseen = [i for i, c in enumerate(cards) if i not in seen and not c["matched"]]
            if not unseen:
                state = harness.call("advance", seconds=0.1)
                continue
            flip(unseen[0])
            face = seen[unseen[0]]
            known = next((i for i, f in open_cards.items() if f == face), None)
            second = known if known is not None else (unseen[1] if len(unseen) > 1 else unseen[0])
            state = flip(second)

    def _custom(self, harness: Harness, result: RunResult) -> None:
        """Feature 24: taps where the mechanic's own hint says a skilled player would."""
        state = harness.call("advance", seconds=0.0)
        while state["phase"] == "playing":
            hint = state["state"].get("hint")
            if hint:
                self._tap(harness, float(hint[0]), float(hint[1]), result)
            state = harness.call("advance", seconds=self.pace)
            self._shot(harness, state, result)

    def _scratch(self, harness: Harness, result: RunResult) -> None:
        """Rubs the card in rows, top to bottom, pass after pass."""
        state = harness.call("advance", seconds=0.0)
        card = state["state"]["card"]
        step = state["state"]["brush"] * 1.5
        rows = max(1, int(-(-card["h"] // step)))
        row = 0
        while state["phase"] == "playing":
            y = card["y"] + step / 2 + (row % rows) * step
            xs = (card["x"] + 4, card["x"] + card["w"] - 4)
            x1, x2 = xs if row % 2 == 0 else xs[::-1]
            a = harness.call("to_screen", x=x1, y=y)
            b = harness.call("to_screen", x=x2, y=y)
            harness.call("drag", x1=a["x"], y1=a["y"], x2=b["x"], y2=b["y"])
            result.actions += 1
            state = harness.call("advance", seconds=self.pace)
            self._shot(harness, state, result)
            row += 1

    def _spots(self, harness: Harness, result: RunResult) -> None:
        state = harness.call("advance", seconds=0.0)
        while state["phase"] == "playing":
            lit = next((s for s in state["state"]["spots"] if s["state"] == "lit"), None)
            if lit:
                self._tap(harness, lit["x"], lit["y"], result)
                state = harness.call("advance", seconds=self.pace)
            else:
                state = harness.call("advance", seconds=0.1)
            self._shot(harness, state, result)

    def _stack(self, harness: Harness, result: RunResult) -> None:
        state = harness.call("advance", seconds=0.0)
        while state["phase"] == "playing":
            game = state["state"]
            moving = game["moving"]
            if moving and abs(moving["x"] - game["top"]["x"]) <= 3:
                self._tap(harness, 180, 320, result)
            self._shot(harness, state, result)
            state = harness.call("advance", seconds=1 / 60)

    def _quiz(self, harness: Harness, result: RunResult) -> None:
        state = harness.call("advance", seconds=0.0)
        while state["phase"] == "playing":
            game = state["state"]
            if game["step"] == "answering" and game["answer"] is not None:
                harness.call("advance", seconds=self.pace)
                self._tap_box(harness, game["options"][game["answer"]], result)
            state = harness.call("advance", seconds=0.1)
            self._shot(harness, state, result)

    def _colours(self, harness: Harness, result: RunResult) -> None:
        state = harness.call("advance", seconds=0.0)
        while state["phase"] == "playing":
            game = state["state"]
            if game["wish"] is not None:
                harness.call("advance", seconds=self.pace)
                spot = game["swatches"][game["wish"]]
                self._tap(harness, spot["x"], spot["y"], result)
            state = harness.call("advance", seconds=0.1)
            self._shot(harness, state, result)

    @staticmethod
    def _idle(harness: Harness, result: RunResult) -> None:
        while harness.call("advance", seconds=0.5)["phase"] == "playing":
            pass


# --- the play-tester model ----------------------------------------------------------------


class TesterVerdict(BaseModel):
    won: bool = Field(description="Whether you think you won")
    fun: int = Field(ge=1, le=5, description="How fun the game felt, 1 to 5")
    problems: list[str] = Field(default_factory=list, max_length=5)
    notes: str = Field(default="", max_length=300)


class TapArgs(BaseModel):
    x: float = Field(ge=0, le=360, description="Pixels from the left of the screenshot")
    y: float = Field(ge=0, le=640, description="Pixels from the top of the screenshot")


class DragArgs(BaseModel):
    x1: float = Field(ge=0, le=360)
    y1: float = Field(ge=0, le=640)
    x2: float = Field(ge=0, le=360)
    y2: float = Field(ge=0, le=640)


class WaitArgs(BaseModel):
    seconds: float = Field(ge=0.1, le=3.0)


def tester_tools(harness: Harness, result: RunResult, pace: float) -> ToolRegistry:
    def after(action: str) -> ToolOutput:
        result.actions += 1
        state = harness.call("advance", seconds=pace)
        return ToolOutput(f"{action}; game time {state['elapsed']:.1f}s, {state['phase']}")

    def tap(args: TapArgs) -> ToolOutput:
        harness.call("tap", x=args.x, y=args.y)
        return after(f"tapped ({args.x:.0f}, {args.y:.0f})")

    def drag(args: DragArgs) -> ToolOutput:
        harness.call("drag", x1=args.x1, y1=args.y1, x2=args.x2, y2=args.y2)
        return after("dragged")

    def wait(args: WaitArgs) -> ToolOutput:
        state = harness.call("advance", seconds=args.seconds)
        return ToolOutput(f"waited; game time {state['elapsed']:.1f}s, {state['phase']}")

    return (
        ToolRegistry()
        .add(Tool("tap", "Tap the screen at a point.", TapArgs, tap))
        .add(Tool("drag", "Drag a finger from one point to another.", DragArgs, drag))
        .add(Tool("wait", "Let the game run without touching it.", WaitArgs, wait))
    )


class AgentDriver:
    name = "agent"
    PROMPT = "tester_play"

    def __init__(
        self, client: AIClient, subject: Subject, instruction: str, pace: float = DEFAULT_PACE_S
    ) -> None:
        self._client = client
        self._subject = subject
        self._instruction = instruction
        self._pace = pace

    def play(self, harness: Harness, index: int) -> RunResult:
        _begin(harness, index)
        result = RunResult(index=index, driver=self.name, won=False, seconds=0.0, actions=0)

        def observe() -> Observation:
            png = screenshot(harness)
            if result.gameplay_png is None and result.actions >= 4:
                result.gameplay_png = png
            data = f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
            return Observation("The screen (360 by 640 pixels).", Media(MediaKind.IMAGE, data))

        run = run_agent(
            self._client,
            self.PROMPT,
            {
                "instruction": as_data(self._instruction),
                "step_seconds": self._pace,
                "run": index + 1,
            },
            tester_tools(harness, result, self._pace),
            TesterVerdict,
            observe=observe,
            finished=lambda: harness.call("state")["phase"] == "ended",
            subject=self._subject,
            max_turns=MAX_TURNS,
        )
        result.driver = "+".join(sorted(run.endpoints)) or self.name
        result.verdict = run.verdict.model_dump()
        result.trace = [
            {
                "turn": s.turn,
                "tool": s.tool,
                "args": s.args,
                "result": s.result,
                "thought": s.thought,
            }
            for s in run.steps
        ]
        if not run.finished:
            harness.call("advance", seconds=31.0)  # let the hard stop end an unfinished run
        return _finish(harness, result)
