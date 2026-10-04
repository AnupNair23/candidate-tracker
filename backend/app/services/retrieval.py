"""Step 2 — deterministic candidate retrieval from JobDiva.

Queries are built in code (never by the LLM) from the confirmed SearchIntent and run strict → broad through
v2 TalentSearch (the single approved v2 call: v1 has no skill/title candidate search), plus the candidates
already linked to the job (v1 searchSubmittal sweep + searchStart). Each candidate remembers which skills/titles
JobDiva's resume search matched them on; that becomes ranking evidence.
Candidate data is held only in request memory (plus the per-search snapshot file).
"""

from __future__ import annotations

import re

from app.clients.jobdiva.client import CallBudget, JobDivaClient
from app.clients.jobdiva.errors import FATAL_ERRORS, CallBudgetExhausted, JobDivaError
from app.clients.jobdiva.mappers import as_str, candidate_id_of, map_candidate, map_last_note, map_submittal, pick
from app.constants.search import (
    LINKED_APPLICANT_STATUS,
    LINKED_QUERY_LABEL,
    LINKED_START_STATUS,
    LINKED_STARTS_PAGES,
    LINKED_SUBMITTAL_STATUS,
    MAX_SINGLE_SKILL_QUERIES,
    MAX_TITLE_QUERIES,
    STAGE_RETRIEVE,
    TALENT_RESUME_COUNT_BROAD,
)
from app.core.config import Settings
from app.models.intent import SearchIntent
from app.models.jobdiva import Job
from app.models.pipeline import Emit, Pool, TalentQuery
from app.models.results import QueryStat

# --------------------------------------------------------------------------- queries


def _clean_title(title: str) -> str:
    # Drop parentheticals like "(CATIA)" — they are skills, not part of the title people put on resumes.
    return re.sub(r"\s+", " ", re.sub(r"[(\[].*?[)\]]", " ", title)).strip()


def build_talent_queries(intent: SearchIntent) -> list[TalentQuery]:
    """TalentSearch queries from strict to broad. Skills are ANDed by JobDiva, so breadth comes from fewer skills."""
    skills = [r for r in intent.requirements if r.kind in ("skill", "keyword")]
    key_skills = [r.text for r in skills if r.must_have] + [r.text for r in skills if not r.must_have]
    # No state filter: live, TalentSearch's `states` filter was slow (~20 s per query) and returned nothing for
    # smaller states, while national queries return in under a second. Location is ranked locally (pre-score).
    states: tuple[str, ...] = ()
    where = ""

    titles: list[str] = []
    for t in intent.titles:
        titles.extend([t.title, *t.synonyms])
    titles = list(dict.fromkeys(c for c in (_clean_title(t) for t in titles) if c))

    # Single-skill queries only: live, multi-skill (ANDed) TalentSearch queries took 20–30 s and returned almost
    # nothing, while single-skill queries return in under a second. A candidate found by several skill queries
    # collects every matched skill in `search_matches`, so the AND happens locally in ranking instead.
    queries: list[TalentQuery] = []
    for skill in key_skills[:MAX_SINGLE_SKILL_QUERIES]:
        queries.append(TalentQuery(f"Skill: {skill}{where}", (skill,), None, states, TALENT_RESUME_COUNT_BROAD))
    for title in titles[:MAX_TITLE_QUERIES]:
        queries.append(TalentQuery(f"Title: {title}{where}", (), title, states, TALENT_RESUME_COUNT_BROAD))
    if not queries and intent.keywords:
        queries.append(TalentQuery("Keyword", (intent.keywords[0],), None, states, TALENT_RESUME_COUNT_BROAD))

    unique: dict[tuple, TalentQuery] = {}
    for q in queries:
        unique.setdefault((q.skills, q.title, q.states), q)
    return list(unique.values())


def describe(q: TalentQuery) -> str:
    parts = [f"skills={' AND '.join(q.skills)}" if q.skills else "", f"title={q.title}" if q.title else ""]
    parts.append(f"states={','.join(q.states)}" if q.states else "any state")
    return "; ".join(p for p in parts if p)


# ------------------------------------------------------------------------- retrieval


