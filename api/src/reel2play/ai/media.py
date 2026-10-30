"""Turn stored media into parts a model can read: inline data URLs or signed HTTPS links."""

from __future__ import annotations

import base64

from reel2play.ai.messages import Media, MediaKind
from reel2play.media.storage import MediaStorage
from reel2play.settings import MediaForModels, Settings

# Muse Spark Open accepts up to 100 MiB of request body; keep inline media well inside it.
MAX_INLINE_BYTES = 20 * 1024 * 1024


def media_part(
    storage: MediaStorage, settings: Settings, key: str, kind: MediaKind, content_type: str
) -> Media | None:
    """A media part for ``key``, or None when it is too large to send inline."""
    if settings.media_for_models is MediaForModels.SIGNED_URL:
        return Media(kind, storage.signed_url(key))
    data = storage.get(key)
    if len(data) > MAX_INLINE_BYTES:
        return None
    return Media(kind, f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}")
