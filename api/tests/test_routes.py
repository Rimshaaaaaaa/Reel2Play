"""Health, local media links, the cron tick and the model check."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from reel2play.deps import get_storage
from reel2play.jobs import enqueue
from reel2play.main import create_app
from reel2play.media.storage import SupabaseStorage
from reel2play.media.video import MediaToolError, run_tool
from reel2play.models import Job, JobStatus
from reel2play.settings import AppEnv, Settings, get_settings

CRON = {"X-Cron-Secret": "test-cron-secret"}


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["ok"]
    assert body["ai_mode"] == "mock"
    assert "video.prepare" in body["job_kinds"]
    assert body["attribution"] == "Built with Muse Spark Open"


def test_signed_private_media(client: TestClient) -> None:
    storage = get_storage()
    storage.put("videos/t/clip.mp4", b"clip", "video/mp4")
    url = storage.signed_url("videos/t/clip.mp4").removeprefix("http://testserver")
    assert client.get(url).content == b"clip"
    tampered = url[:-4] + "0000"
    assert client.get(tampered).status_code == 403
    assert client.get("/media/videos/t/clip.mp4?exp=1&sig=x").status_code == 403
    missing = storage.signed_url("videos/t/none.mp4").removeprefix("http://testserver")
    assert client.get(missing).status_code == 404


def test_public_media(client: TestClient) -> None:
    get_storage().put("games/g/index.html", b"<html></html>", "text/html", public=True)
    response = client.get("/public/games/g/index.html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert client.get("/public/bad%20key").status_code == 404


def test_media_routes_only_serve_local_storage(client: TestClient) -> None:
    client.app.dependency_overrides[get_storage] = lambda: SupabaseStorage(  # type: ignore[attr-defined]
        "https://p.supabase.co", "k", "a", "b", 60
    )
    assert client.get("/public/games/x.html").status_code == 404


def test_cron_needs_the_secret(client: TestClient) -> None:
    assert client.post("/internal/cron").status_code == 401
    assert client.post("/internal/cron", headers={"X-Cron-Secret": "wrong"}).status_code == 401


def test_cron_runs_due_jobs(client: TestClient, session: Session) -> None:
    enqueue(session, "video.prepare", {"video_id": "00000000-0000-0000-0000-000000000000"})
    session.commit()
    assert client.post("/internal/cron", headers=CRON).json() == {"recovered": 0, "ran": 1}
    session.expire_all()
    assert session.get(Job, 1).status == JobStatus.DONE  # type: ignore[union-attr]


def test_model_check_with_mock(client: TestClient) -> None:
    results = client.post("/internal/model-check", headers=CRON).json()
    assert {r["role"] for r in results} == {"director", "critic", "tester", "captions"}
    assert all(r["ok"] and r["endpoint"] == "mock" and r["answer"] == "ready" for r in results)


def test_model_check_reports_missing_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from reel2play.ai.client import build_ai, get_ai

    settings = Settings(ai_mode="live", app_env=AppEnv.TEST)  # type: ignore[arg-type]
    app = create_app(settings)
    app.dependency_overrides[get_ai] = lambda: build_ai(settings)
    with TestClient(app) as live_client:
        results = live_client.post("/internal/model-check", headers=CRON).json()
    assert not any(r["ok"] for r in results)
    assert "no endpoint is configured" in results[0]["error"]


def test_run_tool_errors() -> None:
    with pytest.raises(MediaToolError, match="not installed"):
        run_tool(["/nonexistent/ffmpeg"])
    with pytest.raises(MediaToolError, match="failed"):
        run_tool(["ffprobe", "-v", "error", "/nonexistent.mp4"])
    with pytest.raises(MediaToolError, match="timed out"):
        run_tool(["sleep", "2"], timeout_s=1)


@pytest.fixture
def worker_app() -> Iterator[TestClient]:
    settings = get_settings().model_copy(
        update={"app_env": AppEnv.LOCAL, "worker_enabled": True, "worker_poll_seconds": 0.05}
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_worker_starts_with_the_app(worker_app: TestClient) -> None:
    assert worker_app.get("/health").status_code == 200


def test_cli_model_check(capsys: pytest.CaptureFixture[str]) -> None:
    from reel2play.cli import main

    assert main(["model-check"]) == 0
    assert "director  ok  mock (mock)" in capsys.readouterr().out


def test_cli_model_check_fails_without_keys(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from reel2play.cli import main
    from reel2play.settings import AIMode

    monkeypatch.setattr(get_settings(), "ai_mode", AIMode.LIVE)
    assert main(["model-check"]) == 1
    assert "NO" in capsys.readouterr().out
