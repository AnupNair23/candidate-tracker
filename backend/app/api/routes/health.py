"""Health and configuration flags shown as the UI's dev-mode badge."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.api.deps import get_deps

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    d = get_deps(request)
    return {
        "ok": True,
        "jobdiva_configured": d.settings.jobdiva_configured,
        "jobdiva_mock": d.settings.jobdiva_mock,
        "llm_mode": d.settings.llm_mode,
        "claude_configured": d.claude.configured,
        "claude_model": d.settings.claude_model,
        "snapshot_replay": d.settings.snapshot_replay,
        "jobdiva_use_bi": d.settings.jobdiva_use_bi,
    }
