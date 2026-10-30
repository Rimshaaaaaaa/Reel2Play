"""Template marketplace for designers (feature 49): the template gallery with live demos,
and designers' submissions with automatic checks and review by the Reel2Play team."""

from __future__ import annotations

import hmac
import secrets
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import select

from reel2play import audit
from reel2play.agency import key_hash
from reel2play.builder.html import compile_game
from reel2play.builder.templates import TemplateSpec, buildable, load_templates
from reel2play.db import utcnow
from reel2play.deps import SessionDep, SettingsDep, StorageDep
from reel2play.marketplace import (
    MAX_GAME_TS_BYTES,
    MAX_TEMPLATE_JSON_BYTES,
    check_submission,
    demo_config,
)
from reel2play.models import SubmissionStatus, TemplateSubmission
from reel2play.ratelimit import RateLimiter, caller_key
from reel2play.routes.media import GAME_CSP
from reel2play.settings import Settings

router = APIRouter(tags=["marketplace"])
SENDERS = RateLimiter(5, 3600)
FILES = ("template.json", "game.ts")


class TemplateCard(BaseModel):
    id: str
    name: str
    description: str
    control: str
    good_for: list[str]
    designer: str
    demo_url: str


class SubmissionOut(BaseModel):
    id: uuid.UUID
    template_id: str | None
    status: str
    problems: list[str]
    review_note: str | None
    created_at: datetime
    # Given once: the designer keeps it to check the review.
    token: str | None = None


class ReviewIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=1000)


class WaitingOut(BaseModel):
    id: uuid.UUID
    template_id: str | None
    designer_name: str
    designer_contact: str
    created_at: datetime


def templates_of(settings: Settings) -> dict[str, TemplateSpec]:
    return load_templates(settings.templates_dir)


@router.get("/api/marketplace/templates")
def gallery(settings: SettingsDep) -> list[TemplateCard]:
    base = settings.api_base_url.rstrip("/")
    return [
        TemplateCard(
            id=spec.id,
            name=spec.name,
            description=spec.description,
            control=spec.control,
            good_for=[c.replace("_", " ") for c in spec.good_for],
            designer=spec.designer,
            demo_url=f"{base}/templates/{spec.id}/demo",
        )
        for spec in buildable(templates_of(settings)).values()
    ]


@lru_cache(maxsize=16)
def _demo(template_id: str, templates_dir: Path, dist: Path, max_bytes: int) -> bytes:
    spec = load_templates(templates_dir)[template_id]
    return compile_game(demo_config(spec), dist, max_bytes).html


