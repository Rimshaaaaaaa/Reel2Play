"""The evaluation harness (feature 62): manifests, the run, and the numbers it reports."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from reel2play.cli import main
from reel2play.evaluation.manifest import load_manifest
from reel2play.evaluation.report import markdown, outcome_numbers, percent
from reel2play.evaluation.runner import VideoResult
from reel2play.models import Event, Preference

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "samples"


def write_manifest(folder: Path, videos: list[dict[str, object]]) -> Path:
    path = folder / "videos.json"
    path.write_text(json.dumps({"name": "test run", "videos": videos}), encoding="utf-8")
    return path


def video(id_: str, **changes: object) -> dict[str, object]:
    return {
        "id": id_,
        "category": "bakery_food",
        "file": str(SAMPLES / "synthetic-cake.mp4"),
        "shop_name": "Synthetic Bakes",
        "price": "Rs 1,800",
        "consent": "Synthetic video made by Reel2Play",
        "synthetic": True,
        "mock_key": "cake",
        **changes,
    }


# --- manifests ------------------------------------------------------------------------------


def test_the_ci_manifest_loads() -> None:
    manifest = load_manifest(ROOT / "eval/ci.json")
    assert [v.id for v in manifest.videos] == ["ci-sneaker", "ci-cake", "ci-fix-loop"]
    assert all(manifest.path_of(v).is_file() for v in manifest.videos)


def test_the_example_must_be_filled_in() -> None:
    with pytest.raises(ValidationError, match="fill in shop_name"):
        load_manifest(ROOT / "eval/videos.example.json")
    data = json.loads((ROOT / "eval/videos.example.json").read_text(encoding="utf-8"))
    kinds = [v["category"] for v in data["videos"]]
    assert len(kinds) == 30
    assert all(kinds.count(kind) == 5 for kind in set(kinds))
    assert len(set(kinds)) == 6


@pytest.mark.parametrize(
    ("videos", "problem"),
    [
        ([video("a"), video("a")], "unique"),
        ([video("a", category="other")], "six kinds of business"),
        ([video("a", shop_url=None)], "WhatsApp number or a shop link"),
        ([video("a", consent="")], "at least 3 characters"),
    ],
)
def test_bad_manifests_are_refused(
    tmp_path: Path, videos: list[dict[str, object]], problem: str
) -> None:
    with pytest.raises(ValidationError, match=problem):
        load_manifest(write_manifest(tmp_path, videos))


def test_missing_videos_are_named(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=r"nowhere\.mp4"):
        load_manifest(write_manifest(tmp_path, [video("a", file="nowhere.mp4")]))


# --- numbers --------------------------------------------------------------------------------


def result(id_: str, category: str, **changes: object) -> VideoResult:
    return VideoResult(id=id_, category=category, synthetic=False, **changes)  # type: ignore[arg-type]


def test_outcome_numbers() -> None:
    results = [
        result("a", "shoes", first_try=True, passed=True, minutes_to_ad=2.0, category_read="shoes"),
        result("b", "shoes", passed=True, fix_rounds=2, minutes_to_ad=6.0, category_read="other"),
        result("c", "cosmetics", status="needs_person", fix_rounds=3, failed_gates=["size"]),
        result("d", "cosmetics", status="failed", error="no frames"),
    ]
    numbers = outcome_numbers(results)
    assert numbers == {
        "videos": 4,
        "first_try_success": 0.25,
        "success_after_fixes": 0.5,
        "median_minutes_to_ad": 4.0,
        "category_read_correctly": 0.5,
        "cost_pkr": 0.0,
    }
    assert outcome_numbers([])["first_try_success"] is None
    assert percent(None) == "not yet"
    assert percent(0.667) == "67%"


# --- a real run, on the mock model ----------------------------------------------------------


def test_a_run_reports_every_measure(
    client: TestClient, session: Session, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 200)  # looks like MP4, is not
    manifest = write_manifest(
        tmp_path,
        [
            video("cake"),
            video("beer", category="shoes", mock_key="blocked_words"),
            video("broken", file=str(broken), category="clothing"),
        ],
    )
    out = tmp_path / "results"
    assert main(["eval", "run", str(manifest), "--out", str(out), "--gallery"]) == 0
    printed = capsys.readouterr().out
    summary = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert summary["videos"][0]["first_try"], summary["videos"][0]
    assert "Evaluating 3 videos (test run)" in printed
    assert "First try 33%, after fixes 33%" in printed

    assert summary["mode"] == "mock"
    assert summary["synthetic_videos"] == 3
    overall = summary["overall"]
    assert (overall["videos"], overall["first_try_success"], overall["success_after_fixes"]) == (
        3,
        0.333,
        0.333,
    )
    assert 0 < overall["median_minutes_to_ad"] < 5
    cake, beer, bad = summary["videos"]
    assert (cake["status"], cake["first_try"], cake["category_read"]) == (
        "published",
        True,
        "bakery_food",
    )
    assert (beer["status"], beer["passed"]) == ("blocked", False)
    assert (bad["status"], bad["ad_id"]) == ("failed", None)
    assert bad["error"]
    assert set(summary["by_category"]) == {"bakery_food", "shoes", "clothing"}
    assert client.get("/api/gallery").json()[0]["id"] == cake["ad_id"]

    text = (out / "report.md").read_text(encoding="utf-8")
    assert "| First-try success | 33% |" in text
    assert "| Blind preference for the game (0 votes) | not yet |" in text
    assert "| cake (synthetic) | bakery food | published | 0 |" in text
    assert text.rstrip().endswith("Built with Muse Spark Open")

    # Visitors play and vote after the run; the report picks that up.
    session.add_all(
        [
            Event(ad_id=cake["ad_id"], kind="play"),
            Event(ad_id=cake["ad_id"], kind="play"),
            Event(ad_id=cake["ad_id"], kind="finish", seconds=18.0, won=True),
            Preference(ad_id=cake["ad_id"], choice="game", game_side="left"),
        ]
    )
    session.commit()
    assert main(["eval", "report", str(out / "results.json")]) == 0
    refreshed = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert refreshed["visitors"] == {
        "plays": 2,
        "completion": 0.5,
        "preference_votes": 1,
        "preferred_game": 1.0,
    }
    assert refreshed["run_at"] == summary["run_at"]
    assert "| Completion on hosted pages (2 plays) | 50% |" in markdown(refreshed)
