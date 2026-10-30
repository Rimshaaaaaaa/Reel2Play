"""Command line: `uv run reel2play <command>`."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from reel2play.ai.client import build_ai
from reel2play.ai.cost import MemoryRecorder
from reel2play.ai.health import check_roles
from reel2play.db import session_scope
from reel2play.evaluation import report
from reel2play.evaluation.manifest import load_manifest
from reel2play.evaluation.runner import VideoResult, run_manifest
from reel2play.media.storage import build_storage
from reel2play.models import Ad, AdStatus
from reel2play.settings import REPO_ROOT, get_settings


def model_check() -> int:
    """Print which endpoint answers for each role; fail when the director has none."""
    results = check_roles(build_ai(get_settings(), recorder=MemoryRecorder()))
    for result in results:
        where = f"{result.endpoint} ({result.model})" if result.ok else result.error
        print(f"{result.role:<9} {'ok ' if result.ok else 'NO '} {where}")
    director = next(r for r in results if r.role == "director")
    return 0 if director.ok else 1


def gallery(action: str, ad_ids: list[str]) -> int:
    """Show published ads in the public gallery (feature 61), take them out, or list them."""
    with session_scope() as session:
        if action == "list":
            for shown in session.scalars(select(Ad).where(Ad.in_gallery.is_(True))):
                print(shown.id, shown.status, shown.slug)
            return 0
        for raw in ad_ids:
            ad = session.get(Ad, uuid.UUID(raw))
            if ad is None or (action == "add" and ad.status != AdStatus.PUBLISHED):
                print(f"{raw}: not a published ad")
                return 1
            ad.in_gallery = action == "add"
            print(f"{raw}: {'in' if ad.in_gallery else 'out of'} the gallery")
    return 0


def eval_run(manifest_path: Path, out: Path | None, limit: int | None, gallery_too: bool) -> int:
    """Run the evaluation (feature 62) and write results.json and report.md."""
    settings = get_settings()
    manifest = load_manifest(manifest_path)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    folder = out or REPO_ROOT / "eval" / "results" / f"{stamp}-{settings.ai_mode}"
    print(f"Evaluating {len(manifest.videos[:limit])} videos ({manifest.name})")
    results = run_manifest(
        manifest,
        build_storage(settings),
        settings,
        limit=limit,
        progress=lambda r: print(f"  {r.id:<24} {r.status:<13} fixes {r.fix_rounds}"),
    )
    with session_scope() as session:
        summary = report.summarize(session, results, mode=settings.ai_mode.value)
        if gallery_too:
            for result in results:
                if result.ad_id and result.status == AdStatus.PUBLISHED:
                    ad = session.get(Ad, uuid.UUID(result.ad_id))
                    if ad is not None:
                        ad.in_gallery = True
    data, text = report.write(summary, folder)
    overall = summary["overall"]
    print(
        f"First try {report.percent(overall['first_try_success'])}, after fixes "
        f"{report.percent(overall['success_after_fixes'])}, median "
        f"{overall['median_minutes_to_ad']} min. Written to {text}"
    )
    return 0 if data.is_file() else 1


def eval_report(results_path: Path) -> int:
    """Refresh a run's visitor numbers (preference and completion) and rewrite its report."""
    saved = json.loads(results_path.read_text(encoding="utf-8"))
    results = [VideoResult(**video) for video in saved["videos"]]
    with session_scope() as session:
        summary = report.summarize(session, results, mode=saved["mode"])
    summary["run_at"] = saved["run_at"]
    _, text = report.write(summary, results_path.parent)
    print(f"Updated {text}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reel2play")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("model-check", help="check which model answers for each role")
    shelf = commands.add_parser("gallery", help="add ads to the public gallery, or list them")
    shelf.add_argument("action", choices=["add", "remove", "list"])
    shelf.add_argument("ad_ids", nargs="*")
    evaluation = commands.add_parser("eval", help="run the evaluation, or refresh its report")
    evaluation.add_argument("action", choices=["run", "report"])
    evaluation.add_argument("path", type=Path, help="a manifest to run, or a results.json")
    evaluation.add_argument("--out", type=Path, default=None)
    evaluation.add_argument("--limit", type=int, default=None)
    evaluation.add_argument("--gallery", action="store_true", help="show passed ads publicly")
    args = parser.parse_args(argv)
    if args.command == "gallery":
        return gallery(args.action, args.ad_ids)
    if args.command == "eval":
        if args.action == "report":
            return eval_report(args.path)
        return eval_run(args.path, args.out, args.limit, args.gallery)
    return model_check()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