@router.get("/templates/{template_id}/demo")
def demo(template_id: str, settings: SettingsDep) -> Response:
    if template_id not in buildable(templates_of(settings)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such template")
    page = _demo(
        template_id, settings.templates_dir, settings.engine_dist_dir, settings.max_game_bytes
    )
    return Response(
        page,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Security-Policy": GAME_CSP,
            "Cache-Control": "public, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


def submission_out(found: TemplateSubmission, token: str | None = None) -> SubmissionOut:
    return SubmissionOut(
        id=found.id,
        template_id=found.template_id,
        status=found.status,
        problems=found.problems,
        review_note=found.review_note,
        created_at=found.created_at,
        token=token,
    )


@router.post("/api/marketplace/submissions", status_code=status.HTTP_201_CREATED)
async def submit(
    request: Request,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    template_json: Annotated[UploadFile, File()],
    game_ts: Annotated[UploadFile, File()],
    designer_name: Annotated[str, Form(min_length=1, max_length=80)],
    designer_contact: Annotated[str, Form(min_length=3, max_length=200)],
    license_confirmed: Annotated[bool, Form()] = False,
) -> SubmissionOut:
    if not license_confirmed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Confirm that you made this template and license it to Reel2Play's shops.",
        )
    caller = request.client.host if request.client else "unknown"
    if not SENDERS.allow(caller_key(caller, "marketplace")):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many templates this hour.")
    spec_bytes = await template_json.read(MAX_TEMPLATE_JSON_BYTES + 1)
    code_bytes = await game_ts.read(MAX_GAME_TS_BYTES + 1)
    taken = set(templates_of(settings)) | set(
        session.scalars(
            select(TemplateSubmission.template_id).where(
                TemplateSubmission.status.in_([SubmissionStatus.WAITING, SubmissionStatus.APPROVED])
            )
        )
    )
    check = check_submission(spec_bytes, code_bytes, {t for t in taken if t})
    found = TemplateSubmission(
        id=uuid.uuid4(),
        designer_name=designer_name.strip(),
        designer_contact=designer_contact.strip(),
        template_id=check.template_id,
        status=SubmissionStatus.WAITING if check.passed else SubmissionStatus.CHECKS_FAILED,
        problems=check.problems,
        token_hash="",
        files_key="",
    )
    found.files_key = f"marketplace/{found.id}"
    storage.put(f"{found.files_key}/template.json", spec_bytes, "application/json")
    storage.put(f"{found.files_key}/game.ts", code_bytes, "text/plain; charset=utf-8")
    token = secrets.token_urlsafe(18)
    found.token_hash = key_hash(token)
    session.add(found)
    session.flush()
    audit.record(
        session,
        actor="designer",
        action="marketplace.submitted",
        subject_type="template_submission",
        subject_id=found.id,
        data={"message": f"A template was submitted ({found.status}).", "problems": check.problems},
    )
    return submission_out(found, token)


@router.get("/api/marketplace/submissions/{submission_id}")
def submission_status(submission_id: uuid.UUID, token: str, session: SessionDep) -> SubmissionOut:
    found = session.get(TemplateSubmission, submission_id)
    if found is None or not hmac.compare_digest(found.token_hash, key_hash(token)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "submission not found")
    return submission_out(found)


def need_admin(settings: Settings, key: str | None) -> None:
    expected = settings.admin_key.get_secret_value()
    if not expected or not key or not hmac.compare_digest(key, expected):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Only the Reel2Play team reviews templates."
        )


@router.get("/api/marketplace/review")
def waiting(
    session: SessionDep, settings: SettingsDep, x_admin_key: Annotated[str | None, Header()] = None
) -> list[WaitingOut]:
    need_admin(settings, x_admin_key)
    return [
        WaitingOut(
            id=s.id,
            template_id=s.template_id,
            designer_name=s.designer_name,
            designer_contact=s.designer_contact,
            created_at=s.created_at,
        )
        for s in session.scalars(
            select(TemplateSubmission)
            .where(TemplateSubmission.status == SubmissionStatus.WAITING)
            .order_by(TemplateSubmission.created_at)
        )
    ]


@router.get("/api/marketplace/submissions/{submission_id}/files/{name}")
def submission_file(
    submission_id: uuid.UUID,
    name: str,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    x_admin_key: Annotated[str | None, Header()] = None,
) -> Response:
    """For review only: the file as plain text, never served as a page or run."""
    need_admin(settings, x_admin_key)
    found = session.get(TemplateSubmission, submission_id)
    if found is None or name not in FILES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")
    return Response(
        storage.get(f"{found.files_key}/{name}"),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/api/marketplace/submissions/{submission_id}/review")
def review(
    submission_id: uuid.UUID,
    decision: ReviewIn,
    session: SessionDep,
    settings: SettingsDep,
    x_admin_key: Annotated[str | None, Header()] = None,
) -> SubmissionOut:
    need_admin(settings, x_admin_key)
    found = session.get(TemplateSubmission, submission_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "submission not found")
    if found.status != SubmissionStatus.WAITING:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Only a submission that passed the checks is reviewed."
        )
    found.status = (
        SubmissionStatus.APPROVED if decision.decision == "approve" else SubmissionStatus.REJECTED
    )
    found.review_note = decision.note.strip() or None
    found.reviewed_at = utcnow()
    audit.record(
        session,
        actor="admin",
        action=f"marketplace.{found.status}",
        subject_type="template_submission",
        subject_id=found.id,
        data={"message": f"The template was {found.status}.", "note": found.review_note},
    )
    return submission_out(found)
