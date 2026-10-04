"""Builds the per-process dependencies (JobDiva client, Claude client, jobs service) and exposes them to routes."""

from __future__ import annotations

from fastapi import Request

from app.clients.claude import ClaudeClient
from app.clients.jobdiva.client import JobDivaClient
from app.core.config import Settings
from app.models.pipeline import Deps
from app.services.jobs import JobsService


def build_jobdiva(settings: Settings) -> JobDivaClient:
    if settings.jobdiva_mock:
        from app.clients.jobdiva.mock import MockJobDivaTransport

        return JobDivaClient(settings, transport=MockJobDivaTransport())
    return JobDivaClient(settings)


def build_deps(settings: Settings, jobdiva: JobDivaClient) -> Deps:
    return Deps(settings=settings, jobdiva=jobdiva, claude=ClaudeClient(settings), jobs=JobsService(jobdiva, settings))


def get_deps(request: Request) -> Deps:
    return request.app.state.deps
