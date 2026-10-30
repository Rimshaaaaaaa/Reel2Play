"""Size: the hosted page within 2 MB (the Meta export is checked when it is packaged)."""

from reel2play.gates.base import Evidence, GateResult, result
from reel2play.gates.thresholds import HOSTED_MAX_BYTES

NAME = "size"


def check(evidence: Evidence) -> GateResult:
    size = evidence.size_bytes
    kb = size / 1024
    return result(
        NAME,
        size <= HOSTED_MAX_BYTES,
        f"The whole game is one {kb:.0f} KB file.",
        f"The game is {kb:.0f} KB; the limit is 2 MB.",
        size_bytes=size,
        limit_bytes=HOSTED_MAX_BYTES,
    )
