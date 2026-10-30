from __future__ import annotations

import time
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from reel2play.db import utcnow
from reel2play.jobs.queue import (
    JobRegistry,
    UnknownJobKindError,
    backoff_seconds,
    claim_next,
    enqueue,
    recover_stale,
    run_due,
    run_one,
)
from reel2play.jobs.worker import Worker
from reel2play.models import Job, JobStatus


class RecordingRegistry(JobRegistry):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[dict[str, Any]] = []
        self.register("ok")(lambda _s, payload: self.calls.append(payload))
        self.register("boom")(self._boom)

    @staticmethod
    def _boom(_: Session, __: dict[str, Any]) -> None:
        raise RuntimeError("broken on purpose")


@pytest.fixture
def jobs() -> RecordingRegistry:
    return RecordingRegistry()


def _job(session: Session, job_id: int) -> Job:
    session.expire_all()
    job = session.get(Job, job_id)
    assert job is not None
    return job


def test_successful_job_is_done(session: Session, jobs: RecordingRegistry) -> None:
    job = enqueue(session, "ok", {"x": 1})
    session.commit()
    assert run_one("t", jobs)
    assert _job(session, job.id).status == JobStatus.DONE
    assert jobs.calls == [{"x": 1}]
    assert not run_one("t", jobs)


def test_failed_job_retries_then_fails(session: Session, jobs: RecordingRegistry) -> None:
    job = enqueue(session, "boom", max_attempts=2)
    session.commit()
    assert run_one("t", jobs)
    retried = _job(session, job.id)
    assert retried.status == JobStatus.QUEUED
    assert "broken on purpose" in (retried.last_error or "")
    assert retried.run_after > utcnow()
    session.execute(update(Job).values(run_after=utcnow()))
    session.commit()
    assert run_one("t", jobs)
    assert _job(session, job.id).status == JobStatus.FAILED


def test_unknown_kind_fails_the_job(session: Session, jobs: RecordingRegistry) -> None:
    job = enqueue(session, "missing", max_attempts=1)
    session.commit()
    run_one("t", jobs)
    failed = _job(session, job.id)
    assert failed.status == JobStatus.FAILED
    assert "UnknownJobKindError" in (failed.last_error or "")


def test_future_jobs_wait(session: Session, jobs: RecordingRegistry) -> None:
    enqueue(session, "ok", run_after=utcnow() + timedelta(hours=1))
    session.commit()
    assert claim_next(session, "t") is None


def test_run_due_respects_limits(session: Session, jobs: RecordingRegistry) -> None:
    for n in range(4):
        enqueue(session, "ok", {"n": n})
    session.commit()
    assert run_due("t", max_jobs=3, jobs=jobs) == 3
    assert run_due("t", max_jobs=10, jobs=jobs) == 1
    assert run_due("t", jobs=jobs) == 0


def test_recover_stale_requeues_dead_jobs(session: Session) -> None:
    job = enqueue(session, "ok")
    session.commit()
    claimed = claim_next(session, "dead-worker")
    assert claimed is not None
    claimed.locked_at = utcnow() - timedelta(hours=2)
    session.commit()
    assert recover_stale(session, 900) == 1
    session.commit()
    assert _job(session, job.id).status == JobStatus.QUEUED


def test_registry_rejects_duplicate_kinds() -> None:
    registry = JobRegistry()

    @registry.register("a")
    def first(_: Session, __: dict[str, Any]) -> None:
        return None

    with pytest.raises(ValueError, match="registered twice"):
        registry.register("a")(lambda _s, _p: None)
    with pytest.raises(UnknownJobKindError):
        registry.get("b")
    assert registry.kinds() == ["a"]


def test_backoff_grows() -> None:
    assert [backoff_seconds(n) for n in (1, 2, 3)] == [5, 10, 20]


def test_worker_thread_drains_queue(session: Session, jobs: RecordingRegistry) -> None:
    job = enqueue(session, "ok", {"w": True})
    session.commit()
    worker = Worker(poll_seconds=0.05, jobs=jobs)
    worker.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _job(session, job.id).status != JobStatus.DONE:
        time.sleep(0.05)
    worker.stop()
    assert _job(session, job.id).status == JobStatus.DONE
    assert not worker.running
