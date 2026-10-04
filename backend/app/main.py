"""FastAPI app: logging, lifespan-managed dependencies, CORS, the /api router and upstream-error handlers."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import build_deps, build_jobdiva
from app.api.routes import router
from app.clients.claude_errors import ClaudeError
from app.clients.jobdiva.errors import JobDivaError
from app.constants.api import CORS_ALLOW_METHODS
from app.core.config import get_settings
from app.core.errors import upstream_error
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    jobdiva = build_jobdiva(settings)
    app.state.deps = build_deps(settings, jobdiva)
    try:
        yield
    finally:
        await jobdiva.aclose()


configure_logging()
app = FastAPI(title="Ascendia sourcing agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=CORS_ALLOW_METHODS,
    allow_headers=["*"],
)
app.include_router(router)
app.add_exception_handler(ClaudeError, upstream_error)
app.add_exception_handler(JobDivaError, upstream_error)
