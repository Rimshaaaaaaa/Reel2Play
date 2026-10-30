"""Can be won: the play-tester wins at least 2 of 3 runs."""

from reel2play.gates.base import Evidence, GateResult, result
from reel2play.gates.thresholds import WINS_NEEDED

NAME = "can_be_won"


def check(evidence: Evidence) -> GateResult:
    wins = sum(1 for run in evidence.runs if run.won)
    total = len(evidence.runs)
    needed = min(WINS_NEEDED, total)
    return result(
        NAME,
        total > 0 and wins >= needed,
        f"The play-tester won {wins} of {total} runs.",
        f"The play-tester won only {wins} of {total} runs; at least {needed} needed.",
        wins=wins,
        runs=total,
        drivers=sorted({r.driver for r in evidence.runs}),
    )
