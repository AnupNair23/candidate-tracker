"""BI data path: live JobDiva formats (v1 tables, v2 objects) → resume text, work history, titles."""

import json

from app.clients.jobdiva.client import detabulate, normalize, unwrap
from app.services.candidates import profile
from app.services.intent import stub_intent
from app.services.pipeline import run_search
from tests.conftest import make_client, make_deps, make_settings


def test_v1_bi_tables_become_rows_and_empty_results_become_empty_lists():
    table = {"message": "ok", "data": [["ID", "FIRSTNAME"], [1, "Ada"], [2, "Bo"]]}
    assert unwrap(normalize(detabulate(table))) == [{"id": 1, "firstname": "Ada"}, {"id": 2, "firstname": "Bo"}]
    assert unwrap(normalize(detabulate({"message": "ok", "data": {}}))) == []
    objects = {"message": "ok", "data": [{"ID": 1, "EXPERIENCE": [{"DATE": "01/2020 - 02/2021"}]}]}
    assert unwrap(normalize(detabulate(objects))) == [{"id": 1, "experience": [{"date": "01/2020 - 02/2021"}]}]


async def _noop(*_):
    return None


async def test_search_loads_resume_text_work_history_and_titles_from_bi(tmp_path):
    settings = make_settings(tmp_path, jobdiva_use_bi=True)
    jobdiva = make_client(settings)
    deps = make_deps(settings, jobdiva)
    job = await deps.jobs.get_job("21000")
    intent = stub_intent(job, "CATIA V5, GD&T")
    result = await run_search(deps, job_id="21000", search_id="s", intent=intent, query="", notes="", emit=_noop)
    snap = json.loads(settings.snapshot_path.read_text())
    reviewed = [snap["records"][p["candidate_id"]] for p in snap["packets"].values()]
    assert reviewed and all(r["resume_text"] for r in reviewed)  # batched BI resume text
    assert all(r["work_history"] and r["title"] for r in reviewed)  # title from latest work history
    assert all("Work history" in p["rendered"] for p in snap["packets"].values())
    assert all(e.title for e in result.shortlist)
    await jobdiva.aclose()


async def test_drawer_profile_uses_bi_detail_and_work_history(tmp_path):
    settings = make_settings(tmp_path, jobdiva_use_bi=True)
    jobdiva = make_client(settings)
    data = await profile(jobdiva, settings, "50052", None)
    assert data["candidate_id"] == "50052" and data["title"] and data["email"]
    assert data["work_history_state"] == "ok" and data["work_history"][0]["period"]
    await jobdiva.aclose()
