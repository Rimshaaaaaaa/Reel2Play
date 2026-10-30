"""A passing game, end to end on the mock model: tested, reported, then published (features
25 to 35). The game really runs in Chromium; the Reel is really encoded with ffmpeg.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play.deps import get_storage
from reel2play.gates import GATES
from reel2play.jobs.queue import run_due
from reel2play.media.video import probe
from reel2play.models import (
    AdStatus,
    Build,
    Export,
    ExportKind,
    Job,
    JobStatus,
    ModelCall,
    TestRun,
)
from reel2play.pipeline.publish import publish
from reel2play.pipeline.runner import FINISHED_JOB, StepFailedError, _context
from reel2play.routes.game_page import PAGES
from tests.helpers import OWNER_FIELDS, ad_for, drain, runs_for, trail, upload

SERVER = "http://testserver"
PREVIEW_TAG = re.compile(
    r"\n<meta (?:property|name)=\"(?:og:|twitter:|description|r2p-analytics)[^>]*>"
)


def local(url: str) -> str:
    return url.removeprefix(SERVER)


def test_a_passing_game_is_tested_reported_and_published(
    client: TestClient, session: Session, sample_media: dict[str, Path], tmp_path: Path
) -> None:
    video_id = upload(client, sample_media["product_video"], **OWNER_FIELDS)
    drain()
    ad = ad_for(session, video_id)
    runs = runs_for(session, ad)
    failed = [(r.round, g["gate"], g["message"]) for r in runs for g in r.gates if not g["passed"]]
    assert failed == []
    assert ad.status == AdStatus.PUBLISHED
    assert ad.error is None
    assert ad.published_at is not None

    # --- the test step and the report
    [run] = runs
    assert run.passed
    assert [g["gate"] for g in run.gates] == [name for name, _ in GATES]
    assert len(run.runs) == 3
    assert {r["driver"] for r in run.runs} == {"scripted"}
    assert sum(r["won"] for r in run.runs) >= 2
    assert len(run.replays) == 3
    assert run.replays[0][0]["cmd"] == "start"
    assert {c["cmd"] for c in run.replays[1]} <= {"restart", "tap", "advance"}
    for name in ("phone-intro", "phone-played-end", "gameplay", "run-1-end", "tablet-timeout-end"):
        assert name in run.screenshots
    assert run.critic is not None
    report = ad.report
    assert report is not None
    assert report["passed"]
    assert report["rounds"] == 0
    assert "Shows your offer and price" in [g["label"] for g in report["gates"]]

    actions = trail(session, ad)
    assert actions.count("test.run") == 3
    assert actions.count("gate.passed") == 13
    assert actions[-9:] == [
        "test.passed",
        "report.written",
        "publish.started",
        "publish.page",
        "publish.reel",
        "publish.meta",
        "publish.poster",
        "publish.captions",
        "publish.done",
    ]
    prompts = set(session.scalars(select(ModelCall.prompt_name).where(ModelCall.ad_id == ad.id)))
    assert {"critic_review", "shop_report", "publisher_captions"} <= prompts

    # --- the published outputs
    exports = {e.kind: e for e in session.scalars(select(Export).where(Export.ad_id == ad.id))}
    assert set(exports) == set(ExportKind)
    assert {k for k, e in exports.items() if e.public} == {
        ExportKind.PREVIEW,
        ExportKind.REEL,
        ExportKind.REEL_SQUARE,
        ExportKind.REEL_WIDE,
    }
    storage = get_storage()

    reel = exports[ExportKind.REEL]
    assert reel.details["exact_replay"] is True
    assert 10 <= reel.details["seconds"] <= 15
    reel_file = tmp_path / "reel.mp4"
    reel_file.write_bytes(storage.get(reel.key, public=True))
    reel_probe = probe(reel_file)
    assert (reel_probe.width, reel_probe.height) == (720, 1280)
    assert 10 <= reel_probe.duration_s <= 15.2
    assert not reel_probe.has_audio
    # Feature 18: the same Reel inside the square and landscape pages, just as long.
    for kind, size in ((ExportKind.REEL_SQUARE, (540, 540)), (ExportKind.REEL_WIDE, (960, 540))):
        shaped = tmp_path / f"{kind}.mp4"
        shaped.write_bytes(storage.get(exports[kind].key, public=True))
        shaped_probe = probe(shaped)
        assert (shaped_probe.width, shaped_probe.height) == size  # REEL_SCALE is 1 in tests
        assert abs(shaped_probe.duration_s - reel_probe.duration_s) < 0.3
        assert not shaped_probe.has_audio
    lead_in = tmp_path / "lead-in.mp4"
    lead_in.write_bytes(storage.get(exports[ExportKind.LEAD_IN].key))
    assert 4.5 <= probe(lead_in).duration_s <= 5.2

    preview = Image.open(io.BytesIO(storage.get(exports[ExportKind.PREVIEW].key, public=True)))
    assert preview.size == (600, 600)

    meta_html = storage.get(exports[ExportKind.META_HTML].key).decode()
    assert '"platform":"meta"' in meta_html.replace(" ", "")
    assert "Built with Muse Spark Open" in meta_html
    assert exports[ExportKind.META_HTML].details["cta_calls"] == 1
    with zipfile.ZipFile(io.BytesIO(storage.get(exports[ExportKind.META_ZIP].key))) as archive:
        assert archive.namelist() == ["index.html"]
        assert archive.read("index.html").decode() == meta_html

    # Feature 36: the counter poster, one A4 page whose QR code was read back.
    poster = exports[ExportKind.POSTER]
    assert storage.get(poster.key).startswith(b"%PDF-")
    assert poster.details == {"pages": 1, "qr": f"{SERVER}/g/{ad.slug}?from=qr"}
    poster_jpg = Image.open(io.BytesIO(storage.get(exports[ExportKind.POSTER_PREVIEW].key)))
    assert poster_jpg.width == 480

    # The hosted page is the tested build plus link-preview tags, and nothing else.
    tested = storage.get(session.get(Build, run.build_id).html_key).decode()  # type: ignore[union-attr]
    hosted = storage.get(exports[ExportKind.HOSTED].key).decode()
    assert len(PREVIEW_TAG.findall(hosted)) == 8
    assert PREVIEW_TAG.sub("", hosted) == tested

    # --- captions
    captions = ad.captions
    assert captions is not None
    assert captions["written_by"] == "model"
    link = f"{SERVER}/g/{ad.slug}"
    assert captions["facebook"].endswith(link)
    assert captions["whatsapp_status"].endswith(link)
    assert captions["instagram"].endswith("#sneakers #shoeshop #playandwin #canvasshoes")

    # --- the API and the short link
    assert ad.slug is not None
    assert re.fullmatch(r"[A-Za-z0-9]{7}", ad.slug)
    PAGES.clear()
    page = client.get(f"/g/{ad.slug}")
    assert page.status_code == 200
    assert page.text == hosted
    assert page.headers["content-type"].startswith("text/html")
    assert "sandbox allow-scripts" in page.headers["content-security-policy"]
    assert page.headers["content-security-policy"].endswith("connect-src http://testserver")
    assert f"&quot;adId&quot;: &quot;{ad.id}&quot;" in page.text
    assert "&quot;coupons&quot;: &quot;http://testserver/api/coupons&quot;" in page.text
    assert page.headers["referrer-policy"] == "no-referrer"
    assert f'<meta property="og:url" content="{link}">' in page.text
    assert '<meta property="og:description" content="20% off. Rs 3,200">' in page.text
    assert client.head(f"/g/{ad.slug}").status_code == 200

    share = client.get(f"/api/ads/{ad.id}").json()["share"]
    assert share["link"] == link
    assert share["square_link"] == f"{link}?layout=square"
    assert share["landscape_link"] == f"{link}?layout=landscape"
    assert client.get(local(share["wide_reel_url"])).headers["content-type"] == "video/mp4"
    assert share["reel_seconds"] == reel.details["seconds"]
    assert client.get(local(share["reel_url"])).headers["content-type"] == "video/mp4"
    assert client.get(local(share["preview_url"])).status_code == 200
    assert [e["shape"] for e in share["embeds"]] == ["tall", "wide"]
    assert share["embeds"][0]["src"] == f"{link}?from=embed"
    assert client.get(local(share["poster_url"])).headers["content-type"] == "application/pdf"
    for name in (
        "meta_html_url",
        "meta_zip_url",
        "lead_in_url",
        "poster_url",
        "poster_preview_url",
    ):
        assert "sig=" in share[name]
        assert client.get(local(share[name])).status_code == 200
    assert share["captions"]["language"] == "en"

    # The finished ad was announced once, and a web upload needs no WhatsApp message.
    notices = session.scalars(select(Job).where(Job.kind == FINISHED_JOB)).all()
    assert [(j.payload["ad_id"], j.status) for j in notices] == [(str(ad.id), JobStatus.DONE)]


@pytest.mark.parametrize("slug", ["nope", "abcdefg", "abc/def", "a" * 40])
def test_unknown_short_links_are_not_found(client: TestClient, slug: str) -> None:
    assert client.get(f"/g/{slug}").status_code == 404


def test_only_a_tested_build_is_published(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video_id = upload(client, sample_media["product_video"], **OWNER_FIELDS)
    run_due("test", max_jobs=1)
    ad = ad_for(session, video_id)
    ctx = _context(session, ad)
    with pytest.raises(StepFailedError, match="passed every check"):
        publish(ctx)
    build = Build(
        ad_id=ad.id,
        number=1,
        template="catch",
        proposal={},
        config={},
        html_key="k",
        size_bytes=1,
        sha256="0" * 64,
    )
    session.add(build)
    session.flush()
    passed = TestRun(
        ad_id=ad.id,
        build_id=build.id,
        round=1,
        passed=True,
        gates=[],
        runs=[],
        duration_s=1.0,
    )
    session.add(passed)
    session.flush()
    with pytest.raises(StepFailedError, match="no replay"):
        publish(ctx)
    passed.passed = False
    session.flush()
    with pytest.raises(StepFailedError, match="passed every check"):
        publish(ctx)
    assert ad.captions is None
    assert ad.status != AdStatus.PUBLISHED
