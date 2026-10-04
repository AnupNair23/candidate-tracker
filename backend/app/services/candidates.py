"""Live candidate data for the drawer and the Candidates tab — fetched from JobDiva on every request."""

from __future__ import annotations

import asyncio
from typing import Any

from app.clients.jobdiva.client import JobDivaClient
from app.clients.jobdiva.errors import FATAL_ERRORS, JobDivaError, JobDivaNotFound
from app.clients.jobdiva.mappers import (
    apply_work_history,
    as_str,
    candidate_id_of,
    dedupe_interactions,
    iso,
    map_candidate,
    map_note,
    map_submittal,
    newest_resume_id,
    pick,
    resume_text_of,
)
from app.constants.jobdiva import QUICK_SEARCH_MAX_RETURNED
from app.constants.search import LINKED_START_STATUS, LINKED_SUBMITTAL_STATUS, START_ROW_INDEX_OFFSET
from app.core.config import Settings
from app.models.jobdiva import CandidateRecord, Interaction


async def linked_candidates(client: JobDivaClient, job_id: str, page_size: int = 30) -> dict[str, Any]:
    """Submittals + starts for a job. One source failing still returns the other, with a warning."""
    results = await asyncio.gather(
        client.job_submittals(job_id),
        client.job_starts(job_id, offset=0, max_returned=page_size),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, FATAL_ERRORS):
            raise r
    failures = [r for r in results if isinstance(r, BaseException)]
    if len(failures) == len(results):
        raise failures[0]
    warnings = [
        f"Could not load {name} from JobDiva: {getattr(r, 'message', type(r).__name__)}"
        for name, r in zip(("submittals", "starts"), results, strict=True)
        if isinstance(r, BaseException)
    ]
    items: dict[str, dict[str, Any]] = {}
    for source, rows in zip(("submittal", "start"), results, strict=True):
        if isinstance(rows, BaseException):
            continue
        for row in rows:
            cid = candidate_id_of(row)
            rec = map_candidate(row) if cid else None
            if rec is None:
                continue
            date = iso(pick(row, "submittaldate", "startdate", "hiredate", "datecreated"))
            status = as_str(pick(row, "submittalstatus", "startstatus", "status"))
            current = items.get(cid)
            if current is None or (date or "") > (current["date"] or ""):
                items[cid] = {
                    "candidate_id": cid,
                    "name": rec.name,
                    "title": rec.title,
                    "city": rec.city,
                    "state": rec.state,
                    "status": status or (LINKED_START_STATUS if source == "start" else LINKED_SUBMITTAL_STATUS),
                    "date": date,
                    "source": source,
                }
    return {"items": sorted(items.values(), key=lambda x: x["date"] or "", reverse=True), "warnings": warnings}


