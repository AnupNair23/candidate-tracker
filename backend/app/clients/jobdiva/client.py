"""Async client for the JobDiva REST API, Version 1 (`/api/...`).

- Auth: `GET /api/authenticate` returns a bare token, sent as `Authorization: Bearer <token>`.
  v1 has no refresh endpoint, so "refresh" means re-authenticating. Any auth-header failure
  triggers exactly one single-flight refresh, then one retry of the call.
- 429: honours Retry-After (else exponential backoff with jitter) up to `jobdiva_max_retries`,
  then raises `JobDivaRateLimited` so the UI can offer "Retry search".
- Keys are normalized (lowercase, alphanumerics only) because BI endpoints return UPPERCASE keys
  wrapped in `{message, data}` while standard endpoints use lowercase keys containing spaces.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections.abc import Iterable, Sequence
from typing import Any

import httpx

from app.clients.jobdiva.errors import (
    CallBudgetExhausted,
    JobDivaAuthError,
    JobDivaError,
    JobDivaNotConfigured,
    JobDivaNotFound,
    JobDivaRateLimited,
    JobDivaUnavailable,
)
from app.constants.jobdiva import (
    AUTH_FAILURE_MARKERS,
    AUTH_FAILURE_SCAN_CHARS,
    AUTHENTICATE_PATH,
    BACKOFF_JITTER_S,
    BATCH_SIZE,
    BI_CANDIDATE_EXPERIENCE_PATH,
    BI_CANDIDATE_NOTES_PATH,
    BI_CANDIDATES_RESUMES_PATH,
    BI_RESUME_DETAIL_PATH,
    CREDENTIALS_REJECTED_MARKERS,
    DEFAULT_MAX_RETURNED,
    ERROR_MESSAGE_CHARS,
    OPEN_JOB_STATUS,
    QUICK_CANDIDATE_SEARCH_PATH,
    QUICK_SEARCH_MAX_RETURNED,
    SEARCH_CANDIDATE_PROFILE_PATH,
    SEARCH_JOB_PATH,
    SEARCH_START_PATH,
    SEARCH_SUBMITTAL_PATH,
    SUBMITTAL_CANDIDATE_WILDCARD,
    UNIVERSAL_SEARCH_PATH,
    VALIDATION_ERROR_PREFIXES,
)
from app.core.config import Settings

log = logging.getLogger("app.jobdiva")

_KEY_RE = re.compile(r"[^a-z0-9]")


def normalize_key(key: Any) -> str:
    return _KEY_RE.sub("", str(key).lower())


def normalize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {normalize_key(k): normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize(v) for v in obj]
    return obj


def unwrap(payload: Any) -> Any:
    """BI endpoints wrap rows as {message, data: [...]}; return the rows."""
    if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], list | dict):
        return payload["data"]
    return payload


def as_list(payload: Any) -> list[dict]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def chunks(items: Sequence[str], size: int = BATCH_SIZE) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield list(items[i : i + size])


def error_message(resp: httpx.Response) -> str | None:
    """JobDiva (Spring Boot) error bodies look like {"status":500,"error":"...","message":"Error: ..."}."""
    try:
        body = resp.json()
    except ValueError:
        text = resp.text.strip()
        return text[:ERROR_MESSAGE_CHARS] or None
    if isinstance(body, dict):
        msg = body.get("message") or body.get("error")
        return str(msg)[:ERROR_MESSAGE_CHARS] if msg else None
    return None


def is_validation_error(message: str | None) -> bool:
    """JobDiva reports bad/missing parameters as HTTP 500 with a message starting "Error:". Retrying won't help."""
    return bool(message) and message.lower().startswith(VALIDATION_ERROR_PREFIXES)


class CallBudget:
    """Caps the number of JobDiva calls a single search may make (retries included)."""

    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0

    @property
    def exhausted(self) -> bool:
        return self.used >= self.limit

    def consume(self) -> None:
        if self.used >= self.limit:
            raise CallBudgetExhausted(f"JobDiva call budget of {self.limit} calls exhausted")
        self.used += 1


class JobDivaClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._s = settings
        self._http = httpx.AsyncClient(
            base_url=settings.jobdiva_base_url,
            timeout=settings.jobdiva_timeout_s,
            transport=transport,
        )
        self._token: str | None = None
        self._auth_lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(max(1, settings.jobdiva_max_concurrency))
        self._pace_lock = asyncio.Lock()
        self._last_start = 0.0
        self.auth_calls = 0
        self.sleep = asyncio.sleep  # injectable for tests

    async def aclose(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------ auth

    async def _authenticate(self) -> str:
        s = self._s
        if not s.jobdiva_configured:
            raise JobDivaNotConfigured(
                "JobDiva credentials are not configured (JOBDIVA_CLIENT_ID / JOBDIVA_USERNAME / JOBDIVA_PASSWORD)"
            )
        self.auth_calls += 1
        params = {
            "clientid": s.jobdiva_client_id,
            "username": s.jobdiva_username,
            "password": s.jobdiva_password.get_secret_value() if s.jobdiva_password else "",
        }
        try:
            resp = await self._http.get(AUTHENTICATE_PATH, params=params)
        except httpx.TransportError as exc:
            raise JobDivaUnavailable(f"Could not reach JobDiva: {type(exc).__name__}") from exc
        log.info("jobdiva auth status=%s uuid=%s", resp.status_code, resp.headers.get("X-LI-UUID"))
        body = resp.text.strip()
        if resp.status_code == 200 and body:
            return body.strip('"')
        if resp.status_code == 429:
            raise JobDivaRateLimited(
                "JobDiva is rate-limiting authentication", status=429, retry_after=self._retry_after(resp, 0)
            )
        lowered = body.lower()
        if resp.status_code in (401, 403) or any(marker in lowered for marker in CREDENTIALS_REJECTED_MARKERS):
            raise JobDivaAuthError("JobDiva credentials rejected", status=resp.status_code)
        raise JobDivaUnavailable(f"JobDiva authentication failed (HTTP {resp.status_code})", status=resp.status_code)

    async def _current_token(self) -> str:
        if self._token:
            return self._token
        async with self._auth_lock:
            if not self._token:
                self._token = await self._authenticate()
            return self._token

    async def _refresh(self, stale: str) -> str:
        """Single-flight: concurrent callers holding the same stale token trigger one re-auth."""
        async with self._auth_lock:
            if self._token and self._token != stale:
                return self._token
            self._token = None
            self._token = await self._authenticate()
            return self._token

    def invalidate_token(self) -> None:
        """Force re-authentication on the next call (credential/token rotation)."""
        self._token = None

    @staticmethod
    def _is_auth_failure(resp: httpx.Response) -> bool:
        if resp.status_code in (401, 403):
            return True
        if resp.status_code >= 400:
            text = resp.text[:AUTH_FAILURE_SCAN_CHARS].lower()
            return any(marker in text for marker in AUTH_FAILURE_MARKERS)
        return False

    # ------------------------------------------------------------- transport

    def _retry_after(self, resp: httpx.Response | None, attempt: int) -> float:
        if resp is not None:
            header = resp.headers.get("Retry-After")
            if header:
                try:
                    return max(0.0, float(header))
                except ValueError:
                    pass
        return self._s.jobdiva_backoff_base_s * (2**attempt) + random.uniform(0, BACKOFF_JITTER_S)

    async def _pace(self) -> None:
        async with self._pace_lock:
            now = time.monotonic()
            wait = self._last_start + self._s.jobdiva_min_interval_s - now
            if wait > 0:
                await self.sleep(wait)
            self._last_start = time.monotonic()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        budget: CallBudget | None = None,
    ) -> Any:
        refreshed = False
        attempt = 0
        max_retries = self._s.jobdiva_max_retries
        while True:
            if budget is not None:
                budget.consume()
            token = await self._current_token()
            started = time.monotonic()
            async with self._sem:
                await self._pace()
                try:
                    resp = await self._http.request(
                        method, path, params=params, json=json, headers={"Authorization": f"Bearer {token}"}
                    )
                except httpx.TransportError as exc:
                    resp = None
                    transport_error: Exception | None = exc
                else:
                    transport_error = None

            if resp is None:
                if attempt < max_retries:
                    attempt += 1
                    await self.sleep(self._retry_after(None, attempt - 1))
                    continue
                raise JobDivaUnavailable(f"Could not reach JobDiva: {type(transport_error).__name__}")

            message = error_message(resp) if resp.status_code >= 400 else None
            log.info(
                "jobdiva %s %s status=%s ms=%d uuid=%s%s",
                method,
                path,
                resp.status_code,
                (time.monotonic() - started) * 1000,
                resp.headers.get("X-LI-UUID"),
                f" message={message!r}" if message else "",
            )

            if self._is_auth_failure(resp):
                if not refreshed:
                    refreshed = True
                    await self._refresh(token)
                    continue
                if resp.status_code == 403:
                    raise JobDivaAuthError(f"JobDiva API user is not permitted to call {path}", status=403)
                raise JobDivaAuthError("JobDiva rejected the API token after re-authenticating", status=401)

            if resp.status_code == 429:
                wait = self._retry_after(resp, attempt)
                if attempt < max_retries:
                    attempt += 1
                    await self.sleep(wait)
                    continue
                raise JobDivaRateLimited("JobDiva is rate-limiting requests", status=429, retry_after=wait)

            if resp.status_code >= 500 and is_validation_error(message):
                raise JobDivaError(f"JobDiva rejected the request to {path}: {message}", status=resp.status_code)

            if resp.status_code >= 500:
                if attempt < max_retries:
                    attempt += 1
                    await self.sleep(self._retry_after(resp, attempt - 1))
                    continue
                detail = f": {message}" if message else ""
                raise JobDivaUnavailable(
                    f"JobDiva returned HTTP {resp.status_code} for {path}{detail}", status=resp.status_code
                )

            if resp.status_code == 404:
                raise JobDivaNotFound(f"JobDiva has no resource at {path}", status=404)
            if resp.status_code >= 400:
                detail = f": {message}" if message else ""
                raise JobDivaError(
                    f"JobDiva returned HTTP {resp.status_code} for {path}{detail}", status=resp.status_code
                )
            return self._decode(resp)

    @staticmethod
    def _decode(resp: httpx.Response) -> Any:
        if not resp.content:
            return None
        try:
            payload = resp.json()
        except ValueError:
            return resp.text
        return unwrap(normalize(payload))

    # ------------------------------------------------------------- endpoints
    # Standard v1 endpoints (/api/jobdiva/...); paths live in app.constants.jobdiva. Parameter casing is exactly as
    # in the v1 spec.

    async def list_jobs_page(self, *, offset: int, max_returned: int, budget: CallBudget | None = None) -> list[dict]:
        params = {"status": OPEN_JOB_STATUS, "showAllOpenJobs": "true", "offset": offset, "maxReturned": max_returned}
        return as_list(await self.request("GET", SEARCH_JOB_PATH, params=params, budget=budget))

    async def get_job(self, job_id: str) -> dict | None:
        rows = as_list(await self.request("GET", SEARCH_JOB_PATH, params={"jobId": job_id}))
        # SearchJob can return an unrelated job for bad input — require an exact id match.
        return next((r for r in rows if str(r.get("id") or r.get("jobid")) == str(job_id)), None)

    async def job_submittals(self, job_id: str, budget: CallBudget | None = None) -> list[dict]:
        # searchSubmittal rejects a job-only search ("please specify at least one candidate parameter"), so a
        # wildcard last name is sent alongside jobid. JobDiva accepts it (HTTP 200); confirm against a job that
        # has submittals that it returns them all.
        params = {"jobid": job_id, **SUBMITTAL_CANDIDATE_WILDCARD}
        return as_list(await self.request("GET", SEARCH_SUBMITTAL_PATH, params=params, budget=budget))

    async def job_starts(
        self, job_id: str, *, offset: int, max_returned: int, budget: CallBudget | None = None
    ) -> list[dict]:
        params = {"jobId": job_id, "offset": offset, "maxreturned": max_returned}
        return as_list(await self.request("GET", SEARCH_START_PATH, params=params, budget=budget))

    async def universal_search(
        self, criteria: str, *, offset: int, max_returned: int, budget: CallBudget | None = None
    ) -> tuple[list[dict], int | None]:
        body = {
            "criteria": criteria,
            "includeCandidates": True,
            "includeJobs": False,
            "includeContacts": False,
            "includeCompanies": False,
            "includeNotes": False,
            "includeContactNotes": False,
            "includeOpportunity": False,
            "maxReturned": max_returned,
            "offset": offset,
            "supportFuzzyMatching": False,
        }
        data = await self.request("POST", UNIVERSAL_SEARCH_PATH, json=body, budget=budget)
        cores = as_list(data)
        core = next((c for c in cores if "candidate" in str(c.get("corename", "")).lower()), None)
        if core is None and len(cores) == 1:
            core = cores[0]
        if core is None:
            return [], 0
        docs = as_list(core.get("documents"))
        found = core.get("numfound")
        return docs, int(found) if str(found).isdigit() else None

    async def quick_candidate_search(
        self, criteria: str, *, max_returned: int = QUICK_SEARCH_MAX_RETURNED
    ) -> list[dict]:
        params = {"criteria": criteria, "maxReturned": max_returned}
        return as_list(await self.request("GET", QUICK_CANDIDATE_SEARCH_PATH, params=params))

    async def search_candidate_profile(
        self,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        city: str | None = None,
        state: str | None = None,
        zipcode: str | None = None,
        offset: int = 0,
        max_returned: int = DEFAULT_MAX_RETURNED,
        budget: CallBudget | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {"offset": offset, "maxreturned": max_returned}
        for key, value in (
            ("firstName", first_name),
            ("lastName", last_name),
            ("city", city),
            ("state", state),
            ("zipCode", zipcode),
        ):
            if value:
                params[key] = value
        return as_list(await self.request("POST", SEARCH_CANDIDATE_PROFILE_PATH, params=params, budget=budget))

    async def candidate_submittals(self, candidate_id: str, budget: CallBudget | None = None) -> list[dict]:
        return as_list(
            await self.request("GET", SEARCH_SUBMITTAL_PATH, params={"candidateid": candidate_id}, budget=budget)
        )

    async def candidate_starts(
        self, candidate_id: str, *, max_returned: int = DEFAULT_MAX_RETURNED, budget: CallBudget | None = None
    ) -> list[dict]:
        params = {"candidateid": candidate_id, "offset": 0, "maxreturned": max_returned}
        return as_list(await self.request("GET", SEARCH_START_PATH, params=params, budget=budget))

    # Optional BI endpoints (/api/bi/...) — only called when JOBDIVA_USE_BI=true. They are the only v1
    # source for candidate notes, resume text and work history.

    async def bi_candidate_notes(self, candidate_id: str, budget: CallBudget | None = None) -> list[dict]:
        return as_list(
            await self.request("GET", BI_CANDIDATE_NOTES_PATH, params={"candidateId": candidate_id}, budget=budget)
        )

    async def bi_candidate_resume_ids(
        self, candidate_ids: Sequence[str], budget: CallBudget | None = None
    ) -> list[dict]:
        rows: list[dict] = []
        for chunk in chunks(list(candidate_ids)):
            rows.extend(
                as_list(
                    await self.request("GET", BI_CANDIDATES_RESUMES_PATH, params={"candidateIds": chunk}, budget=budget)
                )
            )
        return rows

    async def bi_resume_detail(self, resume_id: str, budget: CallBudget | None = None) -> dict | None:
        rows = as_list(await self.request("GET", BI_RESUME_DETAIL_PATH, params={"resumeId": resume_id}, budget=budget))
        return rows[0] if rows else None

    async def bi_candidate_experience(self, candidate_id: str) -> list[dict]:
        return as_list(await self.request("GET", BI_CANDIDATE_EXPERIENCE_PATH, params={"employeeId": candidate_id}))
