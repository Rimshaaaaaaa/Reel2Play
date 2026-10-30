"""Loads fast: the first frame within 2 seconds on a simulated mid-range phone."""

from reel2play.gates.base import Evidence, GateResult, result
from reel2play.gates.thresholds import FIRST_FRAME_MS

NAME = "loads_fast"


def check(evidence: Evidence) -> GateResult:
    ms = evidence.screens["phone"].first_frame_ms
    return result(
        NAME,
        ms <= FIRST_FRAME_MS,
        f"The first frame showed in {ms} ms on a slowed-down phone.",
        f"The first frame took {ms} ms; the limit is {FIRST_FRAME_MS} ms.",
        first_frame_ms=ms,
        limit_ms=FIRST_FRAME_MS,
    )
