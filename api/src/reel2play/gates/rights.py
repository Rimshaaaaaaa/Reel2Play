"""Rights: the owner confirmed the video is theirs, and the original audio is removed."""

from reel2play.gates.base import Evidence, GateResult, result

NAME = "rights"


def check(evidence: Evidence) -> GateResult:
    passed = evidence.rights_confirmed and evidence.audio_removed
    return result(
        NAME,
        passed,
        "You confirmed the video is yours, and its sound was removed.",
        "The video's rights were not confirmed, or its sound was not removed.",
        rights_confirmed=evidence.rights_confirmed,
        audio_removed=evidence.audio_removed,
    )
