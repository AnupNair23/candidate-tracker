"""Live candidate data for the drawer: profile, interactions and resume."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.deps import get_deps
from app.constants.api import NAME_HINT_MAX_CHARS
from app.services import candidates as candidate_service

router = APIRouter()


@router.get("/candidates/{candidate_id}")
async def candidate_profile(
    candidate_id: str, request: Request, name: str | None = Query(None, max_length=NAME_HINT_MAX_CHARS)
) -> dict[str, Any]:
    d = get_deps(request)
    return await candidate_service.profile(d.jobdiva, d.settings, candidate_id, name)


@router.get("/candidates/{candidate_id}/interactions")
async def candidate_interactions(
    candidate_id: str, request: Request, job_id: str | None = Query(None, max_length=NAME_HINT_MAX_CHARS)
) -> dict[str, Any]:
    d = get_deps(request)
    return await candidate_service.interactions(d.jobdiva, d.settings, candidate_id, job_id)


@router.get("/candidates/{candidate_id}/resume")
async def candidate_resume(candidate_id: str, request: Request) -> dict[str, Any]:
    d = get_deps(request)
    return await candidate_service.resume(d.jobdiva, d.settings, candidate_id)
