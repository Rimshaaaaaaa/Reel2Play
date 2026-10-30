"""The demo (features 41, 60, 61, 63, 65): try-it samples, live progress, the gallery, the
blind preference page, and the mock model's recorded answers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from reel2play.cli import main
from reel2play.jobs.queue import run_due
from reel2play.models import Ad, AdStatus, Preference, Video
from reel2play.routes import live
from reel2play.settings import AIMode, get_settings
from tests.helpers import ad_for, drain

PROMPTS = Path(__file__).resolve().parents[1] / "src/reel2play/ai/prompts"
FIXTURES = PROMPTS.parent / "fixtures"


def try_sample(client: TestClient, key: str) -> dict[str, object]:
    response = client.post("/api/try", json={"sample": key})
    return {"http": response.status_code, **response.json()}


def mark_published(session: Session, ad: Ad, slug: str = "AbC1234") -> None:
    session.execute(update(Ad).where(Ad.id == ad.id).values(status=AdStatus.PUBLISHED, slug=slug))
    session.commit()


# --- try-it samples -------------------------------------------------------------------------


def test_samples_are_listed_and_labelled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    samples = client.get("/api/samples").json()
    keys = [s["key"] for s in samples]
    assert keys == ["sneaker", "sneaker-urdu", "cake", "fix-loop", "blocked"]
    assert all(s["synthetic"] for s in samples)
    video = client.get(samples[0]["video_url"].removeprefix("http://testserver"))
    assert (video.status_code, video.headers["content-type"]) == (200, "video/mp4")
    assert client.get("/api/samples/nope/video").status_code == 404

    monkeypatch.setattr(get_settings(), "ai_mode", AIMode.LIVE)
    live_keys = [s["key"] for s in client.get("/api/samples").json()]
    assert live_keys == ["sneaker", "sneaker-urdu", "cake"]  # recorded-answer demos hidden
    assert try_sample(client, "fix-loop")["http"] == 404


@pytest.mark.usefixtures("stop_after_build")
def test_a_sample_is_an_ordinary_synthetic_upload(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = try_sample(client, "cake")
    assert first["http"] == 201
    assert first["is_synthetic"] is True
    video = session.get(Video, first["id"])
    assert video is not None
    assert (video.source, video.sample_key, video.cta_target) == (
        "try",
        "cake",
        "https://example.com/",
    )
    assert (video.owner_price, video.owner_offer) == ("Rs 1,800", None)
    monkeypatch.setattr(get_settings(), "max_try_running", 1)
    busy = try_sample(client, "sneaker")
    assert busy["http"] == 429
    assert "Try again in a minute" in str(busy["detail"])
    run_due("test", max_jobs=10)  # the cake game is built; the pipeline stops after build
    session.execute(update(Ad).values(status=AdStatus.PUBLISHED))
    session.commit()
    assert try_sample(client, "sneaker")["http"] == 201


@pytest.mark.parametrize(
    ("sample", "product", "language", "template"),
    [
        ("cake", "Strawberry layer cake", "en", "catch"),
        ("sneaker-urdu", "Canvas sneaker", "ur", "runner"),
    ],
)
def test_samples_go_all_the_way(
    client: TestClient,
    session: Session,
    sample: str,
    product: str,
    language: str,
    template: str,
) -> None:
    video_id = try_sample(client, sample)["id"]
    drain()
    ad = ad_for(session, video_id)  # type: ignore[arg-type]
    failed = [g["gate"] for g in (ad.report or {}).get("gates", []) if not g["passed"]]
    assert failed == []
    assert ad.status == AdStatus.PUBLISHED
    assert (ad.language, ad.template) == (language, template)
    body = client.get(f"/api/ads/{ad.id}").json()
    assert body["brief"]["product"] == product
    assert body["report"]["language"] == language
    assert body["share"]["captions"]["language"] == language
    if language == "ur":
        assert "گیم" in body["share"]["captions"]["whatsapp_status"]
        assert "گیم" in body["report"]["summary"]


# --- live progress --------------------------------------------------------------------------


def events_of(body: str) -> list[tuple[str, dict[str, object]]]:
    found = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            found.append((lines["event"], json.loads(lines["data"])))
    return found


@pytest.mark.usefixtures("stop_after_build")
def test_live_progress_streams_until_the_ad_is_finished(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video_id = try_sample(client, "sneaker")["id"]
    run_due("test", max_jobs=10)
    ad = ad_for(session, video_id)  # type: ignore[arg-type]
    mark_published(session, ad)
    with client.stream("GET", f"/api/ads/{ad.id}/stream") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    events = events_of(body)
    kinds = [kind for kind, _ in events]
    assert kinds[-2:] == ["status", "end"]
    assert kinds.count("progress") >= 8
    assert events[0][1]["action"] == "ad.created"
    assert events[-1][1] == {"status": "published"}
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/ads/{missing}/stream").status_code == 404


@pytest.mark.usefixtures("stop_after_build")
def test_a_stream_gives_up_after_a_while(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_id = try_sample(client, "sneaker")["id"]
    run_due("test", max_jobs=10)
    ad = ad_for(session, video_id)  # type: ignore[arg-type]
    ticks = iter(range(0, 10_000, 100))
    out = "".join(live.stream(ad.id, sleep=lambda _: None, clock=lambda: float(next(ticks))))
    assert ": keep-alive" in out
    assert out.endswith('event: end\ndata: {"status": "building"}\n\n')


# --- gallery and the blind preference page --------------------------------------------------


@pytest.mark.usefixtures("stop_after_build")
def test_gallery_and_blind_preference(
    client: TestClient, session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    assert client.get("/api/gallery").json() == []
    assert client.get("/api/compare").status_code == 404
    video_id = try_sample(client, "sneaker")["id"]
    run_due("test", max_jobs=10)
    ad = ad_for(session, video_id)  # type: ignore[arg-type]
    assert main(["gallery", "add", str(ad.id)]) == 1  # not published yet
    mark_published(session, ad)

    compare = client.get("/api/compare").json()  # any published ad until the gallery has some
    assert compare["ad_id"] == str(ad.id)
    assert compare["game_url"] == "http://testserver/g/AbC1234"
    assert compare["game_side"] in ("left", "right")
    assert compare["still"]["product"] == "Canvas sneaker"
    assert (
        client.get(compare["still"]["image_url"].removeprefix("http://testserver")).status_code
        == 200
    )

    assert main(["gallery", "add", str(ad.id)]) == 0
    assert main(["gallery", "list"]) == 0
    assert str(ad.id) in capsys.readouterr().out
    [shown] = client.get("/api/gallery").json()
    assert (shown["product"], shown["template"], shown["link"]) == (
        "Canvas sneaker",
        "catch",
        "http://testserver/g/AbC1234",
    )
    assert shown["stats"]["plays"] == 0

    for choice in ("game", "game", "still"):
        vote = {"ad_id": str(ad.id), "choice": choice, "game_side": "left"}
        assert client.post("/api/compare", json=vote).status_code == 204
    bad = {"ad_id": str(ad.id), "choice": "neither", "game_side": "left"}
    assert client.post("/api/compare", json=bad).status_code == 422
    assert client.get("/api/compare/results").json() == {
        "votes": 3,
        "game": 2,
        "game_share": 0.667,
    }
    assert session.scalars(select(Preference)).first() is not None
    assert main(["gallery", "remove", str(ad.id)]) == 0
    assert client.get("/api/gallery").json() == []
    session.execute(update(Ad).values(status=AdStatus.NEEDS_PERSON))
    session.commit()
    vote = {"ad_id": str(ad.id), "choice": "game", "game_side": "right"}
    assert client.post("/api/compare", json=vote).status_code == 404


# --- the mock model -------------------------------------------------------------------------


def test_every_prompt_has_recorded_answers() -> None:
    for prompt in sorted(PROMPTS.glob("*.md")):
        fixture = json.loads((FIXTURES / f"{prompt.stem}.json").read_text(encoding="utf-8"))
        assert "default" in fixture, prompt.stem
        assert "Synthetic" in fixture["_note"]
