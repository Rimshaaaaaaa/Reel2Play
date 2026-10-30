"""The evaluation's numbers, as the build spec defines them, written as JSON and Markdown.

- First-try success: share of videos whose first game passes every gate with no fixes.
- Success after fixes: share that passes within the fix rounds.
- Time to ad: median minutes from upload to a passed game.
- Blind preference: share of people who picked the game over the still ad.
- Completion: share of plays on the hosted pages that reach the end card.
Preference and completion come from real visitors, so they fill in after the run.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from reel2play.evaluation.manifest import BUSINESS_KINDS
from reel2play.evaluation.runner import VideoResult
from reel2play.insights import stats_for
from reel2play.models import Preference

ATTRIBUTION = "Built with Muse Spark Open"


def rate(hits: int, total: int) -> float | None:
    return round(hits / total, 3) if total else None


def outcome_numbers(results: list[VideoResult]) -> dict[str, Any]:
    times = [r.minutes_to_ad for r in results if r.minutes_to_ad is not None]
    read = [r for r in results if r.category_read is not None]
    return {
        "videos": len(results),
        "first_try_success": rate(sum(r.first_try for r in results), len(results)),
        "success_after_fixes": rate(sum(r.passed for r in results), len(results)),
        "median_minutes_to_ad": round(median(times), 2) if times else None,
        "category_read_correctly": rate(
            sum(r.category_read == r.category for r in read), len(read)
        ),
        "cost_pkr": round(sum(r.cost_pkr for r in results), 2),
    }


def visitor_numbers(session: Session, ad_ids: list[uuid.UUID]) -> dict[str, Any]:
    stats = stats_for(session, ad_ids).values()
    plays = sum(s.plays for s in stats)
    finishes = sum(s.finishes for s in stats)
    votes, game = (
        session.execute(
            select(
                func.count(Preference.id),
                func.count(Preference.id).filter(Preference.choice == "game"),
            ).where(Preference.ad_id.in_(ad_ids))
        ).one()
        if ad_ids
        else (0, 0)
    )
    return {
        "plays": plays,
        "completion": rate(finishes, plays),
        "preference_votes": int(votes),
        "preferred_game": rate(int(game), int(votes)),
    }


def summarize(session: Session, results: list[VideoResult], *, mode: str) -> dict[str, Any]:
    ad_ids = [uuid.UUID(r.ad_id) for r in results if r.ad_id]
    return {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": mode,
        "synthetic_videos": sum(r.synthetic for r in results),
        "overall": outcome_numbers(results),
        "visitors": visitor_numbers(session, ad_ids),
        "by_category": {
            kind.value: outcome_numbers([r for r in results if r.category == kind])
            for kind in BUSINESS_KINDS
            if any(r.category == kind for r in results)
        },
        "videos": [asdict(r) for r in results],
    }


def percent(value: float | None) -> str:
    return "not yet" if value is None else f"{value * 100:.0f}%"


def markdown(summary: dict[str, Any]) -> str:
    overall, visitors = summary["overall"], summary["visitors"]
    synthetic = summary["synthetic_videos"]
    lines = [
        "# Reel2Play evaluation",
        "",
        f"{overall['videos']} videos, run on {summary['run_at']} with the "
        f"{'mock (recorded answers)' if summary['mode'] == 'mock' else 'real'} models."
        + (f" {synthetic} of them are synthetic test videos." if synthetic else ""),
        "",
        "| Measure | Result |",
        "| --- | --- |",
        f"| First-try success | {percent(overall['first_try_success'])} |",
        f"| Success after fixes | {percent(overall['success_after_fixes'])} |",
        f"| Median minutes from upload to a passed game | {overall['median_minutes_to_ad']} |",
        f"| Blind preference for the game ({visitors['preference_votes']} votes) | "
        f"{percent(visitors['preferred_game'])} |",
        f"| Completion on hosted pages ({visitors['plays']} plays) | "
        f"{percent(visitors['completion'])} |",
        f"| Director read the business correctly | {percent(overall['category_read_correctly'])} |",
        f"| Model cost for the run | Rs {overall['cost_pkr']} |",
        "",
        "## By kind of business",
        "",
        "| Kind | Videos | First try | After fixes | Median minutes |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for kind, numbers in summary["by_category"].items():
        lines.append(
            f"| {kind.replace('_', ' ')} | {numbers['videos']} | "
            f"{percent(numbers['first_try_success'])} | "
            f"{percent(numbers['success_after_fixes'])} | {numbers['median_minutes_to_ad']} |"
        )
    lines += [
        "",
        "## Every video",
        "",
        "| Video | Kind | Result | Fix rounds | Minutes | Still failing |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for video in summary["videos"]:
        name = f"{video['id']} (synthetic)" if video["synthetic"] else video["id"]
        lines.append(
            f"| {name} | {video['category'].replace('_', ' ')} | {video['status']} | "
            f"{video['fix_rounds']} | {video['minutes_to_ad'] or ''} | "
            f"{', '.join(video['failed_gates']) or ''} |"
        )
    lines += ["", ATTRIBUTION, ""]
    return "\n".join(lines)


def write(summary: dict[str, Any], folder: Path) -> tuple[Path, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    data, text = folder / "results.json", folder / "report.md"
    data.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    text.write_text(markdown(summary), encoding="utf-8")
    return data, text
