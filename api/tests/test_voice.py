"""Voice brief (feature 10): the owner's voice note is kept as speech for the director, and
what they said sets the offer, the audience and the occasion, under the same checks as the
video."""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.analysis import CreativeBrief, VideoAnalysis
from reel2play.intake.upload import VOICE_PROBLEM, check_voice, sniff_voice
from reel2play.jobs.queue import run_due
from reel2play.models import Analysis, Video, VideoStatus
from tests.helpers import ad_for

pytestmark = pytest.mark.usefixtures("stop_after_build")


def tone(folder: Path, seconds: float, name: str = "synthetic-voice.mp3", *extra: str) -> Path:
    """Synthetic: a plain tone standing in for a voice note."""
    target = folder / name
    subprocess.run(  # noqa: S603 - fixed arguments
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",  # noqa: S607
         "-i", f"sine=frequency=330:duration={seconds}", *extra, str(target)],
        check=True,
    )  # fmt: skip
    return target


@pytest.fixture(scope="module")
def voice_note(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tone(tmp_path_factory.mktemp("voice"), 3)


def send(
    client: TestClient, video: Path, voice: bytes | None, **fields: str
) -> tuple[int, dict[str, object]]:
    files = [("files", (video.name, video.read_bytes()))]
    if voice is not None:
        files.append(("voice_note", ("voice.mp3", voice)))
    data = {"shop_name": "Synthetic Shoes", "rights_confirmed": "true", **fields}
    response = client.post("/api/uploads", data=data, files=files)
    return response.status_code, response.json()


def made_with(
    client: TestClient,
    session: Session,
    video: Path,
    voice: bytes | None,
    key: str,
    **fields: str,
) -> Video:
    status, body = send(client, video, voice, whatsapp_number="923001234567", **fields)
    assert status == 201, body
    video_id = uuid.UUID(str(body["id"]))
    session.execute(update(Video).where(Video.id == video_id).values(sample_key=key))
    session.commit()
    run_due("test", max_jobs=20)
    found = session.get(Video, video_id)
    assert found is not None
    session.refresh(found)
    return found


def brief_of(session: Session, video: Video) -> tuple[CreativeBrief, VideoAnalysis]:
    ad = ad_for(session, video.id)
    analysis = session.scalars(select(Analysis).where(Analysis.ad_id == ad.id)).one()
    return (
        CreativeBrief.model_validate(analysis.brief),
        VideoAnalysis.model_validate(analysis.reading),
    )


def said(session: Session, video: Video, action: str) -> list[str]:
    ad = ad_for(session, video.id)
    return [
        e.data["message"] for e in audit.entries_for(session, "ad", ad.id) if e.action == action
    ]


# --- the file ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("head", "kind"),
    [
        (b"ID3\x04\x00", "mp3"),
        (b"\xff\xfb\x90\x00", "mp3"),
        (b"OggS\x00\x02", "ogg"),
        (b"RIFF\x24\x08\x00\x00WAVEfmt ", "wav"),
        (b"\x00\x00\x00\x20ftypM4A ", "m4a"),
        (b"\x1a\x45\xdf\xa3\x9f", "webm"),
        (b"%PDF-1.7", None),
        (b"", None),
    ],
)
def test_voice_notes_are_recognised_by_their_first_bytes(head: bytes, kind: str | None) -> None:
    assert sniff_voice(head) == kind


def test_voice_notes_that_cannot_be_used_are_refused(
    client: TestClient, sample_media: dict[str, Path]
) -> None:
    with pytest.raises(ValueError, match="under 10 MB"):
        check_voice(b"ID3" + b"\x00" * (10 * 1024 * 1024))
    status, body = send(client, sample_media["product_video"], b"%PDF-1.7 not audio")
    assert (status, body["detail"]) == (422, VOICE_PROBLEM)


