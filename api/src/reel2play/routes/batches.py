"""Batch mode (feature 46): a shop or an agency uploads several products at once and gets one
tested game per product, all sharing the shop's details and offer.

Each file is one product (a video or a photo), optionally with its own name, price and
offer. Every file is checked before anything is stored, so one bad file stops the batch
with a message saying which. Each product then goes through the ordinary pipeline; the
director is told which templates the other games of the set use, so the set is varied.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy import select

from reel2play import audit
from reel2play.analysis import Occasion
from reel2play.deps import SessionDep, SettingsDep, StorageDep
from reel2play.intake.upload import (
    Brief,
    UploadLimits,
    UploadRejectedError,
    accept_upload,
    classify,
)
from reel2play.models import Ad, AdStatus, Analysis, Batch, Export, ExportKind, Shop, Video
from reel2play.publish.hosted import page_link
from reel2play.routes.uploads import _read_limited, check_shop, unprocessable
from reel2play.shops import issue_key

router = APIRouter(prefix="/api/batches", tags=["batches"])


class BatchItemIn(BaseModel):
    """What the owner typed for one product; anything left out comes from the shared form."""

    name: str | None = Field(default=None, max_length=60)
    price: str | None = Field(default=None, max_length=40)
    offer: str | None = Field(default=None, max_length=200)


ITEMS = TypeAdapter(list[BatchItemIn])


class BatchItemOut(BaseModel):
    video_id: uuid.UUID
    name: str | None
    price: str | None
    video_status: str
    ad_id: uuid.UUID | None
    status: str | None
    template: str | None
    link: str | None
    preview_url: str | None


class BatchOut(BaseModel):
    id: uuid.UUID
    shop_id: uuid.UUID
    created_at: datetime
    items: list[BatchItemOut]
    published: int
    finished: int
    # Given once, when the batch makes a new shop: the browser keeps it for the studio.
    shop_key: str | None = None


FINISHED = {
    AdStatus.PUBLISHED,
    AdStatus.NEEDS_PERSON,
    AdStatus.BLOCKED,
    AdStatus.FAILED,
}


def batch_out(
    session: SessionDep, storage: StorageDep, settings: SettingsDep, batch: Batch
) -> BatchOut:
    videos = list(
        session.scalars(
            select(Video).where(Video.batch_id == batch.id).order_by(Video.created_at, Video.id)
        )
    )
    ads = {
        ad.video_id: ad
        for ad in session.scalars(
            select(Ad)
            .where(Ad.video_id.in_([v.id for v in videos]), Ad.easier_for.is_(None))
            .order_by(Ad.created_at)
        )
        if ad.variant == "A"
    }
    ad_ids = [ad.id for ad in ads.values()]
    names = {
        ad_id: str(brief["product"]["name"])
        for ad_id, brief in session.execute(
            select(Analysis.ad_id, Analysis.brief).where(Analysis.ad_id.in_(ad_ids))
        )
    }
    previews = {
        ad_id: storage.public_url(key)
        for ad_id, key in session.execute(
            select(Export.ad_id, Export.key).where(
                Export.ad_id.in_(ad_ids), Export.kind == ExportKind.PREVIEW
            )
        )
    }
    items = []
    for video in videos:
        ad = ads.get(video.id)
        live = ad is not None and ad.status == AdStatus.PUBLISHED and ad.slug
        items.append(
            BatchItemOut(
                video_id=video.id,
                name=video.owner_product or (names.get(ad.id) if ad else None),
                price=video.owner_price,
                video_status=video.status,
                ad_id=ad.id if ad else None,
                status=ad.status if ad else None,
                template=ad.template if ad else None,
                link=page_link(settings.share_base, ad.slug) if live and ad and ad.slug else None,
                preview_url=previews.get(ad.id) if ad else None,
            )
        )
    return BatchOut(
        id=batch.id,
        shop_id=batch.shop_id,
        created_at=batch.created_at,
        items=items,
        published=sum(1 for i in items if i.status == AdStatus.PUBLISHED),
        finished=sum(1 for i in items if i.status in FINISHED or i.video_status == "failed"),
    )


def read_items(raw: str, count: int) -> list[BatchItemIn]:
    try:
        items = ITEMS.validate_json(raw or "[]")
    except ValidationError as exc:
        raise UploadRejectedError("The product list could not be read.") from exc
    if items and len(items) != count:
        raise UploadRejectedError("Give one line of product details for each file.")
    return items or [BatchItemIn() for _ in range(count)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_batch(
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    files: Annotated[list[UploadFile], File(description="One video or photo per product")],
    shop_name: Annotated[str, Form()],
    items: Annotated[str, Form(description="JSON: [{name, price, offer}] per file")] = "[]",
    rights_confirmed: Annotated[bool, Form()] = False,
    shop_id: Annotated[uuid.UUID | None, Form()] = None,
    language: Annotated[str, Form()] = "auto",
    whatsapp_number: Annotated[str | None, Form()] = None,
    shop_url: Annotated[str | None, Form()] = None,
    offer: Annotated[str | None, Form()] = None,
    occasion: Annotated[str, Form()] = "none",
    x_shop_key: Annotated[str | None, Header()] = None,
    x_agency_key: Annotated[str | None, Header()] = None,
) -> BatchOut:
    check_shop(session, shop_id, x_shop_key, x_agency_key)
    if not 2 <= len(files) <= settings.max_batch_items:
        raise unprocessable(
            UploadRejectedError(
                f"A batch has 2 to {settings.max_batch_items} products, one file each."
            )
        )
    limits = UploadLimits(settings.max_upload_bytes, settings.max_photos)
    try:
        details = read_items(items, len(files))
        briefs = [
            Brief(
                shop_name=shop_name,
                shop_id=shop_id,
                language=language,
                whatsapp_number=whatsapp_number,
                shop_url=shop_url,
                price=item.price,
                offer=item.offer or offer,
                rights_confirmed=rights_confirmed,
                occasion=cast(Occasion, occasion),  # checked by Brief
                product_name=item.name,
            )
            for item in details
        ]
        incoming = []
        for number, upload in enumerate(files, start=1):
            try:
                data = await _read_limited(upload, settings.max_upload_bytes)
                incoming.append(classify([data], limits))
            except UploadRejectedError as exc:
                raise UploadRejectedError(f"File {number}: {exc}") from exc
        if not rights_confirmed:
            raise UploadRejectedError("Please confirm the videos are yours to use before we start.")
    except (ValidationError, UploadRejectedError) as exc:
        raise unprocessable(exc) from exc

    first = accept_upload(session, storage, briefs[0], incoming[0], source="batch")
    batch = Batch(shop_id=first.shop_id, items=len(files))
    session.add(batch)
    session.flush()
    first.batch_id = batch.id
    for brief, files_in in zip(briefs[1:], incoming[1:], strict=True):
        brief = brief.model_copy(update={"shop_id": first.shop_id})
        accept_upload(session, storage, brief, files_in, source="batch", batch_id=batch.id)
    audit.record(
        session,
        actor="shop",
        action="batch.received",
        subject_type="shop",
        subject_id=first.shop_id,
        data={"message": f"A batch of {len(files)} products.", "batch_id": str(batch.id)},
    )
    out = batch_out(session, storage, settings, batch)
    owner = session.get(Shop, first.shop_id)
    if shop_id is None and owner is not None and owner.access_key_hash is None:
        out.shop_key = issue_key(owner)
    return out


@router.get("/{batch_id}")
def get_batch(
    batch_id: uuid.UUID, session: SessionDep, storage: StorageDep, settings: SettingsDep
) -> BatchOut:
    batch = session.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "batch not found")
    return batch_out(session, storage, settings, batch)