async def retrieve(
    client: JobDivaClient, intent: SearchIntent, job: Job, settings: Settings, budget: CallBudget, emit: Emit
) -> Pool:
    pool = Pool()
    page_size = settings.jobdiva_page_size
    target = settings.pool_target

    linked = QueryStat(label=LINKED_QUERY_LABEL, criteria=f"submittals + applicants + starts for job {job.job_id}")

    def add_linked(rows: list[dict], default_status: str) -> None:
        linked.returned += len(rows)
        for row in rows:
            cid = candidate_id_of(row)
            rec = map_candidate(row, pool.records.get(cid)) if cid else None
            if rec is None:
                continue
            rec.job_linked = True
            if default_status == LINKED_SUBMITTAL_STATUS:  # this job's submittal history
                rec.interactions.extend(map_submittal({**row, "jobid": job.job_id}, len(rec.interactions)))
            rec.job_link_status = (
                rec.job_link_status or as_str(pick(row, "submittalstatus", "startstatus", "status")) or default_status
            )
            linked.new += int(pool.add(rec))

    errors: list[str] = []
    try:
        add_linked(await client.job_submittals(job.job_id, budget=budget), LINKED_SUBMITTAL_STATUS)
    except CallBudgetExhausted:
        pool.partial = True
    except FATAL_ERRORS:
        raise
    except JobDivaError as exc:
        errors.append(f"submittals: {exc.message}")
    if client.use_bi:
        try:
            add_linked(await client.bi_job_applicants(job.job_id, budget=budget), LINKED_APPLICANT_STATUS)
        except CallBudgetExhausted:
            pool.partial = True
        except FATAL_ERRORS:
            raise
        except JobDivaError as exc:
            errors.append(f"applicants: {exc.message}")
    try:
        for page in range(LINKED_STARTS_PAGES):
            rows = await client.job_starts(job.job_id, offset=page * page_size, max_returned=page_size, budget=budget)
            add_linked(rows, LINKED_START_STATUS)
            if len(rows) < page_size:
                break
    except CallBudgetExhausted:
        pool.partial = True
    except FATAL_ERRORS:
        raise
    except JobDivaError as exc:
        errors.append(f"starts: {exc.message}")
    linked.error = "; ".join(errors) or None
    linked.found = linked.returned
    pool.queries.append(linked)
    await emit("progress", {"stage": STAGE_RETRIEVE, "message": f"{linked.new} candidates already linked to the job"})

    for q in build_talent_queries(intent):
        if len(pool.records) >= target or pool.partial:
            break
        stat = QueryStat(label=q.label, criteria=describe(q))
        try:
            rows = await client.talent_search(
                skills=q.skills, title=q.title, states=q.states, resume_count=q.resume_count, budget=budget
            )
        except CallBudgetExhausted:
            pool.partial = True
            rows = []
        except FATAL_ERRORS:
            raise
        except JobDivaError as exc:
            stat.error = exc.message
            rows = []
        stat.returned = stat.found = len(rows)
        for row in rows:
            cid = candidate_id_of(row)
            rec = map_candidate(row, pool.records.get(cid), from_search=True) if cid else None
            if rec is None:
                continue
            for matched in (*q.skills, *((q.title,) if q.title else ())):
                if matched not in rec.search_matches:
                    rec.search_matches.append(matched)
            note = map_last_note(row)
            if note and all(i.interaction_id != note.interaction_id for i in rec.interactions):
                rec.interactions.append(note)
            stat.new += int(pool.add(rec))
        pool.queries.append(stat)
        await emit(
            "progress",
            {
                "stage": STAGE_RETRIEVE,
                "message": f"{q.label}: {stat.returned} returned, {stat.new} new",
                "pool": len(pool.records),
            },
        )

    if pool.partial:
        pool.warnings.append("JobDiva call budget reached during retrieval; continuing with candidates found so far.")
    searches = [q for q in pool.queries if q.label != LINKED_QUERY_LABEL]
    if searches and all(q.returned == 0 and not q.error for q in searches):
        pool.warnings.append(
            f"JobDiva TalentSearch returned no candidates for any of {len(searches)} queries. Try fewer must-have "
            "skills, different skill spellings, or remove the location."
        )
    return pool
