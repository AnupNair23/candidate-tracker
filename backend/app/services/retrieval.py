"""Step 2 — deterministic candidate retrieval from JobDiva v1.

Queries are built in code (never by the LLM) from the confirmed SearchIntent and run strict → broad,
paged 30 at a time, until the pool target or the per-search call budget is reached.
Candidate data is held only in request memory (plus the per-search snapshot file).
"""

from __future__ import annotations

import re

from app.clients.jobdiva.client import CallBudget, JobDivaClient
from app.clients.jobdiva.errors import FATAL_ERRORS, CallBudgetExhausted, JobDivaError
from app.clients.jobdiva.mappers import as_str, candidate_id_of, map_candidate, pick
from app.constants.search import (
    LINKED_QUERY_LABEL,
    LINKED_START_STATUS,
    LINKED_STARTS_PAGES,
    LINKED_SUBMITTAL_STATUS,
    LOCATION_QUERY_LABEL,
    LOCATION_SEARCH_PAGES,
    LOCATION_SEARCH_TARGET_DIVISOR,
    MAX_PLAIN_TITLE_QUERY_SKILLS,
    MAX_QUERY_ANY_SKILLS,
    MAX_QUERY_KEYWORDS,
    MAX_QUERY_MUST_SKILLS,
    MAX_QUERY_TITLES,
    MAX_SINGLE_SKILL_QUERIES,
    STAGE_RETRIEVE,
)
from app.core.config import Settings
from app.models.intent import SearchIntent
from app.models.jobdiva import Job
from app.models.pipeline import Emit, Pool
from app.models.results import QueryStat

# --------------------------------------------------------------------------- queries


def _term(text: str) -> str:
    cleaned = re.sub(r'["\\]', "", text).strip()
    return f'"{cleaned}"' if re.search(r"[^A-Za-z0-9]", cleaned) else cleaned


def _any(terms: list[str]) -> str:
    terms = list(dict.fromkeys(t for t in terms if t))
    return terms[0] if len(terms) == 1 else "(" + " OR ".join(terms) + ")"


def build_keyword_queries(intent: SearchIntent, boolean: bool = True) -> list[tuple[str, str, int]]:
    """(label, criteria, max_pages) from strict to broad."""
    titles: list[str] = []
    for t in intent.titles:
        titles.extend([t.title, *t.synonyms])
    # Drop parentheticals like "(CATIA)" — they are skills, not part of the title people put on resumes.
    titles = [re.sub(r"\s+", " ", re.sub(r"[(\[].*?[)\]]", " ", x)).strip() for x in titles]
    titles = list(dict.fromkeys(x for x in titles if x))[:MAX_QUERY_TITLES]
    skills = [r for r in intent.requirements if r.kind in ("skill", "keyword")]
    musts = [r.text for r in skills if r.must_have]
    key_skills = musts or [r.text for r in skills]

    queries: list[tuple[str, str, int]] = []
    if boolean:
        title_q = _any([_term(t) for t in titles]) if titles else ""
        musts_q = " AND ".join(_term(m) for m in musts[:MAX_QUERY_MUST_SKILLS])
        if title_q and musts_q:
            queries.append(("Title + all must-have skills", f"{title_q} AND {musts_q}", 3))
        if len(musts) >= 2:
            queries.append(("All must-have skills", musts_q, 2))
        if title_q and key_skills:
            any_skill_q = _any([_term(s) for s in key_skills[:MAX_QUERY_ANY_SKILLS]])
            queries.append(("Title + any key skill", f"{title_q} AND {any_skill_q}", 2))
        if title_q:
            queries.append(("Title only", title_q, 2))
    else:
        if titles and musts:
            queries.append(
                (
                    "Title + must-have skills",
                    " ".join([_term(titles[0]), *(_term(m) for m in musts[:MAX_PLAIN_TITLE_QUERY_SKILLS])]),
                    3,
                )
            )
        if len(musts) >= 2:
            queries.append(("Must-have skills", " ".join(_term(m) for m in musts[:MAX_QUERY_MUST_SKILLS]), 2))
        if titles:
            queries.append(("Title only", _term(titles[0]), 2))
    for skill in key_skills[:MAX_SINGLE_SKILL_QUERIES]:
        queries.append((f"Skill: {skill}", _term(skill), 1))
    if not queries and intent.keywords:
        queries.append(("Keywords", " ".join(_term(k) for k in intent.keywords[:MAX_QUERY_KEYWORDS]), 2))

    seen: set[str] = set()
    unique = []
    for label, criteria, pages in queries:
        if criteria not in seen:
            seen.add(criteria)
            unique.append((label, criteria, pages))
    return unique