async def profile(
    client: JobDivaClient, settings: Settings, candidate_id: str, name_hint: str | None
) -> dict[str, Any]:
    """v1 has no /api/jobdiva profile-by-id endpoint: look the candidate up through quick search (by id, then by
    name) and accept only an exact candidate-id match; then fetch contact + qualifications by name."""
    rec = CandidateRecord(candidate_id=candidate_id)
    found = False
    if settings.jobdiva_use_bi:  # direct lookup by id (BI is the only JobDiva endpoint that offers one)
        try:
            row = await client.bi_candidate_detail(candidate_id)
        except FATAL_ERRORS:
            raise
        except JobDivaError:
            row = None
        if row and candidate_id_of(row) == candidate_id:
            map_candidate(row, rec)
            found = True
    for criteria in (candidate_id, name_hint):
        if not criteria or found:
            continue
        try:
            docs = await client.quick_candidate_search(criteria, max_returned=QUICK_SEARCH_MAX_RETURNED)
        except FATAL_ERRORS:
            raise
        except JobDivaError:
            docs = []
        for doc in docs:
            if candidate_id_of(doc) == candidate_id:
                map_candidate(doc, rec)
                found = True
                break

    first, last = rec.first_name, rec.last_name
    if not (first and last) and name_hint:
        parts = name_hint.split()
        first, last = (parts[0], " ".join(parts[1:])) if len(parts) > 1 else (None, None)
    if first and last:
        try:
            for row in await client.search_candidate_profile(
                first_name=first, last_name=last, max_returned=QUICK_SEARCH_MAX_RETURNED
            ):
                if candidate_id_of(row) == candidate_id:
                    map_candidate(row, rec)
                    found = True
        except FATAL_ERRORS:
            raise
        except JobDivaError:
            pass
    if not found:
        raise JobDivaNotFound(f"Candidate {candidate_id} could not be found through the JobDiva search API", status=404)

    work_history: list[dict[str, Any]] = []
    history_state = "unavailable"
    if settings.jobdiva_use_bi:
        try:
            apply_work_history(rec, await client.bi_candidate_experience(candidate_id))
            work_history = [w.model_dump() for w in rec.work_history]
            history_state = "ok" if work_history else "none"
        except FATAL_ERRORS:
            raise
        except JobDivaError:
            history_state = "unavailable"

    return {
        "candidate_id": candidate_id,
        "name": rec.name,
        "title": rec.title,
        "employer": rec.employer,
        "city": rec.city,
        "state": rec.state,
        "zipcode": rec.zipcode,
        "email": rec.email,
        "phone": rec.phone,
        "years_experience": rec.years_experience,
        "available": rec.available,
        "updated_on": rec.updated_on,
        "skills": [q.model_dump() for q in rec.qualifications],
        "work_history": work_history,
        "work_history_state": history_state,
    }


def _split(items: list[Interaction]) -> tuple[list[Interaction], list[Interaction]]:
    notes = [i for i in items if i.type in ("notes", "recorded_conversations")]
    history = [i for i in items if i.type not in ("notes", "recorded_conversations")]
    return notes, history


async def _no_rows() -> list[dict]:
    return []


async def interactions(
    client: JobDivaClient, settings: Settings, candidate_id: str, job_id: str | None = None
) -> dict[str, Any]:
    """Starts/activities across all jobs, plus submittals to `job_id` (JobDiva requires a job for submittals)."""
    results = await asyncio.gather(
        client.candidate_job_submittals(candidate_id, job_id) if job_id else _no_rows(),
        client.candidate_starts(candidate_id, max_returned=settings.jobdiva_page_size),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, FATAL_ERRORS):
            raise r
    items: list[Interaction] = []
    ok = 0
    for offset, rows in zip((0, START_ROW_INDEX_OFFSET), results, strict=True):
        if isinstance(rows, BaseException):
            continue
        ok += 1
        items.extend(x for i, row in enumerate(rows) for x in map_submittal(row, offset + i))
    history_state = "unavailable" if ok == 0 else ("ok" if items else "none")

    notes_state = "unavailable"
    if settings.jobdiva_use_bi:
        try:
            rows = await client.bi_candidate_notes(candidate_id)
            mapped = [n for i, row in enumerate(rows) if (n := map_note(row, i))]
            items.extend(mapped)
            notes_state = "ok" if mapped else "none"
        except FATAL_ERRORS:
            raise
        except JobDivaError:
            notes_state = "unavailable"

    items = sorted(dedupe_interactions(items), key=lambda i: i.date or "", reverse=True)
    notes, history = _split(items)
    if notes_state == "unavailable" and notes:
        notes_state = "ok"  # submittal internal notes surfaced as notes
    return {
        "candidate_id": candidate_id,
        "notes": [n.model_dump() for n in notes],
        "history": [h.model_dump() for h in history],
        "sources": {"notes": notes_state, "history": history_state},
    }


async def resume(client: JobDivaClient, settings: Settings, candidate_id: str) -> dict[str, Any]:
    if not settings.jobdiva_use_bi:
        return {"candidate_id": candidate_id, "text": None, "available": False}
    rid = newest_resume_id(await client.bi_candidate_resume_ids([candidate_id])).get(candidate_id)
    text = resume_text_of(await client.bi_resume_detail(rid)) if rid else None
    return {"candidate_id": candidate_id, "text": text, "available": True}
