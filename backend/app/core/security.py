"""HTTP basic auth as a pure ASGI middleware: guards the API, the SSE stream and the static UI without buffering
responses. `GET /healthz` is the only path served without credentials (Render's health check)."""

from __future__ import annotations

import base64
import binascii
import secrets

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.constants.deploy import BASIC_AUTH_REALM, HEALTHZ_PATH


def _credentials(scope: Scope) -> tuple[bytes, bytes] | None:
    """(user, password) from the request's `Authorization: Basic …` header, or None if absent or malformed."""
    header = next((v for k, v in scope.get("headers", ()) if k == b"authorization"), None)
    if header is None:
        return None
    scheme, _, token = header.partition(b" ")
    if scheme.lower() != b"basic":
        return None
    try:
        decoded = base64.b64decode(token.strip(), validate=True)
    except (binascii.Error, ValueError):
        return None
    user, sep, password = decoded.partition(b":")
    return (user, password) if sep else None


class BasicAuthMiddleware:
    def __init__(self, app: ASGIApp, *, username: str, password: str, realm: str = BASIC_AUTH_REALM) -> None:
        self.app = app
        self._user = username.encode()
        self._password = password.encode()
        self._challenge = PlainTextResponse(
            "Unauthorized", status_code=401, headers={"WWW-Authenticate": f'Basic realm="{realm}"'}
        )

    def _authorized(self, scope: Scope) -> bool:
        creds = _credentials(scope)
        if creds is None:
            return False
        user_ok = secrets.compare_digest(creds[0], self._user)
        password_ok = secrets.compare_digest(creds[1], self._password)
        return user_ok and password_ok

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "http" and scope["method"] == "GET" and scope["path"] == HEALTHZ_PATH:
            await self.app(scope, receive, send)
            return
        if self._authorized(scope):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await self._challenge(scope, receive, send)