# ------------------------------------------------------------------------- retrieval


async def retrieve(
    client: JobDivaClient, intent: SearchIntent, job: Job, settings: Settings, budget: CallBudget, emit: Emit
) -> Pool:
    pool = Pool()
    page_size = settings.jobdiva_page_size
    target = settings.pool_target

    linked = QueryStat(label=LINKED_QUERY_LABEL, criteria=f"submittals + starts for job {job.job_id}")

    def add_linked(rows: list[dict], default_status: str) -> None:
        linked.returned += len(rows)
        for row in rows:
            cid = candidate_id_of(row)
            rec = map_candidate(row, pool.records.get(cid)) if cid else None
            if rec is None:
                continue
            rec.job_linked = True
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

    for label, criteria, pages in build_keyword_queries(intent, settings.jobdiva_boolean_search):
        if len(pool.records) >= target or pool.partial:
            break
        stat = QueryStat(label=label, criteria=criteria)
        for page in range(pages):
            try:
                docs, found = await client.universal_search(
                    criteria, offset=page * page_size, max_returned=page_size, budget=budget
                )
            except CallBudgetExhausted:
                pool.partial = True
                break
            except FATAL_ERRORS:
                raise
            except JobDivaError as exc:
                stat.error = exc.message
                break
            if page == 0:
                stat.found = found
            stat.returned += len(docs)
            for doc in docs:
                cid = candidate_id_of(doc)
                rec = map_candidate(doc, pool.records.get(cid), from_search=True) if cid else None
                if rec is not None:
                    stat.new += int(pool.add(rec))
            if len(docs) < page_size or len(pool.records) >= target:
                break
        pool.queries.append(stat)
        await emit(
            "progress",
            {
                "stage": STAGE_RETRIEVE,
                "message": f"{label}: {stat.returned} returned, {stat.new} new",
                "pool": len(pool.records),
            },
        )

    loc = intent.location
    if (
        loc
        and (loc.zipcode or loc.city or loc.state)
        and len(pool.records) < target // LOCATION_SEARCH_TARGET_DIVISOR
        and not pool.partial
    ):
        where = ", ".join(p for p in (loc.city, loc.state, loc.zipcode) if p)
        stat = QueryStat(label=LOCATION_QUERY_LABEL, criteria=where)
        for page in range(LOCATION_SEARCH_PAGES):
            try:
                rows = await client.search_candidate_profile(
                    city=loc.city,
                    state=loc.state,
                    zipcode=loc.zipcode,
                    offset=page * page_size,
                    max_returned=page_size,
                    budget=budget,
                )
            except CallBudgetExhausted:
                pool.partial = True
                break
            except FATAL_ERRORS:
                raise
            except JobDivaError as exc:
                stat.error = exc.message
                break
            stat.returned += len(rows)
            for row in rows:
                cid = candidate_id_of(row)
                rec = map_candidate(row, pool.records.get(cid)) if cid else None
                if rec is not None:
                    stat.new += int(pool.add(rec))
            if len(rows) < page_size:
                break
        stat.found = stat.returned
        pool.queries.append(stat)

    if pool.partial:
        pool.warnings.append("JobDiva call budget reached during retrieval; continuing with candidates found so far.")
    keyword = [q for q in pool.queries if q.label not in (LINKED_QUERY_LABEL, LOCATION_QUERY_LABEL)]
    if keyword and all(q.returned == 0 and not q.error for q in keyword):
        pool.warnings.append(
            f"JobDiva candidate keyword search returned no candidates for any of {len(keyword)} queries. If JobDiva "
            "has matching candidates, check that the API user is permitted to search candidates."
        )
    return pool
