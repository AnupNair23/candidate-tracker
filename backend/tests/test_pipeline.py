import json

import pytest

from app.clients.claude_errors import ClaudeRateLimited
from app.clients.jobdiva.mock import MockJobDivaTransport
from app.services.intent import stub_intent
from app.services.pipeline import run_search
from tests.conftest import fake_claude, handles_in, make_client, make_deps, make_settings, requirement_ids


async def collect(_event, _data):
    return None


async def _intent(deps, job_id="21000", query="CATIA V5, GD&T, Aerospace structures, 3+ years"):
    job = await deps.jobs.get_job(job_id)
    it = stub_intent(job, query)
    it.requirements[0].must_have = True
    return it


async def test_stub_search_returns_valid_shortlist_and_overwrites_snapshot(tmp_path):
    settings = make_settings(tmp_path)
    jobdiva = make_client(settings)
    deps = make_deps(settings, jobdiva)
    it = await _intent(deps)

    r1 = await run_search(deps, job_id="21000", search_id="s1", intent=it, query="q", notes="", emit=collect)
    assert r1.job_id == "21000" and 0 < len(r1.shortlist) <= 30
    assert [e.rank for e in r1.shortlist] == list(range(1, len(r1.shortlist) + 1))
    pool_ids = set(json.loads(settings.snapshot_path.read_text())["records"])
    assert all(e.candidate_id in pool_ids for e in r1.shortlist)
    assert all(m.evidence for e in r1.shortlist for m in e.matched)  # every matched skill cites evidence

    r2 = await run_search(deps, job_id="21000", search_id="s2", intent=it, query="q2", notes="", emit=collect)
    snapshots = list(settings.snapshot_path.parent.glob("*.json"))
    assert snapshots == [settings.snapshot_path]  # one file, overwritten — never accumulates
    assert json.loads(settings.snapshot_path.read_text())["search_id"] == r2.search_id
    await jobdiva.aclose()


async def test_snapshot_replay_makes_no_jobdiva_calls(tmp_path):
    settings = make_settings(tmp_path)
    transport = MockJobDivaTransport()
    jobdiva = make_client(settings, transport)
    deps = make_deps(settings, jobdiva)
    it = await _intent(deps)
    await run_search(deps, job_id="21000", search_id="s1", intent=it, query="q", notes="", emit=collect)

    replay_settings = make_settings(tmp_path, snapshot_replay=True)
    calls_before = len(transport.calls)
    replay = await run_search(
        make_deps(replay_settings, jobdiva),
        job_id="21000",
        search_id="s3",
        intent=it,
        query="q",
        notes="",
        emit=collect,
    )
    assert replay.replayed and len(transport.calls) == calls_before
    await jobdiva.aclose()


def adversarial_responder(kwargs):
    """Fake Claude: claims every requirement 'met' citing the first evidence item, adds a fabricated
    candidate, cites another candidate's evidence, and asserts not_met without evidence."""
    cands = handles_in(kwargs)
    reqs = requirement_ids(kwargs)
    handles = list(cands)
    out = []
    for i, (handle, evidence) in enumerate(cands.items()):
        first = evidence[0][0] if evidence else f"{handle}-e01"
        other = f"{handles[(i + 1) % len(handles)]}-e01"
        verdicts = [{"requirement_id": r, "status": "met", "evidence_ids": [first]} for r in reqs[:-1]]
        verdicts.append({"requirement_id": reqs[-1], "status": "not_met", "evidence_ids": []})
        out.append(
            {
                "handle": handle,
                "verdicts": verdicts,
                "source_contributions": [
                    {"source": "profile", "effect": "positive", "summary": "s", "evidence_ids": [other]}
                ],
                "reason": "Looks great.",
                "concerns": [],
                "injection_suspected": False,
            }
        )
    out.append(
        {
            "handle": "c999",
            "verdicts": [],
            "source_contributions": [],
            "reason": "fabricated",
            "concerns": [],
            "injection_suspected": False,
        }
    )
    return "end_turn", json.dumps({"assessments": out})


async def test_claude_output_is_validated_before_display(tmp_path):
    settings = make_settings(tmp_path, llm_mode="claude", stage2_top_n=10)
    jobdiva = make_client(settings)
    claude, messages = fake_claude(settings, adversarial_responder)
    deps = make_deps(settings, jobdiva, claude)
    it = await _intent(deps)
    result = await run_search(deps, job_id="21000", search_id="s1", intent=it, query="q", notes="", emit=collect)

    assert messages.calls, "Claude was called"
    snap = json.loads(settings.snapshot_path.read_text())
    assert all(e.candidate_id in snap["records"] for e in result.shortlist)  # c999 never surfaces
    for entry in result.shortlist:
        assert not entry.contributions  # cross-candidate evidence removed → contribution dropped
        for m in entry.matched:
            assert m.status == "met"
            assert any(m.label.lower() in ev.quote.lower() for ev in m.evidence)  # text-supported claims only
        assert all(g.status in ("unknown", "unverified") for g in entry.gaps)  # not_met w/o evidence → unknown
    assert any("unknown handle" in i for i in snap["validation_issues"])
    # Prompts never contain names or contact details.
    sent = "\n".join(b["text"] for call in messages.calls for b in call["messages"][0]["content"])
    for rec in list(snap["records"].values())[:10]:
        for value in (rec["email"], rec["phone"], rec["last_name"]):
            if value:
                assert value not in sent
    await jobdiva.aclose()


async def test_truncated_batches_are_split_and_refusals_marked_not_assessed(tmp_path):
    settings = make_settings(tmp_path, llm_mode="claude", stage2_top_n=6, assess_batch_size=8)
    jobdiva = make_client(settings)
    state = {"refused": False}

    def responder(kwargs):
        cands = handles_in(kwargs)
        if len(cands) > 3:
            return "max_tokens", '{"assessments": ['
        if not state["refused"]:
            state["refused"] = True
            return "refusal", None
        reqs = requirement_ids(kwargs)
        out = [
            {
                "handle": h,
                "verdicts": [{"requirement_id": r, "status": "unknown", "evidence_ids": []} for r in reqs],
                "source_contributions": [],
                "reason": "r",
                "concerns": [],
                "injection_suspected": False,
            }
            for h in cands
        ]
        return "end_turn", json.dumps({"assessments": out})

    claude, messages = fake_claude(settings, responder)
    deps = make_deps(settings, jobdiva, claude)
    it = await _intent(deps)
    result = await run_search(deps, job_id="21000", search_id="s1", intent=it, query="q", notes="", emit=collect)
    assert len(messages.calls) >= 3  # first batch truncated → split into halves
    assert result.funnel.not_assessed_reasons.get("model_declined", 0) >= 1
    assert result.partial
    await jobdiva.aclose()


async def test_claude_rate_limit_propagates(tmp_path):
    settings = make_settings(tmp_path, llm_mode="claude", stage2_top_n=4)
    jobdiva = make_client(settings)

    class Limited:
        async def create(self, **_):
            raise ClaudeRateLimited("slow down", retry_after=7)

    from types import SimpleNamespace

    from app.clients.claude import ClaudeClient

    claude = ClaudeClient(settings, client=SimpleNamespace(beta=SimpleNamespace(messages=Limited())))
    deps = make_deps(settings, jobdiva, claude)
    it = await _intent(deps)
    with pytest.raises(ClaudeRateLimited):
        await run_search(deps, job_id="21000", search_id="s1", intent=it, query="q", notes="", emit=collect)
    await jobdiva.aclose()
