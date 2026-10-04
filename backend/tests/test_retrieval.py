import pytest

from app.clients.jobdiva.mock import MockJobDivaTransport
from app.models.intent import LocationTarget, Requirement, SearchIntent, TitleTarget
from app.services.geo import same_state, state_code
from app.services.retrieval import build_talent_queries
from tests.conftest import make_client, make_settings


def _intent(state: str | None = "Alabama") -> SearchIntent:
    return SearchIntent(
        summary="",
        titles=[TitleTarget(title="Mechanical Design Engineer (CATIA)", synonyms=["Design Engineer"], source="job")],
        location=LocationTarget(
            city="Huntsville", state=state, zipcode=None, radius_mi=50, remote_ok=None, required=False, source="job"
        ),
        years=None,
        requirements=[
            Requirement(id="r1", text="CATIA V5", kind="skill", must_have=True, aliases=[], source="query"),
            Requirement(id="r2", text="GD&T", kind="skill", must_have=True, aliases=[], source="query"),
            Requirement(id="r3", text="AS9100", kind="keyword", must_have=False, aliases=[], source="job"),
        ],
        keywords=[],
        exclusions=[],
        preferences_from_notes=[],
        ambiguities=[],
    )


def test_state_codes():
    assert state_code("Alabama") == "AL" and state_code("al") == "AL" and state_code("Atlantis") is None
    assert same_state("Utah", "UT") and not same_state("UT", "TX")


def test_talent_queries_run_strict_to_broad_nationally():
    queries = build_talent_queries(_intent())
    assert [q.skills for q in queries[:3]] == [("CATIA V5",), ("GD&T",), ("AS9100",)]  # must-haves first
    assert all(len(q.skills) <= 1 for q in queries)  # ANDed multi-skill queries were 20–30 s live
    assert all(q.states == () for q in queries)  # location is ranked locally, not filtered in JobDiva
    titles = [q.title for q in queries if q.title]
    assert titles == ["Mechanical Design Engineer", "Design Engineer"]  # parenthetical skill dropped
    assert all(q.skills or q.title for q in queries)  # never an unfiltered TalentSearch


async def test_talent_search_refuses_an_unfiltered_query(tmp_path):
    client = make_client(make_settings(tmp_path))
    with pytest.raises(ValueError):
        await client.talent_search(resume_count=10)
    await client.aclose()


async def test_job_submittal_sweep_returns_every_submittal_and_is_cached(tmp_path):
    transport = MockJobDivaTransport()
    client = make_client(make_settings(tmp_path), transport)
    job_id = str(transport.ds.submittals[0]["job id in jd"])
    expected = {s["submittal id"] for s in transport.ds.submittals if str(s["job id in jd"]) == job_id}
    rows = await client.job_submittals(job_id)
    assert {r["submittalid"] for r in rows} == expected
    calls = len(transport.calls)
    await client.job_submittals(job_id)
    assert len(transport.calls) == calls  # served from the short-lived cache
    await client.aclose()


async def test_candidate_only_submittal_search_is_rejected_like_live_jobdiva(tmp_path):
    from app.clients.jobdiva.errors import JobDivaError

    client = make_client(make_settings(tmp_path))
    with pytest.raises(JobDivaError, match="missing job parameters"):
        await client.request("GET", "/api/jobdiva/searchSubmittal", params={"candidateid": "50000"})
    await client.aclose()
