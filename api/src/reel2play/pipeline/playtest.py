"""Test step (features 25 to 30, 57): play the game, measure it, run the 13 gates, decide.

The game runs in the harness (a Modal Sandbox with no network in production). The tester
plays three runs on a 360 x 640 phone; the end card is measured there and on a 768 x 1024
tablet; the critic (Spark Open) checks the product and the end card. Code then runs every
gate. A pass moves on; a failure goes to the fix step, up to the round limit, after which
the shop gets the report and a "needs a person" flag instead of a broken game.
"""

from __future__ import annotations

import base64
import time
import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import func, select

from reel2play.ai.media import media_part
from reel2play.ai.messages import Media, MediaKind
from reel2play.analysis import LANGUAGE_NAMES
from reel2play.builder.config import Palette
from reel2play.builder.templates import load_templates
from reel2play.gates import run_gates
from reel2play.gates.base import CriticReview, Evidence, GateResult, RunSummary, ScreenCheck
from reel2play.gates.thresholds import SCREENS, SHAPED
from reel2play.models import AdStatus, Build, TestRun
from reel2play.pipeline.report import fix_count, write_report
from reel2play.pipeline.runner import PIPELINE, StepContext, StepFailedError
from reel2play.pipeline.state import latest_brief, latest_build
from reel2play.playtest.drivers import AgentDriver, Driver, ScriptedDriver, screenshot
from reel2play.playtest.replay import Command, TracingHarness
from reel2play.playtest.session import Harness, harness_session
from reel2play.safety import as_data
from reel2play.settings import AIMode

PHONE_THROTTLE = 4.0


def choose_driver(ctx: StepContext, build: Build) -> Driver:
    pace = load_templates(ctx.settings.templates_dir)[build.template].tester_pace_seconds
    if ctx.settings.ai_mode is AIMode.MOCK:
        return ScriptedDriver(pace)
    return AgentDriver(ctx.ai, ctx.subject, str(build.config["text"]["instruction"]), pace)


class Shots:
    """Stores this test's screenshots and remembers their keys."""

    def __init__(self, ctx: StepContext, test_id: uuid.UUID) -> None:
        self._ctx = ctx
        self._base = f"ads/{ctx.ad.id}/tests/{test_id}"
        self.keys: dict[str, str] = {}

    def save(self, name: str, png: bytes | None) -> str | None:
        if png is None:
            return None
        key = f"{self._base}/{name}.png"
        self._ctx.storage.put(key, png, "image/png")
        self.keys[name] = key
        return key


def measure_screen(harness: Harness, html_b64: str, name: str, shots: Shots) -> ScreenCheck:
    """Open at one size, let the hard stop end the game untouched, and measure the end card."""
    width, height = SCREENS[name]
    layout = name if name in SHAPED else None
    opened = harness.call("open", html_b64=html_b64, width=width, height=height, layout=layout)
    harness.call("start")
    harness.call("advance", seconds=31.0)
    key = shots.save(f"{name}-timeout-end", screenshot(harness)) or ""
    return ScreenCheck(width, height, int(opened["first_frame_ms"]), harness.call("end_card"), key)


def critic_review(ctx: StepContext, shots: Shots) -> CriticReview:
    brief = latest_brief(ctx)
    images: list[Media] = []
    for key, mime in (
        (brief.key_frames[0].key, "image/jpeg"),
        (shots.keys.get("gameplay"), "image/png"),
        (shots.keys.get("phone-played-end"), "image/png"),
    ):
        part = media_part(ctx.storage, ctx.settings, key, MediaKind.IMAGE, mime) if key else None
        if part is not None:
            images.append(part)
    return ctx.ai.ask_json(
        "critic_review",
        {
            "product": as_data(brief.product.name),
            "offer": as_data(brief.offer_text),
            "price": as_data(brief.price),
            "language_name": LANGUAGE_NAMES[brief.language],
        },
        CriticReview,
        media=images,
        subject=ctx.subject,
    )


def next_test_round(ctx: StepContext) -> int:
    count = ctx.session.scalar(select(func.count(TestRun.id)).where(TestRun.ad_id == ctx.ad.id))
    return int(count or 0) + 1


@dataclass(frozen=True)
class Played:
    evidence: Evidence
    replays: list[list[Command]]  # the commands of each run, to replay it exactly


