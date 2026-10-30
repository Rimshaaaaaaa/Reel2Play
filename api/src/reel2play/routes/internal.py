"""Internal endpoints behind the cron secret: the cron tick and the model check."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from reel2play.ai.health import RoleCheck, check_roles
from reel2play.deps import AIDep, CronGuard, SessionDep, SettingsDep
from reel2play.jobs.queue import recover_stale, run_due
from reel2play.jobs.worker import worker_id

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[CronGuard])


class CronResult(BaseModel):
    recovered: int
    ran: int


@router.post("/cron")
def cron_tick(session: SessionDep, settings: SettingsDep) -> CronResult:
    """Called by cron-job.org: wakes the free Render service and drains due jobs."""
    recovered = recover_stale(session, settings.job_stale_after_seconds)
    session.commit()
    ran = run_due(f"cron:{worker_id()}", max_jobs=5, time_budget_s=25)
    return CronResult(recovered=recovered, ran=ran)


@router.post("/model-check")
def model_check(ai: AIDep) -> list[RoleCheck]:
    """Ask every role's endpoint chain for a one-word answer, to verify keys and failover."""
    return check_roles(ai)
