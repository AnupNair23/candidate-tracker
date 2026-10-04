import json

import httpx
from asgi_lifespan import LifespanManager

from app.clients.jobdiva.mock import MockJobDivaTransport
from app.main import app
from app.services.intent import stub_intent
from tests.conftest import make_client, make_deps, make_settings


async def _client(tmp_path, transport=None, **overrides):
    settings = make_settings(tmp_path, **overrides)
    jobdiva = make_client(settings, transport)
    return settings, jobdiva


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for frame in body.strip().split("\n\n"):
        event, data = "message", None
        for line in frame.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:])
        if data is not None:
            events.append((event, data))
    return events


async def run_app(tmp_path, transport=None, **overrides):
    settings, jobdiva = await _client(tmp_path, transport, **overrides)
    lm = LifespanManager(app)
    await lm.__aenter__()
    app.state.deps = make_deps(settings, jobdiva)
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60)
    return lm, http, jobdiva


async def test_search_stream_tags_every_event_with_job_and_search_id(tmp_path):
    lm, http, jobdiva = await run_app(tmp_path)
    try:
        job = await app.state.deps.jobs.get_job("21000")
        intent = stub_intent(job, "CATIA V5, GD&T").model_dump()
        resp = await http.post("/api/jobs/21000/search", json={"intent": intent, "query": "", "notes": ""})
        assert resp.status_code == 200
        events = parse_sse(resp.text)
        kinds = [e for e, _ in events]
        assert kinds[0] == "stage" and kinds[-1] == "result"
        search_ids = {d["search_id"] for _, d in events}
        assert {d["job_id"] for _, d in events} == {"21000"} and len(search_ids) == 1
    finally:
        await http.aclose()
        await lm.__aexit__(None, None, None)
        await jobdiva.aclose()


async def test_persistent_jobdiva_429_ends_stream_with_rate_limited_error(tmp_path):
    transport = MockJobDivaTransport()
    lm, http, jobdiva = await run_app(tmp_path, transport, jobdiva_max_retries=1)
    try:
        job = await app.state.deps.jobs.get_job("21000")
        intent = stub_intent(job, "CATIA V5").model_dump()
        transport._rate_limit_left = 1000
        resp = await http.post("/api/jobs/21000/search", json={"intent": intent, "query": "", "notes": ""})
        events = parse_sse(resp.text)
        event, data = events[-1]
        assert event == "error"
        assert data["code"] == "rate_limited" and data["source"] == "jobdiva"
        assert data["retry_after"] is not None and data["job_id"] == "21000"
    finally:
        await http.aclose()
        await lm.__aexit__(None, None, None)
        await jobdiva.aclose()


async def test_rest_errors_are_typed(tmp_path):
    transport = MockJobDivaTransport()
    lm, http, jobdiva = await run_app(tmp_path, transport, jobdiva_max_retries=0)
    try:
        assert (await http.get("/api/jobs", params={"page_size": 5})).status_code == 422
        missing = await http.get("/api/jobs/1")
        assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"
        transport._rate_limit_left = 5
        limited = await http.get("/api/jobs")
        assert limited.status_code == 429 and limited.json()["error"]["code"] == "rate_limited"
        assert "Retry-After" in limited.headers or limited.json()["error"]["retry_after"] is not None
    finally:
        await http.aclose()
        await lm.__aexit__(None, None, None)
        await jobdiva.aclose()
