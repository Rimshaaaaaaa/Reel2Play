"""Fix loop and the failure paths of the test step (features 25 to 30) on the mock model.

The games really run: each test step opens the compiled game in the local harness
(Chromium through Playwright), plays three scripted runs and measures the end card. The
passing path, through to publishing, is in test_pipeline_publish.py.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from reel2play.builder.proposal import GameProposal
from reel2play.jobs.queue import PermanentJobError, run_due
from reel2play.models import AdStatus, Build, Fix, Video
from reel2play.pipeline.fix import describe_change, fix
from reel2play.pipeline.playtest import Shots, playtest
from reel2play.pipeline.runner import StepFailedError, _context
from reel2play.playtest.session import SandboxUnavailableError
from tests.helpers import OWNER_FIELDS as FIELDS
from tests.helpers import ad_for, drain, runs_for, trail, upload


def test_failing_game_is_fixed_three_times_then_needs_a_person(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video_id = upload(client, sample_media["product_video"], **FIELDS)
    # The "always_fails" recordings make the critic misread the price every round.
    session.execute(update(Video).where(Video.id == video_id).values(sample_key="always_fails"))
    session.commit()
    drain()
    ad = ad_for(session, video_id)
    assert ad.status == AdStatus.NEEDS_PERSON

    runs = runs_for(session, ad)
    assert [r.round for r in runs] == [1, 2, 3, 4]
    assert not any(r.passed for r in runs)
    for run in runs:
        failed = [g for g in run.gates if not g["passed"]]
        assert [g["gate"] for g in failed] == ["offer_shown"]
        assert "read the price as 'Rs 3,20'" in failed[0]["message"]

    fixes = list(session.scalars(select(Fix).where(Fix.ad_id == ad.id).order_by(Fix.round)))
    assert [f.round for f in fixes] == [1, 2, 3]
    assert all(f.failed_gates == ["offer_shown"] for f in fixes)
    assert "difficulty normal to easy" in fixes[0].change
    assert fixes[1].change == "rebuilt with the same proposal"
    builds = session.scalars(select(Build.number).where(Build.ad_id == ad.id)).all()
    assert sorted(builds) == [1, 2, 3, 4]
    assert [f.build_id for f in fixes] == [r.build_id for r in runs[1:]]

    actions = trail(session, ad)
    assert actions.count("test.failed") == 3
    assert actions.count("fix.done") == 3
    assert actions[-2:] == ["test.needs_person", "report.written"]

    report = ad.report
    assert report is not None
    assert not report["passed"]
    assert report["rounds"] == 3
    assert report["next_step"] == "Our team will look at it and send you a fixed game."
    offer = next(g for g in report["gates"] if g["gate"] == "offer_shown")
    assert not offer["passed"]
    assert offer["screenshot_key"]

    body = client.get(f"/api/ads/{ad.id}").json()
    assert body["status"] == "needs_person"
    gate = next(g for g in body["report"]["gates"] if g["gate"] == "offer_shown")
    assert gate["screenshot_url"].startswith("http://testserver/media/")


def test_steps_refuse_to_run_out_of_order(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video_id = upload(client, sample_media["product_video"], **FIELDS)
    run_due("test", max_jobs=1)  # prepares the video and creates the ad
    ctx = _context(session, ad_for(session, video_id))
    with pytest.raises(StepFailedError, match="no game to test"):
        playtest(ctx)
    with pytest.raises(StepFailedError, match="no failed test"):
        fix(ctx)
    shots = Shots(ctx, uuid.uuid4())
    assert shots.save("nothing", None) is None
    assert shots.keys == {}


def test_a_missing_sandbox_is_not_retried() -> None:
    assert issubclass(SandboxUnavailableError, PermanentJobError)


PROPOSAL = {
    "template": "catch",
    "reason": "r",
    "difficulty": "normal",
    "difficulty_overrides": {},
    "title": "Catch!",
    "instruction": "Tap.",
    "win_text": "Yay",
    "lose_text": "Aw",
    "cta_label": "Order",
    "product_label": "Sneaker",
    "offer_line": "20% off",
    "primary_color": "#c8243a",
    "accent_color": "#1c1a36",
}


@pytest.mark.parametrize(
    ("changes", "words"),
    [
        ({}, "rebuilt with the same proposal"),
        ({"template": "runner"}, "switched to the runner template"),
        ({"difficulty": "easy"}, "difficulty normal to easy"),
        ({"difficulty_overrides": {"spawn_every": 1.4}}, "tuned spawn_every"),
        ({"title": "Grab it", "cta_label": "Buy"}, "rewrote title, cta label"),
        ({"accent_color": "#000000"}, "changed the colours"),
    ],
)
def test_describe_change(changes: dict[str, object], words: str) -> None:
    after = GameProposal.model_validate({**PROPOSAL, **changes})
    assert words in describe_change(PROPOSAL, after)
