"""ORM models. One class per table; table names follow the build spec's data model."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from reel2play.db import Base, TimestampMixin, utcnow


def new_id() -> uuid.UUID:
    return uuid.uuid4()


class Shop(TimestampMixin, Base):
    __tablename__ = "shops"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(8), default="auto")
    country: Mapped[str] = mapped_column(String(2), default="PK")
    whatsapp_number: Mapped[str | None] = mapped_column(String(20))
    shop_url: Mapped[str | None] = mapped_column(String(500))
    brand_kit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("brand_kits.id", use_alter=True, ondelete="SET NULL")
    )
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    # SHA-256 of the key this shop's browser keeps for the studio; the key itself is not kept.
    access_key_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    # Feature 43: players may ask for this shop's offers on WhatsApp, with their consent.
    leads_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    lead_code: Mapped[str | None] = mapped_column(String(12), unique=True)
    # Feature 47: a brand an agency manages.
    agency_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agencies.id", ondelete="SET NULL"), index=True
    )


class BrandKit(TimestampMixin, Base):
    __tablename__ = "brand_kits"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    palette: Mapped[list[str]] = mapped_column(JSONB, default=list)
    logo_key: Mapped[str | None] = mapped_column(String(300))
    fonts: Mapped[list[str]] = mapped_column(JSONB, default=list)
    tone: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class VideoKind(StrEnum):
    VIDEO = "video"
    PHOTOS = "photos"


class VideoStatus(StrEnum):
    UPLOADED = "uploaded"
    READY = "ready"
    FAILED = "failed"


class CtaKind(StrEnum):
    WHATSAPP = "whatsapp"
    LINK = "link"


class Batch(TimestampMixin, Base):
    """Several products uploaded together, one game each (feature 46)."""

    __tablename__ = "batches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    shop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    items: Mapped[int] = mapped_column(Integer)


class Video(TimestampMixin, Base):
    """One upload: a Reel or product video, or a set of product photos."""

    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10), default=VideoKind.VIDEO)
    status: Mapped[str] = mapped_column(String(12), default=VideoStatus.UPLOADED)
    error: Mapped[str | None] = mapped_column(Text)
    original_key: Mapped[str | None] = mapped_column(String(300))
    muted_key: Mapped[str | None] = mapped_column(String(300))
    audio_key: Mapped[str | None] = mapped_column(String(300))
    photo_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # Feature 10: the owner's voice note about the offer, as sent and as the director hears it.
    voice_original_key: Mapped[str | None] = mapped_column(String(300))
    voice_key: Mapped[str | None] = mapped_column(String(300))
    voice_seconds: Mapped[float | None] = mapped_column(Float)
    # Feature 11: the photos are different products (a catalog), not views of one product.
    catalog: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    duration_s: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    rights_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    audio_removed: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_price: Mapped[str | None] = mapped_column(String(40))
    owner_offer: Mapped[str | None] = mapped_column(String(200))
    # Feature 22: the occasion the owner picked (Eid, 14 August ...); it wins over the video.
    owner_occasion: Mapped[str | None] = mapped_column(String(20))
    cta_kind: Mapped[str] = mapped_column(String(10), default=CtaKind.WHATSAPP)
    cta_target: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(20), default="web")
    whatsapp_chat_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("whatsapp_chats.id", ondelete="SET NULL")
    )
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set for the try-it samples; also picks the mock model's recorded answers.
    sample_key: Mapped[str | None] = mapped_column(String(60))
    # Feature 46: one product of a batch, and the name the owner gave it.
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("batches.id", ondelete="SET NULL"), index=True
    )
    owner_product: Mapped[str | None] = mapped_column(String(60))
    # Feature 24: the owner asked for an experimental game with a new mechanic.
    lab: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Job(TimestampMixin, Base):
    """A unit of background work in the PostgreSQL queue."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_due", "status", "run_after"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(60), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(10), default=JobStatus.QUEUED, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(80))
    last_error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEntry(Base):
    """Hash-chained record of every agent and person action."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(60))
    action: Mapped[str] = mapped_column(String(80))
    subject_type: Mapped[str] = mapped_column(String(30), index=True)
    subject_id: Mapped[str] = mapped_column(String(60), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), unique=True)


class ModelCall(TimestampMixin, Base):
    """One request to a model endpoint, with tokens and cost (feature 48)."""

    __tablename__ = "model_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ad_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    video_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    role: Mapped[str] = mapped_column(String(30))
    endpoint: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    prompt_name: Mapped[str] = mapped_column(String(60))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    usd_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(0))
    pkr_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal(0))
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text)


class AdStatus(StrEnum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    CUTTING_OUT = "cutting_out"
    BUILDING = "building"
    TESTING = "testing"
    FIXING = "fixing"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    NEEDS_PERSON = "needs_person"
    BLOCKED = "blocked"
    FAILED = "failed"
    # Feature 44: an easier version, tested and waiting for the owner to use it.
    READY = "ready"
    # Feature 44: a game whose link now opens its easier version.
    REPLACED = "replaced"


class Suggestion(StrEnum):
    """Where an easier version (feature 44) stands with the owner."""

    MAKING = "making"  # being built and tested
    READY = "ready"  # tested, waiting for the owner
    USING = "using"  # the owner said yes; publishing under the same link
    USED = "used"  # live under the old link
    DISMISSED = "dismissed"  # the owner said no


class Ad(TimestampMixin, Base):
    """One ad made from one upload. Variants of the same ad share ``group_id``."""

    __tablename__ = "ads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    group_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=new_id, index=True)
    shop_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default=AdStatus.QUEUED, index=True)
    step: Mapped[str | None] = mapped_column(String(20))
    template: Mapped[str | None] = mapped_column(String(30))
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    variant: Mapped[str] = mapped_column(String(4), default="A")
    language: Mapped[str | None] = mapped_column(String(8))
    error: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    # The shop's plain-words test report (feature 30), written when testing ends.
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # The short link's code (feature 32): random, never derived from the shop or the owner.
    slug: Mapped[str | None] = mapped_column(String(12), unique=True)
    # Feature 19: on version A only, the link that shares visitors between A, B and C.
    ab_slug: Mapped[str | None] = mapped_column(String(12), unique=True)
    captions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Shown in the public gallery of evaluated ads (feature 61).
    in_gallery: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # Feature 44: an easier version of this other ad, made because players found it hard.
    easier_for: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ads.id", ondelete="CASCADE"), index=True
    )
    suggestion: Mapped[str | None] = mapped_column(String(10))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Analysis(TimestampMixin, Base):
    """What the director found in the video, and the brief derived from it."""

    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    ad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ads.id", ondelete="CASCADE"), index=True)
    video_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    reading: Mapped[dict[str, Any]] = mapped_column(JSONB)
    brief: Mapped[dict[str, Any]] = mapped_column(JSONB)
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    prompt_version: Mapped[int] = mapped_column(Integer, default=1)


class Sprite(TimestampMixin, Base):
    """A product cut-out: the sprite PNG, its mask, and how it was made."""

    __tablename__ = "sprites"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    ad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ads.id", ondelete="CASCADE"), index=True)
    source_frame_key: Mapped[str] = mapped_column(String(300))
    mask_key: Mapped[str] = mapped_column(String(300))
    sprite_key: Mapped[str] = mapped_column(String(300))
    method: Mapped[str] = mapped_column(String(12))
    quality: Mapped[str] = mapped_column(String(8))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    area_fraction: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    # Feature 11: 0 is the main product; 1 to 3 are the other products the game shows.
    product_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Feature 7: the product followed across a short clip, as a strip of square frames.
    track_key: Mapped[str | None] = mapped_column(String(300))
    track_frames: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    track_fps: Mapped[float | None] = mapped_column(Float)
    track_method: Mapped[str | None] = mapped_column(String(16))
    # Feature 55: whether the source frame was checked for bystanders' faces (and blurred).
    face_check: Mapped[str] = mapped_column(
        String(10), default="unchecked", server_default="unchecked"
    )


class Build(TimestampMixin, Base):
    """One compiled game: the proposal it came from, its config, and the HTML file."""

    __tablename__ = "builds"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    ad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ads.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    template: Mapped[str] = mapped_column(String(30))
    proposal: Mapped[dict[str, Any]] = mapped_column(JSONB)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    html_key: Mapped[str] = mapped_column(String(300))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    platform: Mapped[str] = mapped_column(String(10), default="hosted")


class TestRun(TimestampMixin, Base):
    """One play-test of one build: every gate's result, the runs, and screenshots."""

    __tablename__ = "test_runs"
    __test__ = False  # not a pytest test class

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    ad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ads.id", ondelete="CASCADE"), index=True)
    build_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("builds.id", ondelete="CASCADE"))
    round: Mapped[int] = mapped_column(Integer)
    passed: Mapped[bool] = mapped_column(Boolean)
    gates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    runs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    # Each run's game commands, so publishing can replay the winning run exactly.
    replays: Mapped[list[list[dict[str, Any]]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    screenshots: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    critic: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    duration_s: Mapped[float] = mapped_column(Float)


class Fix(TimestampMixin, Base):
    """One repair round: which gates failed, what the director changed, the new build."""

    __tablename__ = "fixes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    ad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ads.id", ondelete="CASCADE"), index=True)
    round: Mapped[int] = mapped_column(Integer)
    failed_gates: Mapped[list[str]] = mapped_column(JSONB)
    change: Mapped[str] = mapped_column(Text)
    build_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("builds.id", ondelete="CASCADE"))


