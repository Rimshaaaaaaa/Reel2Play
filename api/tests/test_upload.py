"""Upload (feature 1): validation, storage, preparation job, and the API."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from reel2play import audit
from reel2play.deps import get_storage
from reel2play.intake.upload import (
    Brief,
    MediaType,
    UploadLimits,
    UploadRejectedError,
    classify,
    sniff,
)
from reel2play.jobs.queue import run_due, run_one
from reel2play.media.storage import LocalStorage
from reel2play.models import Job, Shop, Video, VideoStatus

LIMITS = UploadLimits(max_bytes=1024, max_photos=2)
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 8
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 12


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (MP4, MediaType.MP4),
        (b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 4, MediaType.QUICKTIME),
        (b"\x1a\x45\xdf\xa3" + b"\x00" * 12, MediaType.WEBM),
        (JPG, MediaType.JPEG),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, MediaType.PNG),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", MediaType.WEBP),
        (b"%PDF-1.7" + b"\x00" * 8, None),
    ],
)
def test_sniff(head: bytes, expected: MediaType | None) -> None:
    assert sniff(head) == expected


def test_media_type_properties() -> None:
    assert MediaType.QUICKTIME.extension == "mov"
    assert MediaType.QUICKTIME.is_video
    assert not MediaType.WEBP.is_video


def test_classify_rules() -> None:
    assert [f.media_type for f in classify([JPG, JPG], LIMITS)] == [MediaType.JPEG] * 2
    with pytest.raises(UploadRejectedError, match="choose a video"):
        classify([], LIMITS)
    with pytest.raises(UploadRejectedError, match="under"):
        classify([MP4 + b"\x00" * 2000], LIMITS)
    with pytest.raises(UploadRejectedError, match="Only MP4"):
        classify([b"hello world 12345"], LIMITS)
    with pytest.raises(UploadRejectedError, match="not both"):
        classify([MP4, JPG], LIMITS)
    with pytest.raises(UploadRejectedError, match="at most 2"):
        classify([JPG, JPG, JPG], LIMITS)


def test_brief_cleans_input() -> None:
    brief = Brief(
        shop_name="Ali Shoes",
        whatsapp_number="+92 300-1234567",
        price="  Rs 2,499 ",
        offer=" ",
        shop_url="https://ali.example/shop",
    )
    assert brief.whatsapp_number == "923001234567"
    assert brief.price == "Rs 2,499"
    assert brief.offer is None
    assert Brief(shop_name="x", whatsapp_number=" ", shop_url="").whatsapp_number is None
    with pytest.raises(ValidationError, match="10 to 15 digits"):
        Brief(shop_name="x", whatsapp_number="12345")
    with pytest.raises(ValidationError, match="https://"):
        Brief(shop_name="x", shop_url="http://insecure.example")
    with pytest.raises(ValidationError):
        Brief(shop_name="x", language="fr")


def _post(
    client: TestClient, files: list[Path], key: str | None = None, **fields: str
) -> dict[str, object]:
    data = {"shop_name": "Ali Shoes", "rights_confirmed": "true", **fields}
    payload = [("files", (p.name, p.read_bytes())) for p in files]
    headers = {"X-Shop-Key": key} if key else {}
    response = client.post("/api/uploads", data=data, files=payload, headers=headers)
    return {**response.json(), "http": response.status_code}


def test_video_upload_is_stored_prepared_and_audited(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    result = _post(
        client,
        [sample_media["video_with_audio"]],
        whatsapp_number="923001234567",
        price="Rs 2,499",
        offer="20% off",
    )
    assert result["http"] == 201
    assert result["kind"] == "video"
    video_id = uuid.UUID(str(result["id"]))
    assert session.scalars(select(Job.kind)).all() == ["video.prepare"]

    assert run_one("test")
    session.expire_all()
    video = session.get(Video, video_id)
    assert video is not None
    assert video.status == VideoStatus.READY
    assert video.audio_removed
    assert video.duration_s == pytest.approx(3, abs=0.2)
    assert (video.width, video.height) == (360, 640)
    assert video.owner_price == "Rs 2,499"
    assert video.cta_kind == "whatsapp"
    storage = get_storage()
    assert video.muted_key
    assert video.audio_key
    assert storage.exists(video.muted_key)
    assert storage.exists(video.audio_key)
    assert [e.action for e in audit.entries_for(session, "video", video_id)] == [
        "upload.received",
        "video.prepared",
    ]
    assert client.get(f"/api/videos/{video_id}").json()["status"] == "ready"


def test_muted_copy_has_no_audio(session: Session, sample_media: dict[str, Path]) -> None:
    from reel2play.media.video import probe, strip_audio

    target = sample_media["video_with_audio"].with_name("muted-check.mp4")
    strip_audio(sample_media["video_with_audio"], target)
    assert not probe(target).has_audio
    webm_target = sample_media["video_webm"].with_name("from-webm.mp4")
    strip_audio(sample_media["video_webm"], webm_target)
    assert probe(webm_target).has_video


def test_photos_upload(client: TestClient, session: Session, sample_media: dict[str, Path]) -> None:
    result = _post(
        client, [sample_media["photo_jpg"], sample_media["photo_png"]], shop_url="https://x.pk"
    )
    assert result["kind"] == "photos"
    run_due("test")
    session.expire_all()
    video = session.get(Video, uuid.UUID(str(result["id"])))
    assert video is not None
    assert video.status == VideoStatus.READY
    assert video.width == 400
    assert video.cta_kind == "link"
    assert len(video.photo_keys) == 2


def test_silent_video_has_no_speech_track(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    result = _post(client, [sample_media["video_silent"]])
    run_due("test")
    session.expire_all()
    video = session.get(Video, uuid.UUID(str(result["id"])))
    assert video is not None
    assert video.status == VideoStatus.READY
    assert video.audio_key is None


def test_too_long_video_fails_with_reason(
    client: TestClient,
    session: Session,
    sample_media: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reel2play.settings import get_settings

    monkeypatch.setattr(get_settings(), "max_video_seconds", 5)
    result = _post(client, [sample_media["video_long"]])
    run_due("test")
    session.expire_all()
    video = session.get(Video, uuid.UUID(str(result["id"])))
    assert video is not None
    assert video.status == VideoStatus.FAILED
    assert "limit is 5s" in (video.error or "")


def test_broken_video_fails_without_retries(client: TestClient, session: Session) -> None:
    broken = MP4 + b"\x00" * 64
    response = client.post(
        "/api/uploads",
        data={"shop_name": "S", "rights_confirmed": "true"},
        files=[("files", ("broken.mp4", broken))],
    )
    assert response.status_code == 201
    run_due("test")
    session.expire_all()
    video = session.get(Video, uuid.UUID(response.json()["id"]))
    assert video is not None
    assert video.status == VideoStatus.FAILED
    assert video.error


def test_rejections_are_explained(client: TestClient, sample_media: dict[str, Path]) -> None:
    no_rights = _post(client, [sample_media["photo_jpg"]], rights_confirmed="false")
    assert no_rights["http"] == 422
    assert "confirm the video is yours" in str(no_rights["detail"])
    bad_phone = _post(client, [sample_media["photo_jpg"]], whatsapp_number="123")
    assert "10 to 15 digits" in str(bad_phone["detail"])
    unknown_shop = _post(client, [sample_media["photo_jpg"]], shop_id=str(uuid.uuid4()))
    assert unknown_shop["http"] == 403
    assert "not linked to that shop" in str(unknown_shop["detail"])
    response = client.post(
        "/api/uploads",
        data={"shop_name": "S", "rights_confirmed": "true"},
        files=[("files", ("x.txt", b"plain text file here"))],
    )
    assert response.status_code == 422


def test_upload_reuses_existing_shop(
    client: TestClient, session: Session, sample_media: dict[str, Path]
) -> None:
    first = _post(client, [sample_media["photo_jpg"]])
    second = _post(
        client, [sample_media["photo_png"]], str(first["shop_key"]), shop_id=str(first["shop_id"])
    )
    assert second["shop_id"] == first["shop_id"]
    assert session.scalar(select(Shop.name)) == "Ali Shoes"


def test_file_size_limit_on_the_route(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, sample_media: dict[str, Path]
) -> None:
    from reel2play.settings import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    result = _post(client, [sample_media["photo_jpg"]])
    assert result["http"] == 422
    assert "under 0 MB" in str(result["detail"])


def test_unknown_video_is_404(client: TestClient) -> None:
    assert client.get(f"/api/videos/{uuid.uuid4()}").status_code == 404


def test_storage_is_local_in_tests() -> None:
    assert isinstance(get_storage(), LocalStorage)
