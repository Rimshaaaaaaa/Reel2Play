"""The JSON-action agent loop that the play-tester runs on."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from reel2play.ai.agent import Observation, run_agent, tools_instruction, trim_images
from reel2play.ai.jsonout import JSONOutputError
from reel2play.ai.messages import ChatResponse, Media, MediaKind, user
from reel2play.ai.tools import Tool, ToolOutput, ToolRegistry
from tests.helpers import Scripted, make_client


class Tap(BaseModel):
    x: int
    y: int


class Verdict(BaseModel):
    won: bool


SHOT = Media(MediaKind.IMAGE, "data:image/png;base64,AA")


class Game:
    """A pretend game that ends after a number of taps."""

    def __init__(self, taps_to_end: int) -> None:
        self.taps: list[tuple[int, int]] = []
        self.taps_to_end = taps_to_end

    def registry(self) -> ToolRegistry:
        def tap(args: Tap) -> ToolOutput:
            self.taps.append((args.x, args.y))
            return ToolOutput("tapped")

        def crash(_: Tap) -> ToolOutput:
            raise RuntimeError("canvas gone")

        return (
            ToolRegistry()
            .add(Tool("tap", "Tap the screen", Tap, tap))
            .add(Tool("crash", "Always fails", Tap, crash))
        )

    def finished(self) -> bool:
        return len(self.taps) >= self.taps_to_end

    def observe(self) -> Observation:
        return Observation(f"{len(self.taps)} taps so far", SHOT)


def turn(*actions: tuple[str, dict[str, object]], thought: str = "go") -> ChatResponse:
    import json

    body = {"thought": thought, "actions": [{"tool": t, "args": a} for t, a in actions]}
    return ChatResponse(text=json.dumps(body))


def test_agent_acts_until_the_game_ends_then_judges() -> None:
    game = Game(taps_to_end=3)
    provider = Scripted(
        "modal_glimmer",
        [
            turn(("tap", {"x": 1, "y": 2}), ("crash", {"x": 0, "y": 0}), ("nope", {})),
            ChatResponse(text="not json at all"),
            turn(("tap", {"x": "bad", "y": 0}), ("tap", {"x": 3, "y": 4})),
            turn(("tap", {"x": 5, "y": 6}), ("tap", {"x": 7, "y": 8})),
            ChatResponse(text='{"won": true}'),
        ],
    )
    run = run_agent(
        make_client(provider),
        "demo",
        {"shop": "S", "product": "P"},
        game.registry(),
        Verdict,
        observe=game.observe,
        finished=game.finished,
    )
    assert run.verdict.won
    assert run.finished
    assert run.endpoints == {"modal_glimmer"}
    assert game.taps == [(1, 2), (3, 4), (5, 6)]  # stops acting once the game ends
    results = [step.result for step in run.steps]
    assert "canvas gone" in results[1]
    assert "unknown tool" in results[2]
    assert "bad arguments" in results[3]
    first = provider.requests[0]
    assert "Tools:" in first.messages[0].text
    assert first.messages[-1].media == [SHOT]
    repaired = provider.requests[2].messages
    assert "could not be used" in repaired[-1].text


def test_agent_stops_at_the_turn_limit() -> None:
    game = Game(taps_to_end=99)
    provider = Scripted(
        "modal_glimmer",
        [*(turn(("tap", {"x": 1, "y": 1})) for _ in range(2)), ChatResponse(text='{"won": false}')],
    )
    run = run_agent(
        make_client(provider),
        "demo",
        {"shop": "S", "product": "P"},
        game.registry(),
        Verdict,
        observe=game.observe,
        finished=game.finished,
        max_turns=2,
    )
    assert run.turns == 2
    assert not run.finished
    assert not run.verdict.won


def test_an_unusable_verdict_raises() -> None:
    game = Game(taps_to_end=0)
    provider = Scripted("modal_glimmer", [ChatResponse(text="no"), ChatResponse(text="still no")])
    with pytest.raises(JSONOutputError):
        run_agent(
            make_client(provider),
            "demo",
            {"shop": "S", "product": "P"},
            game.registry(),
            Verdict,
            observe=game.observe,
            finished=game.finished,
        )


def test_trim_images_keeps_latest() -> None:
    messages = [user(f"shot {n}", [SHOT]) for n in range(5)]
    trimmed = trim_images(messages, keep=2)
    assert [bool(m.media) for m in trimmed] == [False, False, False, True, True]
    assert trimmed[0].text == "shot 0 [earlier screenshot removed]"


def test_registry_describes_tools() -> None:
    tools = Game(1).registry()
    assert tools.names() == ["crash", "tap"]
    assert '"x"' in tools_instruction(tools)
    with pytest.raises(ValueError, match="already registered"):
        tools.add(Tool("tap", "again", Tap, lambda _: ToolOutput("x")))
