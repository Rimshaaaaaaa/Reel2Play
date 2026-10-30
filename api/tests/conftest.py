"""Test setup: a real PostgreSQL database, local media in a temp folder, the mock model."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

_MEDIA_DIR = Path(tempfile.mkdtemp(prefix="r2p-media-"))
os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": os.environ.get(
            "TEST_DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:5432/reel2play_test"
        ),
        "LOCAL_MEDIA_DIR": str(_MEDIA_DIR),
        "STORAGE_BACKEND": "local",
        "AI_MODE": "mock",
        "WORKER_ENABLED": "false",
        "SECRET_KEY": "test-secret",
        "CRON_SECRET": "test-cron-secret",
        "API_BASE_URL": "http://testserver",
        # Blank keys here win over any real values in a local .env file.
        "BASETEN_API_KEY": "",
        "FIREWORKS_API_KEY": "",
        "GLIMMER_BASE_URL": "",
        "GLIMMER_API_KEY": "",
        "SUPABASE_URL": "",
        "SUPABASE_SERVICE_KEY": "",
        "SAM_URL": "",
        "MODAL_PROXY_TOKEN": "",
        "MODAL_TOKEN_ID": "",
        "MODAL_TOKEN_SECRET": "",
        "WHATSAPP_TOKEN": "",
        "WHATSAPP_PHONE_NUMBER_ID": "",
        "WHATSAPP_APP_SECRET": "",
        "WHATSAPP_VERIFY_TOKEN": "",
        "SHARE_BASE_URL": "",
        # Smaller Reel frames keep the suite quick; production records at 20 fps, 2x.
        "REEL_FPS": "10",
        "REEL_SCALE": "1",
    }
)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from reel2play.db import Base, get_engine, get_session_factory  # noqa: E402
from reel2play.settings import get_settings  # noqa: E402

API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    config = Config(str(API_DIR / "alembic.ini"))
    command.upgrade(config, "head")
    yield
    shutil.rmtree(_MEDIA_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def session() -> Iterator[Session]:
    db = get_session_factory()()
    try:
        yield db
        db.commit()
    finally:
        db.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    from reel2play.main import create_app

    with TestClient(create_app(get_settings())) as test_client:
        yield test_client


@pytest.fixture
def media_dir() -> Path:
    return _MEDIA_DIR


def _ffmpeg(args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args.split()], check=True)  # noqa: S603, S607


X264 = "-c:v libx264 -preset ultrafast -pix_fmt yuv420p"


@pytest.fixture(scope="session")
def sample_media(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Small synthetic media made with ffmpeg (a test pattern and a tone, labelled synthetic)."""
    root = tmp_path_factory.mktemp("samples")
    recipes = {
        "video_with_audio": (
            "synthetic-reel.mp4",
            "-f lavfi -i testsrc=size=360x640:rate=15:duration=3 "
            f"-f lavfi -i sine=frequency=440:duration=3 {X264} -c:a aac -shortest",
        ),
        "video_silent": (
            "synthetic-silent.mp4",
            f"-f lavfi -i testsrc=size=360x640:rate=15:duration=2 {X264}",
        ),
        "video_long": (
            "synthetic-long.mp4",
            f"-f lavfi -i color=c=red:size=64x64:rate=5:duration=8 {X264}",
        ),
        "video_webm": (
            "synthetic.webm",
            "-f lavfi -i testsrc=size=160x284:rate=10:duration=1 -c:v libvpx -b:v 200k",
        ),
        "product_video": (
            "synthetic-product.mp4",
            "-f lavfi -i color=c=0xf0f0f0:size=360x640:rate=12:duration=4 "
            "-vf drawbox=x=100:y=250:w=160:h=140:color=0xc8243a:t=fill:enable='lt(t,2)',"
            "drawbox=x=0:y=0:w=iw:h=ih:color=0x30343a:t=fill:enable='gte(t,2)',"
            "drawbox=x=90:y=300:w=180:h=120:color=0x1c5bd9:t=fill:enable='gte(t,2)' "
            f"{X264}",
        ),
        "photo_jpg": ("synthetic-product.jpg", "-f lavfi -i testsrc=size=400x400 -frames:v 1"),
        "photo_png": ("synthetic-product.png", "-f lavfi -i testsrc=size=300x300 -frames:v 1"),
    }
    files: dict[str, Path] = {}
    for name, (filename, recipe) in recipes.items():
        files[name] = root / filename
        _ffmpeg(f"{recipe} {files[name]}")
    return files


@pytest.fixture
def stop_after_build(monkeypatch: pytest.MonkeyPatch) -> None:
    """End the pipeline after the build step, for tests about the earlier steps."""
    from reel2play.pipeline import PIPELINE

    monkeypatch.setattr(PIPELINE, "order", ["analyze", "cutout", "build"])