class ExportKind(StrEnum):
    HOSTED = "hosted"  # the game page's HTML, with link-preview tags
    PREVIEW = "preview"  # the link-preview image
    REEL = "reel"  # 9:16 gameplay MP4
    META_HTML = "meta_html"  # Meta playable, one HTML file
    META_ZIP = "meta_zip"  # Meta playable, the same as a ZIP with index.html
    LEAD_IN = "lead_in"  # the Meta playable's lead-in video
    REEL_SQUARE = "reel_square"  # 1:1 Reel for feeds (feature 18)
    REEL_WIDE = "reel_wide"  # 16:9 Reel for websites and YouTube (feature 18)
    POSTER = "poster"  # A4 PDF for the shop counter with the game's QR code (feature 36)
    POSTER_PREVIEW = "poster_jpg"  # a small picture of that poster


class Export(TimestampMixin, Base):
    """One published output of an ad (features 32 to 35)."""

    __tablename__ = "exports"
    __table_args__ = (UniqueConstraint("ad_id", "kind"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    ad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ads.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(12))
    key: Mapped[str] = mapped_column(String(300))
    public: Mapped[bool] = mapped_column(Boolean, default=False)
    content_type: Mapped[str] = mapped_column(String(60))
    size_bytes: Mapped[int] = mapped_column(Integer)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class ChatState(StrEnum):
    IDLE = "idle"
    AWAITING_CONSENT = "awaiting_consent"
    WORKING = "working"
    AWAITING_LEAD = "awaiting_lead"  # feature 43: a player was asked to agree to offers


class WhatsAppChat(TimestampMixin, Base):
    """One WhatsApp conversation with a shop owner (feature 2).

    The number is kept only to reply in the same chat; it never goes into logs, links or
    the audit trail (those use the chat id).
    """

    __tablename__ = "whatsapp_chats"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    wa_id: Mapped[str] = mapped_column(String(20), unique=True)
    shop_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shops.id", ondelete="SET NULL"))
    state: Mapped[str] = mapped_column(String(20), default=ChatState.IDLE)
    # The media waiting for the owner's rights confirmation.
    pending: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WhatsAppMessage(TimestampMixin, Base):
    """Message ids seen or sent, so a retried webhook is handled once."""

    __tablename__ = "whatsapp_messages"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("whatsapp_chats.id", ondelete="CASCADE"), index=True
    )
    direction: Mapped[str] = mapped_column(String(3))
    kind: Mapped[str] = mapped_column(String(20))


