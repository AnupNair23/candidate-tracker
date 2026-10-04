"""Intent analysis (step 1) and the streamed search (steps 2–8) for a job."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_deps
from app.api.sse import sse
from app.clients.claude_errors import ClaudeError
from app.clients.jobdiva.errors import JobDivaError
from app.constants.search import HEARTBEAT_S, SSE_HEADERS, STAGE_START
from app.core.errors import error_payload
from app.models.requests import IntentRequest, SearchRequest
from app.services.intent import parse_intent, stub_intent
from app.services.pipeline import run_search

log = logging.getLogger("app.api")
intent_router = APIRouter()
router = APIRouter()


@intent_router.post("/jobs/{job_id}/intent")
async def analyze(job_id: str, body: IntentRequest, request: Request) -> dict[str, Any]:
    d = get_deps(request)
    job = await d.jobs.get_job(job_id)
    if d.settings.llm_mode == "stub":
        intent = stub_intent(job, body.query)
    else:
        intent = await parse_intent(
            d.claude, job=job, query=body.query, notes=body.notes, effort=d.settings.claude_effort_intent
        )
    return {"job_id": job_id, "intent": intent.model_dump()}


@router.post("/jobs/{job_id}/search")
async def search(job_id: str, body: SearchRequest, request: Request) -> StreamingResponse:
    d = get_deps(request)
    search_id = uuid.uuid4().hex
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()
    tag = {"job_id": job_id, "search_id": search_id}

    async def emit(event: str, data: dict[str, Any]) -> None:
        await queue.put((event, {**data, **tag}))

    async def runner() -> None:
        try:
            result = await run_search(
                d,
                job_id=job_id,
                search_id=search_id,
                intent=body.intent,
                query=body.query,
                notes=body.notes,
                emit=emit,
            )
            await queue.put(("result", result.model_dump(mode="json")))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # surfaced as a typed error event
            if not isinstance(exc, JobDivaError | ClaudeError):
                log.exception("search %s failed", search_id)
            await queue.put(("error", {**error_payload(exc), **tag}))
        finally:
            await queue.put(None)

    task = asyncio.create_task(runner())

    async def stream():
        try:
            yield sse("stage", {"stage": STAGE_START, "message": "Search started", **tag})
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_S)
                except TimeoutError:
                    yield sse("heartbeat", tag)
                    continue
                if item is None:
                    break
                yield sse(*item)
        finally:
            if not task.done():
                task.cancel()  # client disconnected — stop JobDiva/Claude work

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)
