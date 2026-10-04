"""Jobs list, job detail and the candidates already linked to a job."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.deps import get_deps
from app.constants.api import JOBS_PAGE_SIZE_DEFAULT, JOBS_PAGE_SIZE_MAX, JOBS_PAGE_SIZE_MIN
from app.services import candidates as candidate_service

router = APIRouter()


@router.get("/jobs")
async def list_jobs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(JOBS_PAGE_SIZE_DEFAULT, ge=JOBS_PAGE_SIZE_MIN, le=JOBS_PAGE_SIZE_MAX),
) -> dict[str, Any]:
    return await get_deps(request).jobs.list_jobs(page, page_size)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict[str, Any]:
    job = await get_deps(request).jobs.get_job(job_id)
    return job.model_dump()


@router.get("/jobs/{job_id}/candidates")
async def job_candidates(job_id: str, request: Request) -> dict[str, Any]:
    d = get_deps(request)
    linked = await candidate_service.linked_candidates(d.jobdiva, job_id, d.settings.jobdiva_page_size)
    return {"job_id": job_id, **linked}
