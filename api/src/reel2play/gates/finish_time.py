"""Finish time: the median run lasts between 15 and 30 seconds."""

from statistics import median

from reel2play.gates.base import Evidence, GateResult, result
from reel2play.gates.thresholds import FINISH_MAX_S, FINISH_MIN_S

NAME = "finish_time"


def check(evidence: Evidence) -> GateResult:
    times = [run.seconds for run in evidence.runs]
    middle = float(median(times)) if times else 0.0
    passed = bool(times) and FINISH_MIN_S <= middle <= FINISH_MAX_S
    if middle < FINISH_MIN_S:
        problem = f"Runs were too short (median {middle:.1f} s); aim for 15 to 30 s."
    else:
        problem = f"Runs were too long (median {middle:.1f} s); aim for 15 to 30 s."
    return result(
        NAME,
        passed,
        f"A typical run lasted {middle:.1f} seconds.",
        problem,
        median_s=round(middle, 2),
        runs_s=times,
        target_s=[FINISH_MIN_S, FINISH_MAX_S],
    )
