"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from reel2play.jobs import handlers  # noqa: F401 - importing registers the job handlers
from reel2play.jobs.queue import registry
from reel2play.jobs.worker import Worker
from reel2play.routes import (
    ads,
    agency,
    audit_log,
    batches,
    coupons,
    easier,
    events,
    gallery,
    game_page,
    internal,
    leads,
    live,
    marketplace,
    mcp,
    media,
    meta_import,
    studio,
    try_it,
    uploads,
    variants,
    why,
)
from reel2play.settings import AppEnv, Settings, get_settings
from reel2play.whatsapp import webhook

ATTRIBUTION = "Built with Muse Spark Open"


class Health(BaseModel):
    ok: bool
    env: str
    ai_mode: str
    storage: str
    job_kinds: list[str]
    attribution: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        worker = None
        if settings.worker_enabled and settings.app_env is not AppEnv.TEST:
            worker = Worker(settings.worker_poll_seconds)
            worker.start()
        yield
        if worker is not None:
            worker.stop()

    app = FastAPI(title="Reel2Play API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    for module in (
        uploads,
        batches,
        meta_import,
        try_it,
        ads,
        why,
        live,
        studio,
        agency,
        leads,
        gallery,
        events,
        coupons,
        media,
        game_page,
        marketplace,
        mcp,
        variants,
        easier,
        internal,
        audit_log,
        webhook,
    ):
        app.include_router(module.router)

    @app.get("/health")
    def health() -> Health:
        return Health(
            ok=True,
            env=settings.app_env.value,
            ai_mode=settings.ai_mode.value,
            storage=settings.storage_backend.value,
            job_kinds=registry.kinds(),
            attribution=ATTRIBUTION,
        )

    return app


app = create_app()
