"""The multi-agent pipeline (feature 50): one job per step, shared state in the database.

Each step reads the ad's state, does its work, writes its results, and names the next
step. Every start, result and failure goes to the audit log for the ad; the try-it page
streams those entries as live progress, and the why panel shows them afterwards.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.ai import AIClient, Subject, get_ai
from reel2play.jobs import enqueue, registry
from reel2play.jobs.queue import PermanentJobError
from reel2play.media.storage import MediaStorage, build_storage
from reel2play.models import Ad, AdStatus, Shop, Video
from reel2play.settings import Settings, get_settings

STEP_JOB = "pipeline.step"
# Queued once when an ad reaches a final status, so channels (WhatsApp) can tell the shop.
FINISHED_JOB = "ad.finished"
TERMINAL = {
    AdStatus.PUBLISHED,
    AdStatus.NEEDS_PERSON,
    AdStatus.BLOCKED,
    AdStatus.FAILED,
    AdStatus.READY,  # feature 44: an easier version waiting for the owner
    AdStatus.REPLACED,
}


class StepFailedError(PermanentJobError):
    """A step cannot succeed for this ad; the message is shown to the shop."""


@dataclass
class StepContext:
    """Shared state for one step: the ad, its video and shop, and the services it may use."""

    session: Session
    ad: Ad
    video: Video
    shop: Shop
    storage: MediaStorage
    ai: AIClient
    settings: Settings

    @property
    def subject(self) -> Subject:
        return Subject(
            ad_id=self.ad.id,
            video_id=self.video.id,
            fixture_key=self.video.sample_key or "default",
        )

    def say(self, actor: str, action: str, message: str, **data: Any) -> None:
        """Record a step event; ``message`` is the plain-words line shown on the page."""
        audit.record(
            self.session,
            actor=actor,
            action=action,
            subject_type="ad",
            subject_id=self.ad.id,
            data={"message": message, **data},
        )


StepFn = Callable[[StepContext], str | None]


@dataclass(frozen=True)
class Step:
    name: str
    status: AdStatus
    actor: str
    label: str
    run: StepFn


@dataclass
class Pipeline:
    """The ordered steps. A step may return another step's name to jump (the fix loop)."""

    order: list[str] = field(default_factory=list)
    steps: dict[str, Step] = field(default_factory=dict)

    def add(
        self, name: str, status: AdStatus, actor: str, label: str
    ) -> Callable[[StepFn], StepFn]:
        def decorator(run: StepFn) -> StepFn:
            self.steps[name] = Step(name, status, actor, label, run)
            return run

        return decorator

    def set_order(self, names: list[str]) -> None:
        """The pipeline's flow, declared once in reel2play/pipeline/__init__.py."""
        missing = [name for name in names if name not in self.steps]
        if missing:
            raise ValueError(f"pipeline steps not registered: {missing}")
        self.order = list(names)

    def after(self, name: str) -> str | None:
        index = self.order.index(name)
        return self.order[index + 1] if index + 1 < len(self.order) else None


PIPELINE = Pipeline()


@dataclass
class Services:
    """Factories for the step context; tests swap these for fakes."""

    storage: Callable[[], MediaStorage] = field(
        default_factory=lambda: lambda: build_storage(get_settings())
    )
    ai: Callable[[], AIClient] = field(default_factory=lambda: get_ai)


SERVICES = Services()


def start_pipeline(session: Session, video: Video) -> Ad:
    """Create the ad for a prepared upload and queue its first step."""
    ad = Ad(shop_id=video.shop_id, video_id=video.id, is_synthetic=video.is_synthetic)
    session.add(ad)
    session.flush()
    audit.record(
        session,
        actor="system",
        action="ad.created",
        subject_type="ad",
        subject_id=ad.id,
        data={"message": "Video received; the director starts next.", "video_id": str(video.id)},
    )
    enqueue(session, STEP_JOB, {"ad_id": str(ad.id), "step": PIPELINE.order[0]})
    return ad


def _context(session: Session, ad: Ad) -> StepContext:
    video = session.get(Video, ad.video_id)
    shop = session.get(Shop, ad.shop_id)
    if video is None or shop is None:  # pragma: no cover - cascades make this impossible
        raise StepFailedError("the ad's video or shop is missing")
    return StepContext(
        session=session,
        ad=ad,
        video=video,
        shop=shop,
        storage=SERVICES.storage(),
        ai=SERVICES.ai(),
        settings=get_settings(),
    )


def _give_up(session: Session, payload: dict[str, Any], error: str) -> None:
    ad = session.get(Ad, uuid.UUID(payload["ad_id"]))
    if ad is None or ad.status in TERMINAL:
        return
    ad.status = AdStatus.FAILED
    ad.error = error.split(": ", 1)[-1]
    audit.record(
        session,
        actor="system",
        action="ad.failed",
        subject_type="ad",
        subject_id=ad.id,
        data={"message": f"Stopped at {payload['step']}: {ad.error}", "step": payload["step"]},
    )
    enqueue(session, FINISHED_JOB, {"ad_id": str(ad.id)})


@registry.register(STEP_JOB, on_give_up=_give_up)
def handle_step(session: Session, payload: dict[str, Any]) -> None:
    ad = session.get(Ad, uuid.UUID(payload["ad_id"]))
    if ad is None or ad.status in TERMINAL:
        return
    step = PIPELINE.steps[payload["step"]]
    ctx = _context(session, ad)
    ad.status = step.status
    ad.step = step.name
    ctx.say(step.actor, f"{step.name}.started", step.label, step=step.name)
    session.flush()
    jump = step.run(ctx)
    if ad.status in TERMINAL:
        enqueue(session, FINISHED_JOB, {"ad_id": str(ad.id)})
        return
    following = jump or PIPELINE.after(step.name)
    if following is None:
        ctx.say("system", "pipeline.stopped", "All steps built so far are done.", step=step.name)
        return
    enqueue(session, STEP_JOB, {"ad_id": str(ad.id), "step": following})
