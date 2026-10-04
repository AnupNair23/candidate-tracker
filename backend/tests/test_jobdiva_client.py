import asyncio
import logging

import httpx
import pytest

from app.clients.jobdiva.client import CallBudget, JobDivaClient, normalize
from app.clients.jobdiva.errors import CallBudgetExhausted, JobDivaAuthError, JobDivaRateLimited
from app.clients.jobdiva.mock import MockJobDivaTransport
from app.core.logging import RedactQueryStrings
from app.services.jobs import JobsService
from tests.conftest import make_client, make_settings, no_sleep


def test_normalize_keys_across_endpoint_styles():
    assert normalize({"job title": "A", "CANDIDATEID": 1, "candidate id in jd": 2, "reference #": "BH-1"}) == {
        "jobtitle": "A",
        "candidateid": 1,
        "candidateidinjd": 2,
        "reference": "BH-1",
    }


async def test_auth_failure_triggers_single_reauth_for_concurrent_calls(tmp_path):
    settings = make_settings(tmp_path)
    transport = MockJobDivaTransport()
    client = make_client(settings, transport)
    await client.list_jobs_page(offset=0, max_returned=30)
    assert client.auth_calls == 1
    # Rotate the server-side token: every in-flight token is now stale.
    transport._token_version += 1
    results = await asyncio.gather(*(client.get_job("21000") for _ in range(5)))
    assert all(r and str(r["id"]) == "21000" for r in results)
    assert client.auth_calls == 2  # exactly one refresh despite 5 concurrent auth failures
    await client.aclose()


async def test_429_honours_retry_after_then_succeeds(tmp_path):
    settings = make_settings(tmp_path, jobdiva_max_retries=3)
    waits: list[float] = []

    async def record(seconds):
        waits.append(seconds)

    client = make_client(settings, MockJobDivaTransport(rate_limit_first=2))
    client.sleep = record
    rows = await client.list_jobs_page(offset=0, max_returned=30)
    assert len(rows) == 30
    assert waits[:2] == [0.0, 0.0]  # Retry-After: 0 from the mock
    await client.aclose()


async def test_persistent_429_raises_rate_limited(tmp_path):
    settings = make_settings(tmp_path, jobdiva_max_retries=2)
    client = make_client(settings, MockJobDivaTransport(rate_limit_first=10))
    with pytest.raises(JobDivaRateLimited) as info:
        await client.list_jobs_page(offset=0, max_returned=30)
    assert info.value.code == "rate_limited"
    assert info.value.retry_after is not None
    await client.aclose()


async def test_rejected_credentials_map_to_auth_error(tmp_path):
    settings = make_settings(
        tmp_path, jobdiva_mock=False, jobdiva_client_id="1", jobdiva_username="u", jobdiva_password="p"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Invalid username/password")

    client = JobDivaClient(settings, transport=httpx.MockTransport(handler))
    client.sleep = no_sleep
    with pytest.raises(JobDivaAuthError):
        await client.list_jobs_page(offset=0, max_returned=30)
    await client.aclose()


async def test_call_budget_is_enforced(tmp_path):
    client = make_client(make_settings(tmp_path))
    budget = CallBudget(1)
    await client.list_jobs_page(offset=0, max_returned=30, budget=budget)
    with pytest.raises(CallBudgetExhausted):
        await client.list_jobs_page(offset=30, max_returned=30, budget=budget)
    await client.aclose()


@pytest.mark.parametrize("page_size", [10, 20, 30, 40, 50])
async def test_ui_page_sizes_map_onto_jobdiva_pages_of_30(tmp_path, page_size):
    settings = make_settings(tmp_path)
    transport = MockJobDivaTransport()
    service = JobsService(make_client(settings, transport), settings)
    all_ids = [str(j["id"]) for j in transport.ds.jobs]  # 45 jobs
    seen: list[str] = []
    page = 1
    while True:
        result = await service.list_jobs(page, page_size)
        seen.extend(item["job_id"] for item in result["items"])
        if not result["has_next"]:
            break
        page += 1
    assert seen == all_ids
    offsets = {c for c in transport.calls if c == "/api/jobdiva/SearchJob"}
    assert offsets  # served from JobDiva pages of 30


def test_query_strings_are_redacted_from_logs():
    record = logging.LogRecord(
        "httpx",
        logging.INFO,
        __file__,
        1,
        "HTTP Request: GET %s",
        ("https://api.jobdiva.com/api/authenticate?clientid=1&username=a&password=secret",),
        None,
    )
    RedactQueryStrings().filter(record)
    assert "secret" not in record.getMessage()
    assert "?<redacted>" in record.getMessage()


async def test_jobdiva_validation_500_is_not_retried_and_message_is_surfaced(tmp_path):
    from app.clients.jobdiva.errors import JobDivaError, JobDivaUnavailable

    transport = MockJobDivaTransport()
    client = make_client(make_settings(tmp_path, jobdiva_max_retries=3), transport)
    with pytest.raises(JobDivaError) as info:
        await client.request("GET", "/api/jobdiva/searchSubmittal", params={"jobid": "21000"})
    assert not isinstance(info.value, JobDivaUnavailable)
    assert "please specify at least one candidate parameter" in info.value.message
    assert transport.calls.count("/api/jobdiva/searchSubmittal") == 1  # deterministic error: no retries
    # The job-level helper sends the candidate wildcard and succeeds.
    rows = await client.job_submittals("21000")
    assert isinstance(rows, list)
    await client.aclose()


async def test_linked_candidates_survive_one_failing_source(tmp_path, monkeypatch):
    from app.clients.jobdiva.errors import JobDivaUnavailable
    from app.services.candidates import linked_candidates

    client = make_client(make_settings(tmp_path))

    async def broken(*_a, **_k):
        raise JobDivaUnavailable("JobDiva returned HTTP 500 for /api/jobdiva/searchSubmittal", status=500)

    monkeypatch.setattr(client, "job_submittals", broken)
    result = await linked_candidates(client, "21000")
    assert result["warnings"] and "submittals" in result["warnings"][0]
    assert isinstance(result["items"], list)
    await client.aclose()
