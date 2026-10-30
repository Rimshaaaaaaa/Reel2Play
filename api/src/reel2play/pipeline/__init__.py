"""The agent pipeline. Importing this package registers every step and fixes their order.

Flow: analyze → cutout → build → test → publish. A failed test jumps to fix, which
rebuilds and returns to test, up to the fix-round limit; publish runs only after a pass.
An easier version of a live game (feature 44) starts at easier, then test; publish holds
it for the owner, and publishes it under the live game's link once the owner chooses it.
"""

from reel2play.pipeline import analyze, build, cutout, easier, fix, playtest, publish
from reel2play.pipeline.runner import PIPELINE, start_pipeline

STEP_MODULES = (analyze, cutout, build, playtest, fix, publish, easier)
PIPELINE.set_order(["analyze", "cutout", "build", "test", "publish"])

__all__ = ["PIPELINE", "STEP_MODULES", "start_pipeline"]
