"""Prepare an upload: read its length and size, mute it, and keep the speech for the director.

The muted copy is the only version later steps use; the extracted audio is read by the
director for spoken offers (feature 8) and is never put into any game or Reel. The owner's
voice note (feature 10) is turned into the same small speech file, at most a minute long;
a voice note that cannot be read is left out, and the video still goes ahead.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.jobs import registry
from reel2play.media.storage import MediaStorage, build_storage
from reel2play.media.video import MediaToolError, extract_audio, probe, strip_audio
from reel2play.models import Video, VideoKind, VideoStatus
from reel2play.pipeline.runner import start_pipeline
from reel2play.settings import get_settings


class VideoTooLongError(ValueError):
    pass


def _fail(session: Session, video: Video, reason: str) -> None:
    video.status = VideoStatus.FAILED
    video.error = reason
    audit.record(
        session,
        actor="system",
        action="video.rejected",
        subject_type="video",
        subject_id=video.id,
        data={"reason": reason},
    )


VOICE_MAX_SECONDS = 60


def prepare_voice(session: Session, storage: MediaStorage, video: Video) -> None:
    """Keep up to a minute of the owner's voice note as mono speech for the director."""
    assert video.voice_original_key is not None
    reason: str | None = None
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / Path(video.voice_original_key).name
        source.write_bytes(storage.get(video.voice_original_key))
        try:
            info = probe(source)
            if not info.has_audio:
                reason = "the voice note has no sound"
            else:
                speech = Path(tmp) / "voice.mp3"
                extract_audio(source, speech, max_seconds=VOICE_MAX_SECONDS)
                video.voice_key = f"videos/{video.id}/voice.mp3"
                video.voice_seconds = round(probe(speech).duration_s, 1)
                storage.put(video.voice_key, speech.read_bytes(), "audio/mpeg")
        except MediaToolError:
            reason = "the voice note could not be read"
    if reason:
        audit.record(
            session,
            actor="system",
            action="voice.skipped",
            subject_type="video",
            subject_id=video.id,
            data={"reason": reason},
        )


def prepare_video(session: Session, storage: MediaStorage, video: Video, max_seconds: int) -> None:
    if video.kind == VideoKind.PHOTOS:
        _prepare_photos(storage, video)
    else:
        _prepare_video_file(storage, video, max_seconds)
    if video.voice_original_key:
        prepare_voice(session, storage, video)
    video.status = VideoStatus.READY
    video.error = None
    audit.record(
        session,
        actor="system",
        action="video.prepared",
        subject_type="video",
        subject_id=video.id,
        data={
            "duration_s": video.duration_s,
            "audio_removed": video.audio_removed,
            "speech_kept_for_reading": video.audio_key is not None,
            "voice_note_seconds": video.voice_seconds,
        },
    )


def _prepare_photos(storage: MediaStorage, video: Video) -> None:
    first = video.photo_keys[0]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / Path(first).name
        path.write_bytes(storage.get(first))
        info = probe(path)
    video.width, video.height = info.width, info.height
    video.audio_removed = True


def _prepare_video_file(storage: MediaStorage, video: Video, max_seconds: int) -> None:
    assert video.original_key is not None
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / Path(video.original_key).name
        source.write_bytes(storage.get(video.original_key))
        info = probe(source)
        if not info.has_video:
            raise MediaToolError("the file has no video track")
        if info.duration_s > max_seconds:
            raise VideoTooLongError(
                f"the video is {info.duration_s:.0f}s; the limit is {max_seconds}s"
            )
        muted = Path(tmp) / "muted.mp4"
        strip_audio(source, muted)
        muted_key = f"videos/{video.id}/muted.mp4"
        storage.put(muted_key, muted.read_bytes(), "video/mp4")
        if info.has_audio:
            speech = Path(tmp) / "speech.mp3"
            extract_audio(source, speech)
            video.audio_key = f"videos/{video.id}/speech.mp3"
            storage.put(video.audio_key, speech.read_bytes(), "audio/mpeg")
    video.muted_key = muted_key
    video.duration_s = info.duration_s
    video.width, video.height = info.width, info.height
    video.audio_removed = True


@registry.register("video.prepare")
def handle_prepare(session: Session, payload: dict[str, Any]) -> None:
    video = session.get(Video, uuid.UUID(payload["video_id"]))
    if video is None or video.status == VideoStatus.READY:
        return
    settings = get_settings()
    try:
        prepare_video(session, build_storage(settings), video, settings.max_video_seconds)
    except (MediaToolError, VideoTooLongError) as exc:
        _fail(session, video, str(exc))
        return
    start_pipeline(session, video)
