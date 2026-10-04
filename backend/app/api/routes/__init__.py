"""HTTP API under /api. Every job/candidate payload echoes its `job_id` / `candidate_id` so the UI can verify
attachment."""

from fastapi import APIRouter

from app.api.routes import candidates, health, jobs, search
from app.constants.api import API_PREFIX

router = APIRouter(prefix=API_PREFIX)
router.include_router(health.router)
router.include_router(jobs.router)
router.include_router(search.intent_router)
router.include_router(candidates.router)
router.include_router(search.router)