class EventKind(StrEnum):
    PLAY = "play"
    FINISH = "finish"
    CTA = "cta"
    SHARE = "share"  # feature 42: a player challenged a friend


class EventSource(StrEnum):
    """Where a play started (features 36 and 37): never who played it."""

    LINK = "link"  # a shared link, a story sticker, an ad
    QR = "qr"  # the counter poster's QR code
    EMBED = "embed"  # the game embedded on the shop's own website
    SHARE = "share"  # feature 42: a friend's challenge link


class Event(Base):
    """One anonymous moment on a hosted game page (feature 39): no IP, device or person."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ads.id", ondelete="CASCADE"), index=True)
    variant: Mapped[str] = mapped_column(String(4), default="A")
    kind: Mapped[str] = mapped_column(String(10))
    seconds: Mapped[float | None] = mapped_column(Float)
    won: Mapped[bool | None] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(6), default=EventSource.LINK, server_default="link")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Preference(Base):
    """One answer on the blind preference page (feature 41): which ad, which side, which pick."""

    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ads.id", ondelete="CASCADE"), index=True)
    choice: Mapped[str] = mapped_column(String(8))  # "game" or "still"
    game_side: Mapped[str] = mapped_column(String(6))  # where the game was shown: left or right
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Coupon(Base):
    """A unique win code (feature 40): which game gave it and whether the shop took it.
    Nothing about the player: no phone number, name, IP address or device."""

    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ads.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(13), unique=True)
    variant: Mapped[str] = mapped_column(String(4), default="A")
    source: Mapped[str] = mapped_column(String(6), default=EventSource.LINK)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Lead(Base):
    """A player who agreed, on WhatsApp, that a shop may send them offers (feature 43).

    The number stays in the chat record (the only place it is kept, to reply); this row is
    the consent itself: which shop, when, and the words the player agreed to. Sending STOP
    deletes every row for that chat, and the chat too when it is not a shop owner's.
    """

    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("shop_id", "chat_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    shop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True
    )
    chat_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("whatsapp_chats.id", ondelete="CASCADE"), index=True
    )
    consent_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgencyRole(StrEnum):
    """Feature 47: what a member of an agency may do."""

    OWNER = "owner"  # everything, and invites people
    EDITOR = "editor"  # adds brands and makes games for them
    VIEWER = "viewer"  # sees the brands and their numbers


class Agency(TimestampMixin, Base):
    """An agency workspace (feature 47): several brands, several people with roles."""

    __tablename__ = "agencies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))


class AgencyMember(TimestampMixin, Base):
    """One person in an agency. Like a shop's studio, no account: a key kept in their browser
    (only its SHA-256 is stored) and the name they gave."""

    __tablename__ = "agency_members"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    agency_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agencies.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(10))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)


class AgencyInvite(TimestampMixin, Base):
    """A single-use invite to an agency, with the role it gives; only its hash is stored."""

    __tablename__ = "agency_invites"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    agency_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agencies.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(10))
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SubmissionStatus(StrEnum):
    CHECKS_FAILED = "checks_failed"  # code found problems; nothing goes to a person
    WAITING = "waiting"  # passed the checks, waiting for the Reel2Play team
    APPROVED = "approved"  # a maintainer adds it to templates/, where it is tested
    REJECTED = "rejected"


class TemplateSubmission(TimestampMixin, Base):
    """A designer's template for the marketplace (feature 49). The designer's name and how to
    reach them are what they chose to give; the files stay private until approved."""

    __tablename__ = "template_submissions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    designer_name: Mapped[str] = mapped_column(String(80))
    designer_contact: Mapped[str] = mapped_column(String(200))
    template_id: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(14))
    problems: Mapped[list[str]] = mapped_column(JSONB, default=list)
    review_note: Mapped[str | None] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    files_key: Mapped[str] = mapped_column(String(300))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
