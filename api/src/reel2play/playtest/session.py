"""Where the harness runs: a Modal Sandbox with no network (production), or a local
subprocess (development, CI and tests). Both speak the same JSON-lines protocol.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Protocol

from reel2play.jobs.queue import PermanentJobError
from reel2play.settings import AppEnv, Settings

HARNESS = Path(__file__).with_name("harness.py")
REPLY_TIMEOUT_S = 90.0
PLAYWRIGHT_IMAGE = "mcr.microsoft.com/playwright/python:v1.63.0-noble"


class HarnessError(RuntimeError):
    pass


class Harness(Protocol):
    def call(self, cmd: str, **args: Any) -> dict[str, Any]: ...

    def close(self) -> None: ...


class LineChannel:
    """Send JSON lines to a process and read its JSON replies, with a timeout."""

    def __init__(self, lines: Iterator[str], write: Any, timeout: float) -> None:
        self._replies: queue.Queue[str | None] = queue.Queue()
        self._write = write
        self._timeout = timeout

        def pump() -> None:
            for line in lines:
                self._replies.put(line)
            self._replies.put(None)

        threading.Thread(target=pump, daemon=True).start()

    def receive(self) -> dict[str, Any]:
        try:
            line = self._replies.get(timeout=self._timeout)
        except queue.Empty as exc:
            wait = f"{self._timeout:.0f}s"
            raise HarnessError(f"the play-test harness did not answer in {wait}") from exc
        if line is None:
            raise HarnessError("the play-test harness stopped")
        reply: dict[str, Any] = json.loads(line)
        return reply

    def call(self, cmd: str, **args: Any) -> dict[str, Any]:
        self._write(json.dumps({"cmd": cmd, **args}) + "\n")
        reply = self.receive()
        if not reply.get("ok", False):
            raise HarnessError(f"{cmd}: {reply.get('error', 'failed')}")
        return reply


class LocalHarness:
    """The harness as a local subprocess (never used in production)."""

    def __init__(self, timeout: float = REPLY_TIMEOUT_S) -> None:
        self._process = subprocess.Popen(  # noqa: S603 - our own script, fixed arguments
            [sys.executable, str(HARNESS)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        stdin = self._process.stdin

        def write(text: str) -> None:
            stdin.write(text)
            stdin.flush()

        self._channel = LineChannel(iter(self._process.stdout), write, timeout)
        self._channel.receive()  # {"ready": true}

    def call(self, cmd: str, **args: Any) -> dict[str, Any]:
        return self._channel.call(cmd, **args)

    def close(self) -> None:
        with suppress(HarnessError):
            self._channel.call("quit")
        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=10)


class ModalHarness:
    """The harness inside a Modal Sandbox with networking blocked (feature 57)."""

    def __init__(self, settings: Settings, timeout: float = REPLY_TIMEOUT_S) -> None:
        import modal

        # The Modal client reads its token from the environment.
        os.environ.setdefault("MODAL_TOKEN_ID", settings.modal_token_id.get_secret_value())
        os.environ.setdefault("MODAL_TOKEN_SECRET", settings.modal_token_secret.get_secret_value())
        app = modal.App.lookup(settings.playtest_app, create_if_missing=True)
        image = modal.Image.from_registry(PLAYWRIGHT_IMAGE).add_local_file(
            str(HARNESS), "/harness/harness.py"
        )
        self._sandbox = modal.Sandbox.create(
            app=app, image=image, block_network=True, timeout=15 * 60, cpu=2.0, memory=2048
        )
        self._process = self._sandbox.exec("python", "/harness/harness.py", bufsize=1)
        stdin = self._process.stdin

        def write(text: str) -> None:
            stdin.write(text)
            stdin.drain()

        self._channel = LineChannel(iter(self._process.stdout), write, timeout)
        self._channel.receive()

    def call(self, cmd: str, **args: Any) -> dict[str, Any]:
        return self._channel.call(cmd, **args)

    def close(self) -> None:
        self._sandbox.terminate()


class SandboxUnavailableError(HarnessError, PermanentJobError):
    """Retrying cannot help: production has no Modal Sandbox configured."""


def modal_configured(settings: Settings) -> bool:
    return bool(
        settings.modal_token_id.get_secret_value()
        and settings.modal_token_secret.get_secret_value()
    )


def open_harness(settings: Settings) -> Harness:
    if modal_configured(settings):
        return ModalHarness(settings)
    if settings.app_env is AppEnv.PRODUCTION:
        raise SandboxUnavailableError(
            "games are only played in a Modal Sandbox in production; set MODAL_TOKEN_ID and "
            "MODAL_TOKEN_SECRET"
        )
    return LocalHarness()


@contextmanager
def harness_session(settings: Settings) -> Iterator[Harness]:
    harness = open_harness(settings)
    try:
        yield harness
    finally:
        harness.close()
