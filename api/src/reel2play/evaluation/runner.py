"""Run the whole pipeline on every video in a manifest and record what happened.

Each video goes through the normal upload path (marked synthetic when it is), then the job
queue runs until its ad is finished. Nothing is skipped or shortened for the evaluation.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import select

from reel2play.ai import cost
from reel2play.db import session_scope
from reel2play.evaluation.manifest import EvalManifest, EvalVideo
from reel2play.intake.upload import Brief, UploadLimits, accept_upload, classify
from reel2play.jobs import handlers  # noqa: F401 - registers every job the pipeline queues
from reel2play.jobs.queue import run_due
from reel2play.media.storage import MediaStorage
from reel2play.models import Ad, AdStatus, Analysis, Fix, TestRun, Video
from reel2play.pipeline.runner import TERMINAL
from reel2play.settings import AIMode, Settings

EVAL_SOURCE = "eval"
MAX_MINUTES_PER_VIDEO = 30.0


@dataclass
class VideoResult:
    id: str
    category: str
    synthetic: bool
    ad_id: str | None = None
    status: str = "not_started"
    first_try: bool = False
    passed: bool = False
    fix_rounds: int = 0
    minutes_to_ad: float | None = None
    category_read: str | None = None
    failed_gates: list[str] = field(default_factory=list)
    cost_pkr: float = 0.0
    error: str | None = None


def start(video: EvalVideo, data: bytes, storage: MediaStorage, settings: Settings) -> uuid.UUID:
    """The video as an ordinary upload; returns its id."""
    with session_scope() as session:
        brief = Brief(
            shop_name=video.shop_name,
            language=video.language,
            whatsapp_number=video.whatsapp_number,
            shop_url=None if video.whatsapp_number else video.shop_url,
            price=video.price,
            offer=video.offer,
            rights_confirmed=True,  # the manifest records who agreed
        )
        limits = UploadLimits(settings.max_upload_bytes, settings.max_photos)
        accepted = accept_upload(
            session,
            storage,
            brief,
            classify([data], limits),
            source=EVAL_SOURCE,
            synthetic=video.synthetic,
        )
        if settings.ai_mode is AIMode.MOCK:
            accepted.sample_key = video.mock_key
        return accepted.id


def wait_for_ad(
    video_id: uuid.UUID,
    *,
    worker: str = "eval",
    clock: Callable[[], float] = time.monotonic,
    max_minutes: float = MAX_MINUTES_PER_VIDEO,
) -> uuid.UUID | None:
    """Run queued jobs until this video's ad is finished; None if it never got an ad."""
    started = clock()
    while clock() - started < max_minutes * 60:
        ran = run_due(worker, max_jobs=50, time_budget_s=60)
        with session_scope() as session:
            video = session.get(Video, video_id)
            ad = session.scalars(select(Ad).where(Ad.video_id == video_id)).first()
            if video is not None and video.status == "failed":
                return None
            if ad is not None and ad.status in TERMINAL:
                return ad.id
        if ran == 0:
            time.sleep(0.5)  # a job is waiting for its retry time
    return None


def outcome(video: EvalVideo, video_id: uuid.UUID, ad_id: uuid.UUID | None) -> VideoResult:
    result = VideoResult(id=video.id, category=video.category, synthetic=video.synthetic)
    with session_scope() as session:
        uploaded = session.get(Video, video_id)
        if ad_id is None:
            result.status = "failed"
            result.error = uploaded.error if uploaded else "the upload was lost"
            return result
        ad = session.get(Ad, ad_id)
        assert ad is not None
        assert uploaded is not None
        runs = list(
            session.scalars(select(TestRun).where(TestRun.ad_id == ad.id).order_by(TestRun.round))
        )
        passing = next((r for r in runs if r.passed), None)
        brief = session.scalars(
            select(Analysis.brief).where(Analysis.ad_id == ad.id).order_by(Analysis.created_at)
        ).first()
        fixes = session.scalars(select(Fix).where(Fix.ad_id == ad.id)).all()
        result.ad_id = str(ad.id)
        result.status = ad.status
        result.passed = passing is not None
        result.first_try = bool(runs) and runs[0].passed
        result.fix_rounds = len(fixes)
        if passing is not None:
            result.minutes_to_ad = round(
                (passing.created_at - uploaded.created_at).total_seconds() / 60, 2
            )
        result.category_read = str(brief["product"]["category"]) if brief else None
        last = runs[-1] if runs else None
        result.failed_gates = [g["gate"] for g in last.gates if not g["passed"]] if last else []
        result.cost_pkr = float(cost.summarize(session, ad_id=ad.id).pkr)
        if ad.status != AdStatus.PUBLISHED:
            result.error = ad.error
    return result


def run_manifest(
    manifest: EvalManifest,
    storage: MediaStorage,
    settings: Settings,
    *,
    limit: int | None = None,
    progress: Callable[[VideoResult], None] = lambda _: None,
) -> list[VideoResult]:
    results: list[VideoResult] = []
    for video in manifest.videos[:limit]:
        video_id = start(video, manifest.path_of(video).read_bytes(), storage, settings)
        result = outcome(video, video_id, wait_for_ad(video_id))
        results.append(result)
        progress(result)
    return results
