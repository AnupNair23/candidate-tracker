"""Search orchestration: retrieve → pre-score → hydrate → assess (Claude) → validate → rank → explain.

Emits typed progress events through `emit`. Writes the per-search snapshot (overwritten each search).
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import UTC, datetime

from app.clients.jobdiva.client import CallBudget
from app.constants.search import (
    STAGE_ASSESS,
    STAGE_HYDRATE,
    STAGE_JOB,
    STAGE_PRESCREEN,
    STAGE_RETRIEVE,
    STAGE_VALIDATE,
)
from app.core.config import Settings
from app.models.intent import SearchIntent
from app.models.jobdiva import CandidateRecord, Job
from app.models.pipeline import Deps, Emit, Pool
from app.models.results import Funnel, QueryStat, RequirementFailure, SearchResult
from app.services.assess import assess_all, assessment_requirements, build_job_block, build_packet
from app.services.hydrate import enrich_stage2
from app.services.intent import normalize_intent
from app.services.prescore import prescore, prescore_pool, select_for_review
from app.services.retrieval import retrieve
from app.services.scoring import score_assessment, to_entry
from app.services.shortfall import explain
from app.services.snapshot import read_snapshot, write_snapshot

log = logging.getLogger("app.pipeline")


def _load_replay(settings: Settings, job_id: str) -> tuple[Job, Pool] | None:
    snap = read_snapshot(settings.snapshot_path)
    if not snap or snap.get("job_id") != job_id or not snap.get("records"):
        return None
    job = Job.model_validate(snap["job"])
    pool = Pool(
        records={cid: CandidateRecord.model_validate(r) for cid, r in snap["records"].items()},
        queries=[QueryStat.model_validate(q) for q in snap.get("queries", [])],
        partial=bool(snap.get("retrieval_partial")),
        warnings=["Replayed from the last search snapshot — JobDiva was not called."],
    )
    return job, pool


async def run_search(
    deps: Deps, *, job_id: str, search_id: str, intent: SearchIntent, query: str, notes: str, emit: Emit
) -> SearchResult:
    s = deps.settings
    started = time.monotonic()
    deadline = started + s.search_deadline_s
    intent = normalize_intent(intent)
    reqs = assessment_requirements(intent)

    replay = _load_replay(s, job_id) if s.snapshot_replay else None
    if replay is not None:
        job, pool = replay
        await emit(
            "stage", {"stage": STAGE_RETRIEVE, "message": f"Replaying {len(pool.records)} candidates from snapshot"}
        )
    else:
        await emit("stage", {"stage": STAGE_JOB, "message": "Loading the job from JobDiva"})
        job = await deps.jobs.get_job(job_id)
        budget = CallBudget(s.search_call_budget)
        await emit("stage", {"stage": STAGE_RETRIEVE, "message": "Searching JobDiva"})
        pool = await retrieve(deps.jobdiva, intent, job, s, budget, emit)
        await emit("stage", {"stage": STAGE_PRESCREEN, "message": f"Pre-screening {len(pool.records)} candidates"})

    scores = await prescore_pool(pool, intent, job)
    selected, prescreened_out, excluded = select_for_review(pool, scores, s.stage2_top_n)

    if replay is None and selected:
        await emit(
            "stage",
            {"stage": STAGE_HYDRATE, "message": f"Loading resumes, notes and history for {len(selected)} candidates"},
        )
        await enrich_stage2(deps.jobdiva, pool, selected, job, budget, emit, s)
    for cid in selected:  # resume text is now available — refresh tie-break scores
        scores[cid] = prescore(pool.records[cid], intent, scores[cid].distance_mi)

    handles = {cid: f"c{i + 1:02d}" for i, cid in enumerate(selected)}
    packets = [build_packet(handles[cid], pool.records[cid], intent, scores[cid].distance_mi, s) for cid in selected]
    job_block = build_job_block(job, intent, reqs)

    await emit("stage", {"stage": STAGE_ASSESS, "message": f"Reviewing {len(packets)} profiles"})
    outcome = await assess_all(
        claude=deps.claude if s.llm_mode == "claude" else None,
        settings=s,
        packets=packets,
        reqs=reqs,
        job_block=job_block,
        emit=emit,
        deadline=deadline,
    )
    await emit("stage", {"stage": STAGE_VALIDATE, "message": "Validating and ranking"})

    packet_by_handle = {p.handle: p for p in packets}
    scored = [score_assessment(va, reqs, pool.records[va.candidate_id]) for va in outcome.assessments.values()]
    included = [x for x in scored if not x.excluded]
    included.sort(key=lambda x: (-x.fit, -scores[x.va.candidate_id].score, x.va.candidate_id))
    model_label = ", ".join(sorted(outcome.models)) or s.claude_model
    entries = [
        to_entry(
            i + 1,
            x,
            pool.records[x.va.candidate_id],
            packet_by_handle[x.va.handle],
            reqs,
            scores[x.va.candidate_id],
            model_label,
        )
        for i, x in enumerate(included[: s.shortlist_size])
    ]

    fail_count: Counter[str] = Counter()
    sole_count: Counter[str] = Counter()
    for x in scored:
        if x.excluded == "not_a_fit":
            fail_count.update(x.failing_musts)
            if len(x.failing_musts) == 1:
                sole_count[x.failing_musts[0]] += 1
    req_label = {r.id: r.text for r in reqs}
    funnel = Funnel(
        queries=pool.queries,
        pool=len(pool.records),
        linked=len(pool.linked_ids),
        excluded_by_filter=excluded,
        prescreened_out=prescreened_out,
        reviewed=len(selected),
        assessed=len(outcome.assessments),
        not_assessed=len(outcome.not_assessed),
        not_assessed_reasons=dict(Counter(outcome.not_assessed.values())),
        not_a_fit=sum(1 for x in scored if x.excluded == "not_a_fit"),
        failing_requirements=[
            RequirementFailure(requirement_id=rid, label=req_label.get(rid, rid), count=n, sole_blocker=sole_count[rid])
            for rid, n in fail_count.most_common()
        ],
        insufficient_evidence=sum(1 for x in scored if x.excluded == "insufficient_evidence"),
        shortlisted=len(entries),
        retrieval_partial=pool.partial,
    )

    warnings = list(pool.warnings)
    corrected = [i for i in outcome.issues if "→" in i or "removed" in i or "dropped" in i]
    if corrected:
        warnings.append(f"{len(corrected)} model claims were corrected or removed during validation.")
    if outcome.fallback_used:
        warnings.append("Some profiles were assessed by a fallback model after a refusal.")
    if s.llm_mode == "stub":
        warnings.append("LLM_MODE=stub: assessments come from a keyword matcher, not Claude.")

    result = SearchResult(
        job_id=job_id,
        search_id=search_id,
        generated_at=datetime.now(UTC).isoformat(),
        intent=intent,
        shortlist=entries,
        funnel=funnel,
        shortfall=explain(funnel, intent, s.shortlist_size, s.stage2_top_n),
        partial=pool.partial or bool(outcome.not_assessed),
        warnings=warnings,
        assessed_by=model_label,
        replayed=replay is not None,
    )

    try:
        write_snapshot(
            s.snapshot_path,
            {
                "job_id": job_id,
                "search_id": search_id,
                "written_at": result.generated_at,
                "elapsed_s": round(time.monotonic() - started, 2),
                "query": query,
                "notes": notes,
                "job": job.model_dump(),
                "intent": intent.model_dump(),
                "queries": [q.model_dump() for q in pool.queries],
                "retrieval_partial": pool.partial,
                "records": {cid: r.model_dump() for cid, r in pool.records.items()},
                "prescores": {cid: vars(ps) for cid, ps in scores.items()},
                "packets": {p.handle: {"candidate_id": p.candidate_id, "rendered": p.rendered} for p in packets},
                "model_outputs": outcome.raw_outputs,
                "validation_issues": outcome.issues,
                "not_assessed": outcome.not_assessed,
                "result": result.model_dump(),
            },
        )
    except OSError as exc:
        log.warning("could not write search snapshot: %s", exc)
    log.info(
        "search %s job=%s pool=%d reviewed=%d shortlisted=%d elapsed=%.1fs",
        search_id,
        job_id,
        funnel.pool,
        funnel.reviewed,
        funnel.shortlisted,
        time.monotonic() - started,
    )
    return result
