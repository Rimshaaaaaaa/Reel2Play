"""In-process worker thread that drains the job queue while the API is awake."""

from __future__ import annotations

import logging
import os
import socket
import threading

from reel2play.jobs.queue import JobRegistry, registry, run_one

log = logging.getLogger(__name__)


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


class Worker:
    def __init__(self, poll_seconds: float, jobs: JobRegistry = registry) -> None:
        self._poll_seconds = poll_seconds
        self._jobs = jobs
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="reel2play-worker", daemon=True)
        self._id = worker_id()

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        self._thread.join(timeout)

    @property
    def running(self) -> bool:
        return self._thread.is_alive()

    def _loop(self) -> None:
        log.info("worker %s started", self._id)
        while not self._stop.is_set():
            try:
                did_work = run_one(self._id, self._jobs)
            except Exception:  # pragma: no cover - database hiccup; keep the loop alive
                log.exception("worker loop error")
                did_work = False
            if not did_work:
                self._stop.wait(self._poll_seconds)
        log.info("worker %s stopped", self._id)
