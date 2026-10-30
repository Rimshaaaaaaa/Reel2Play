"""PostgreSQL job queue: enqueue, claim with SKIP LOCKED, retry with backoff, recover stale jobs."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from reel2play.db import session_scope, utcnow
from reel2play.models import Job, JobStatus

log = logging.getLogger(__name__)

Handler = Callable[[Session, dict[str, Any]], None]
GiveUp = Callable[[Session, dict[str, Any], str], None]
RETRY_BASE_SECONDS = 5


class UnknownJobKindError(LookupError):
    pass


class PermanentJobError(RuntimeError):
    """Raised by a handler when retrying cannot help; the job fails at once."""


class JobRegistry:
    """Maps a job kind to its handler. Handlers must be safe to run more than once.

    ``on_give_up`` runs once when a job of that kind has failed for good, so the owner of the
    work (an ad, a video) can be marked failed with the reason.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}
        self._give_up: dict[str, GiveUp] = {}

    def register(self, kind: str, on_give_up: GiveUp | None = None) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            if kind in self._handlers and self._handlers[kind] is not handler:
                raise ValueError(f"job kind {kind!r} registered twice")
            self._handlers[kind] = handler
            if on_give_up is not None:
                self._give_up[kind] = on_give_up
            return handler

        return decorator

    def get(self, kind: str) -> Handler:
        try:
            return self._handlers[kind]
        except KeyError as exc:
            raise UnknownJobKindError(kind) from exc

    def give_up(self, session: Session, kind: str, payload: dict[str, Any], error: str) -> None:
        hook = self._give_up.get(kind)
        if hook is not None:
            hook(session, payload, error)

    def kinds(self) -> list[str]:
        return sorted(self._handlers)


registry = JobRegistry()


def enqueue(
    session: Session,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    run_after: datetime | None = None,
    max_attempts: int = 3,
) -> Job:
    job = Job(
        kind=kind, payload=payload or {}, max_attempts=max_attempts, run_after=run_after or utcnow()
    )
    session.add(job)
    session.flush()
    return job


def claim_next(session: Session, worker_id: str) -> Job | None:
    stmt = (
        select(Job)
        .where(Job.status == JobStatus.QUEUED, Job.run_after <= utcnow())
        .order_by(Job.run_after, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = session.scalars(stmt).first()
    if job is None:
        return None
    job.status = JobStatus.RUNNING
    job.locked_at = utcnow()
    job.locked_by = worker_id
    job.attempts += 1
    session.flush()
    return job


def backoff_seconds(attempts: int) -> int:
    return int(RETRY_BASE_SECONDS * 2 ** max(0, attempts - 1))


def _finish(job_id: int, error: str | None, jobs: JobRegistry, permanent: bool = False) -> None:
    with session_scope() as session:
        job = session.get(Job, job_id, with_for_update=True)
        if job is None:  # pragma: no cover - deleted while running
            return
        job.locked_at = None
        job.locked_by = None
        if error is None:
            job.status = JobStatus.DONE
            job.last_error = None
            job.finished_at = utcnow()
        elif permanent or job.attempts >= job.max_attempts:
            job.status = JobStatus.FAILED
            job.last_error = error
            job.finished_at = utcnow()
            jobs.give_up(session, job.kind, dict(job.payload), error)
        else:
            job.status = JobStatus.QUEUED
            job.last_error = error
            job.run_after = utcnow() + timedelta(seconds=backoff_seconds(job.attempts))


def run_one(worker_id: str, jobs: JobRegistry = registry) -> bool:
    """Claim and run one due job. Returns False when nothing was due."""
    with session_scope() as session:
        job = claim_next(session, worker_id)
        if job is None:
            return False
        job_id, kind, payload = job.id, job.kind, dict(job.payload)
    error: str | None = None
    permanent = False
    try:
        handler = jobs.get(kind)
        with session_scope() as session:
            handler(session, payload)
    except Exception as exc:
        log.exception("job %s (%s) failed", job_id, kind)
        error = f"{type(exc).__name__}: {exc}"[:2000]
        permanent = isinstance(exc, PermanentJobError | UnknownJobKindError)
    _finish(job_id, error, jobs, permanent)
    return True


def run_due(
    worker_id: str, *, max_jobs: int = 10, time_budget_s: float = 20.0, jobs: JobRegistry = registry
) -> int:
    """Run due jobs until none are left, ``max_jobs`` ran, or the time budget is spent."""
    started = time.monotonic()
    count = 0
    while count < max_jobs and time.monotonic() - started < time_budget_s:
        if not run_one(worker_id, jobs):
            break
        count += 1
    return count


def recover_stale(session: Session, stale_after_s: int) -> int:
    """Put jobs whose worker died back in the queue."""
    cutoff = utcnow() - timedelta(seconds=stale_after_s)
    result = session.execute(
        update(Job)
        .where(Job.status == JobStatus.RUNNING, Job.locked_at < cutoff)
        .values(
            status=JobStatus.QUEUED,
            locked_at=None,
            locked_by=None,
            last_error="recovered after worker stopped",
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)
