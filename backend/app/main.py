"""FastAPI app: logging, lifespan-managed dependencies, basic auth, CORS, the /api router, upstream-error handlers,
the /healthz probe and (when FRONTEND_DIST is set) the built SPA."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.deps import build_deps, build_jobdiva
from app.api.routes import router
from app.clients.claude_errors import ClaudeError
from app.clients.jobdiva.errors import JobDivaError
from app.constants.api import API_PREFIX, CORS_ALLOW_METHODS
from app.constants.deploy import HEALTHZ_PATH, SPA_INDEX
from app.core.config import Settings, get_settings
from app.core.errors import upstream_error
from app.core.logging import configure_logging
from app.core.security import BasicAuthMiddleware

log = logging.getLogger("app.main")


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve files from `dist`; any other non-/api GET returns index.html so client-side routes survive a refresh.
    Registered after the API router, so /api routes keep priority."""
    root = dist.resolve()
    index = root / SPA_INDEX
    api = API_PREFIX.strip("/")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path == api or path.startswith(f"{api}/"):
            raise HTTPException(status_code=404)
        file = (root / path).resolve()
        if path and file.is_file() and file.is_relative_to(root):
            return FileResponse(file)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not settings.basic_auth_enabled and not settings.jobdiva_mock:
            log.warning("BASIC_AUTH_USER / BASIC_AUTH_PASSWORD unset: the app is open to anyone who can reach it")
        jobdiva = build_jobdiva(settings)
        app.state.deps = build_deps(settings, jobdiva)
        try:
            yield
        finally:
            await jobdiva.aclose()

    app = FastAPI(title="Ascendia sourcing agent", lifespan=lifespan)
    if settings.basic_auth_enabled:
        # Added before CORS so CORS stays outermost (preflights and 401s carry CORS headers).
        app.add_middleware(
            BasicAuthMiddleware,
            username=settings.basic_auth_user,
            password=settings.basic_auth_password.get_secret_value(),
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=CORS_ALLOW_METHODS,
        allow_headers=["*"],
    )
    app.include_router(router)
    app.add_exception_handler(ClaudeError, upstream_error)
    app.add_exception_handler(JobDivaError, upstream_error)

    @app.get(HEALTHZ_PATH, include_in_schema=False)
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    if settings.frontend_dist is not None:
        if (settings.frontend_dist / SPA_INDEX).is_file():
            mount_frontend(app, settings.frontend_dist)
        else:
            log.warning("FRONTEND_DIST=%s has no %s; not serving the UI", settings.frontend_dist, SPA_INDEX)
    return app


configure_logging()
app = create_app()
