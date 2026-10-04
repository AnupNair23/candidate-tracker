"""Jobs list (UI pages of 10–50 mapped onto JobDiva pages of 30) and job detail."""

from __future__ import annotations

import time

import bleach

from app.clients.jobdiva.client import JobDivaClient
from app.clients.jobdiva.errors import JobDivaNotFound
from app.clients.jobdiva.mappers import map_job
from app.constants.jobs import DESCRIPTION_ALLOWED_TAGS
from app.core.config import Settings
from app.models.jobdiva import Job


def sanitize_html(value: str | None) -> str | None:
    if not value:
        return None
    return bleach.clean(value, tags=DESCRIPTION_ALLOWED_TAGS, attributes={}, strip=True)


class JobsService:
    def __init__(self, client: JobDivaClient, settings: Settings):
        self._client = client
        self._s = settings
        self._pages: dict[int, tuple[float, list[dict]]] = {}

    async def _jobdiva_page(self, index: int) -> list[dict]:
        size = self._s.jobdiva_page_size
        cached = self._pages.get(index)
        if cached and time.monotonic() - cached[0] < self._s.jobdiva_jobs_cache_ttl_s:
            return cached[1]
        rows = await self._client.list_jobs_page(offset=index * size, max_returned=size)
        self._pages[index] = (time.monotonic(), rows)
        return rows

    async def list_jobs(self, page: int, page_size: int) -> dict:
        size = self._s.jobdiva_page_size
        start = (page - 1) * page_size
        end = start + page_size
        first, last = start // size, (end - 1) // size
        rows: list[dict] = []
        last_full = False
        for index in range(first, last + 1):
            chunk = await self._jobdiva_page(index)
            rows.extend(chunk)
            last_full = len(chunk) == size
            if not last_full:
                break
        window = rows[start - first * size : end - first * size]
        consumed = first * size + len(rows)
        has_next = consumed > end or (consumed == end and last_full)
        items = [j for j in (map_job(r) for r in window) if j is not None]
        return {
            "items": [
                {k: v for k, v in j.model_dump().items() if k not in ("description_html", "description_text")}
                for j in items
            ],
            "page": page,
            "page_size": page_size,
            "has_next": has_next,
        }

    async def get_job(self, job_id: str) -> Job:
        row = await self._client.get_job(job_id)
        job = map_job(row) if row else None
        if job is None or job.job_id != str(job_id):
            raise JobDivaNotFound(f"Job {job_id} was not found in JobDiva", status=404)
        job.description_html = sanitize_html(job.description_html)
        return job