def play_and_measure(ctx: StepContext, build: Build, shots: Shots) -> Played:
    """Play the runs on a slowed-down phone, then measure the end card on both screen sizes."""
    html_b64 = base64.b64encode(ctx.storage.get(build.html_key)).decode("ascii")
    driver = choose_driver(ctx, build)
    width, height = SCREENS["phone"]
    with harness_session(ctx.settings) as harness:
        opened = harness.call(
            "open", html_b64=html_b64, width=width, height=height, throttle=PHONE_THROTTLE
        )
        shots.save("phone-intro", screenshot(harness))
        tracer = TracingHarness(harness)
        runs, replays = [], []
        for index in range(ctx.settings.tester_runs):
            runs.append(driver.play(tracer, index))
            replays.append(tracer.take())
        played = ScreenCheck(
            width,
            height,
            int(opened["first_frame_ms"]),
            harness.call("end_card"),
            shots.save("phone-played-end", screenshot(harness)) or "",
        )
        cta = harness.call("click_cta")
        screens = {
            "phone": played,
            "phone_timeout": measure_screen(harness, html_b64, "phone", shots),
            "tablet": measure_screen(harness, html_b64, "tablet", shots),
            **{shape: measure_screen(harness, html_b64, shape, shots) for shape in SHAPED},
        }
        log = harness.call("log")
    for run in runs:
        shots.save(f"run-{run.index + 1}-end", run.final_png)
        ctx.say(
            "tester",
            "test.run",
            f"Run {run.index + 1}: {'won' if run.won else 'did not win'} in "
            f"{run.seconds:.1f} s with {run.actions} actions ({run.driver}).",
            run=run.index + 1,
            won=run.won,
            seconds=run.seconds,
            driver=run.driver,
            verdict=run.verdict,
        )
    shots.save("gameplay", next((r.gameplay_png for r in runs if r.gameplay_png), None))
    evidence = Evidence(
        brief=latest_brief(ctx),
        config=build.config,
        palette=Palette.model_validate(build.config["palette"]),
        size_bytes=build.size_bytes,
        rights_confirmed=ctx.video.rights_confirmed,
        audio_removed=ctx.video.audio_removed,
        runs=[RunSummary(r.index, r.driver, r.won, r.seconds, r.actions) for r in runs],
        screens=screens,
        cta=cta,
        log=log,
        critic=critic_review(ctx, shots),
        gameplay_key=shots.keys.get("gameplay"),
    )
    return Played(evidence, replays)


def record(
    ctx: StepContext,
    build: Build,
    test_id: uuid.UUID,
    played: Played,
    results: list[GateResult],
    shots: Shots,
    started: float,
) -> TestRun:
    evidence = played.evidence
    run = TestRun(
        id=test_id,
        ad_id=ctx.ad.id,
        build_id=build.id,
        round=next_test_round(ctx),
        passed=all(r.passed for r in results),
        gates=[r.as_json() for r in results],
        runs=[asdict(r) for r in evidence.runs],
        replays=played.replays,
        screenshots=shots.keys,
        critic=evidence.critic.model_dump() if evidence.critic else None,
        duration_s=round(time.monotonic() - started, 1),
    )
    ctx.session.add(run)
    for gate in results:
        actor = "critic" if gate.gate == "looks_like_product" else "tester"
        ctx.say(
            actor,
            "gate.passed" if gate.passed else "gate.failed",
            gate.message,
            gate=gate.gate,
            measured=gate.measured,
        )
    return run


@PIPELINE.add("test", AdStatus.TESTING, "tester", "The play-tester is playing the game.")
def playtest(ctx: StepContext) -> str | None:
    build = latest_build(ctx)
    if build is None:
        raise StepFailedError("there is no game to test yet")
    started = time.monotonic()
    test_id = uuid.uuid4()
    shots = Shots(ctx, test_id)
    played = play_and_measure(ctx, build, shots)
    results = run_gates(played.evidence)
    run = record(ctx, build, test_id, played, results, shots, started)
    failed = [r.gate for r in results if not r.passed]
    if not failed:
        ctx.say("tester", "test.passed", f"All {len(results)} gates passed.", round=run.round)
        write_report(ctx, run, passed=True)
        return None
    rounds = fix_count(ctx)
    if rounds < ctx.settings.max_fix_rounds:
        ctx.say(
            "tester",
            "test.failed",
            f"{len(failed)} gate(s) failed: {', '.join(failed)}. Sending it back to the "
            f"director (fix round {rounds + 1} of {ctx.settings.max_fix_rounds}).",
            failed=failed,
        )
        return "fix"
    ctx.ad.status = AdStatus.NEEDS_PERSON
    ctx.say(
        "tester",
        "test.needs_person",
        f"Still failing after {rounds} fix rounds ({', '.join(failed)}). A person will look "
        "at it; the shop has the report.",
        failed=failed,
    )
    write_report(ctx, run, passed=False)
    return None