def test_the_voice_note_is_kept_as_speech_for_the_director(
    client: TestClient, session: Session, sample_media: dict[str, Path], voice_note: Path
) -> None:
    video = made_with(client, session, sample_media["product_video"], voice_note.read_bytes(),
                      "voice")  # fmt: skip
    assert video.status == VideoStatus.READY
    assert video.voice_original_key is not None
    assert video.voice_key == f"videos/{video.id}/voice.mp3"
    assert video.voice_seconds == pytest.approx(3, abs=0.2)
    prepared = [e for e in audit.entries_for(session, "video", video.id)
                if e.action == "video.prepared"]  # fmt: skip
    assert prepared[0].data["voice_note_seconds"] == video.voice_seconds

    brief, reading = brief_of(session, video)
    assert reading.voice_note is not None
    assert (brief.offer_text, brief.offer_source) == ("Eid sale, 25% off", "voice")
    assert (brief.audience, brief.occasion) == ("young girls", "eid")
    assert brief.price == "Rs 3,200" or brief.price is None  # the price is only ever typed
    assert "offer 'Eid sale, 25% off' (voice); for Eid" in said(session, video, "analysis.done")[0]


def test_long_voice_notes_keep_their_first_minute(
    client: TestClient, session: Session, sample_media: dict[str, Path], tmp_path: Path
) -> None:
    long_note = tone(tmp_path, 65, "long.mp3", "-b:a", "16k")
    video = made_with(client, session, sample_media["product_video"], long_note.read_bytes(),
                      "voice")  # fmt: skip
    assert video.voice_seconds == pytest.approx(60, abs=0.3)


def test_typed_offers_win_but_the_occasion_still_counts(
    client: TestClient, session: Session, sample_media: dict[str, Path], voice_note: Path
) -> None:
    video = made_with(client, session, sample_media["product_video"], voice_note.read_bytes(),
                      "voice", offer="Buy 2 get 1 free")  # fmt: skip
    brief, _ = brief_of(session, video)
    assert (brief.offer_text, brief.offer_source) == ("Buy 2 get 1 free", "owner")
    assert brief.occasion == "eid"


def test_offers_with_numbers_nobody_said_are_left_out(
    client: TestClient, session: Session, sample_media: dict[str, Path], voice_note: Path
) -> None:
    video = made_with(client, session, sample_media["product_video"], voice_note.read_bytes(),
                      "voice_made_up")  # fmt: skip
    brief, reading = brief_of(session, video)
    assert reading.voice_note is not None
    assert reading.voice_note.offer is None
    assert (brief.offer_text, brief.offer_source) == (None, "none")
    assert brief.occasion == "eid"
    assert said(session, video, "voice.offer_dropped") == [
        "The offer from the voice note was left out: its numbers were not in what was heard."
    ]


def test_instructions_in_a_voice_note_are_ignored(
    client: TestClient, session: Session, sample_media: dict[str, Path], voice_note: Path
) -> None:
    video = made_with(client, session, sample_media["product_video"], voice_note.read_bytes(),
                      "voice_injection")  # fmt: skip
    brief, reading = brief_of(session, video)
    assert reading.voice_note is None
    assert brief.offer_source == "caption"  # the video's own offer still counts
    assert said(session, video, "guard.flagged") == [
        "The voice note seemed to give instructions; it was treated as speech and left out."
    ]


def test_a_voice_note_nobody_sent_is_ignored(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    video = made_with(client, session, sample_media["product_video"], None, "voice")
    brief, reading = brief_of(session, video)
    assert reading.voice_note is None
    assert (brief.offer_source, brief.occasion) == ("none", "none")


@pytest.mark.parametrize(
    ("note", "reason"),
    [
        (b"OggS" + b"\x00" * 64, "the voice note could not be read"),
        ("video_webm", "the voice note has no sound"),
    ],
)
def test_unreadable_voice_notes_are_left_out_and_the_video_goes_ahead(
    client: TestClient,
    session: Session,
    sample_media: dict[str, Path],
    note: bytes | str,
    reason: str,
) -> None:
    data = note if isinstance(note, bytes) else sample_media[note].read_bytes()
    video = made_with(client, session, sample_media["product_video"], data, "default")
    assert video.status == VideoStatus.READY
    assert video.voice_key is None
    skipped = [e for e in audit.entries_for(session, "video", video.id)
               if e.action == "voice.skipped"]  # fmt: skip
    assert skipped[0].data["reason"] == reason
    assert ad_for(session, video.id).step == "build"
