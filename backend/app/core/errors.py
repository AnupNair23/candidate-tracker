"""Mapping from domain errors (JobDiva, Claude) to HTTP status codes and the typed error payload the UI reads."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.clients.claude_errors import ClaudeAuthError, ClaudeError, ClaudeNotConfigured, ClaudeRateLimited
from app.clients.jobdiva.errors import (
    JobDivaAuthError,
    JobDivaError,
    JobDivaNotConfigured,
    JobDivaNotFound,
    JobDivaRateLimited,
)


def error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, JobDivaError | ClaudeError):
        source = "jobdiva" if isinstance(exc, JobDivaError) else "claude"
        return {"code": exc.code, "message": exc.message, "source": source, "retry_after": exc.retry_after}
    return {"code": "internal_error", "message": "Unexpected server error", "source": "server", "retry_after": None}


def status_for(exc: Exception) -> int:
    if isinstance(exc, JobDivaRateLimited | ClaudeRateLimited):
        return 429
    if isinstance(exc, JobDivaNotFound):
        return 404
    if isinstance(exc, JobDivaNotConfigured | ClaudeNotConfigured):
        return 503
    if isinstance(exc, JobDivaAuthError | ClaudeAuthError):
        return 502
    return 502


async def upstream_error(_: Request, exc: Exception) -> JSONResponse:
    payload = error_payload(exc)
    headers = {"Retry-After": str(int(payload["retry_after"]))} if payload.get("retry_after") else None
    return JSONResponse({"error": payload}, status_code=status_for(exc), headers=headers)
