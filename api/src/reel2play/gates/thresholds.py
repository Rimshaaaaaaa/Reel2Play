"""Gate thresholds. Our own targets, except the Meta export limits, which are Meta's."""

FIRST_FRAME_MS = 2000
HOSTED_MAX_BYTES = 2 * 1024 * 1024
META_HTML_MAX_BYTES = 2 * 1024 * 1024
META_ZIP_MAX_BYTES = 5 * 1024 * 1024
META_ZIP_MAX_FILES = 100
WINS_NEEDED = 2
FINISH_MIN_S = 15.0
FINISH_MAX_S = 30.0
MIN_CONTRAST = 4.5
SCREENS = {
    "phone": (360, 640),
    "tablet": (768, 1024),
    "square": (540, 540),
    "landscape": (960, 540),
}
# Square and landscape pages (feature 18): the same game beside a panel with the offer.
SHAPED = ("square", "landscape")
