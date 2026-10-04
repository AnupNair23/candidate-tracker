"""Steps 3–4 — enrich candidates from JobDiva.

- `enrich_profiles` (whole pool, JOBDIVA_USE_BI): batched BI profile rows (dates, location, contact) so the
  pre-score can use recency and location.
- `enrich_stage2` (the reviewed set):
  - batched BI calls for resume text, notes and work history (verified live: these are the only JobDiva sources of
    candidate detail);
  - per-candidate v1 searchStart for placements and rejections across jobs.

  Submittals to this job already came from the job's A–Z sweep during retrieval.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable

from app.clients.jobdiva.client import CallBudget, JobDivaClient
from app.clients.jobdiva.errors import FATAL_ERRORS, CallBudgetExhausted, JobDivaError
from app.clients.jobdiva.mappers import (
    apply_work_history,
    as_rows,
    as_str,
    candidate_id_of,
    dedupe_interactions,
    map_candidate,
    map_note,
    map_submittal,
    newest_resume_id,
    pick,
    resume_text_of,
)
from app.constants.search import HYDRATE_PROGRESS_EVERY, MAX_INTERACTIONS, STAGE_HYDRATE, START_ROW_INDEX_OFFSET
from app.core.config import Settings
from app.models.jobdiva import Interaction, Job
from app.models.pipeline import Emit, Pool
from app.utils.text import norm


def _cap_interactions(items: list[Interaction], client_name: str | None) -> list[Interaction]:
    items = sorted(items, key=lambda i: i.date or "", reverse=True)
    if len(items) <= MAX_INTERACTIONS:
        return items
    keep = items[:MAX_INTERACTIONS]
    if client_name:
        same_client = [i for i in items[MAX_INTERACTIONS:] if i.client and norm(i.client) == norm(client_name)]
        keep.extend(same_client)
    return keep


async def _batch(pool: Pool, label: str, call: Callable[[], Awaitable[list[dict]]]) -> list[dict] | None:
    """Run one batched BI call; None means the source is unavailable for this search (recorded as a warning)."""
    try:
        return await call()
    except CallBudgetExhausted:
        pool.partial = True
    except FATAL_ERRORS:
        raise
    except JobDivaError as exc:
        pool.warnings.append(f"JobDiva {label} unavailable: {exc.message}")
    return None


async def enrich_profiles(client: JobDivaClient, pool: Pool, budget: CallBudget, settings: Settings) -> None:
    """Batched BI profile details for every pooled candidate (no-op when JOBDIVA_USE_BI is off)."""
    if not settings.jobdiva_use_bi or not pool.records:
        return
    rows = await _batch(pool, "profiles", lambda: client.bi_candidates_detail(list(pool.records), budget=budget))
    for row in rows or []:
        cid = candidate_id_of(row)
        if cid in pool.records:
            map_candidate(row, pool.records[cid])


async def enrich_stage2(
    client: JobDivaClient, pool: Pool, ids: list[str], job: Job, budget: CallBudget, emit: Emit, settings: Settings
) -> None:
    use_bi = settings.jobdiva_use_bi
    records = {cid: pool.records[cid] for cid in ids}

    if use_bi:
        resume_rows = await _batch(pool, "resume list", lambda: client.bi_candidate_resume_ids(ids, budget=budget))
        rid_map = newest_resume_id(resume_rows or [])
        texts: dict[str | None, str | None] = {}
        if rid_map:
            text_rows = await _batch(
                pool, "resume text", lambda: client.bi_resume_texts(list(rid_map.values()), budget=budget)
            )
            texts = {as_str(pick(r, "globalid", "resumeid")): resume_text_of(r) for r in text_rows or []}
        for cid, rec in records.items():
            if resume_rows is None:
                rec.source_status["resume"] = "unavailable"
            else:
                rec.resume_text = texts.get(rid_map.get(cid))
                rec.source_status["resume"] = "ok" if rec.resume_text else "none"

        note_rows = await _batch(pool, "notes", lambda: client.bi_candidates_notes(ids, budget=budget))
        notes_by_cid: dict[str, list[Interaction]] = defaultdict(list)
        for i, row in enumerate(note_rows or []):
            note = map_note(row, i)
            cid = candidate_id_of(row)
            if note and cid in records:
                notes_by_cid[cid].append(note)
        for cid, rec in records.items():
            rec.interactions.extend(notes_by_cid.get(cid, []))
            if note_rows is None:
                rec.source_status["notes"] = "unavailable"
            else:
                has_notes = any(i.type in ("notes", "recorded_conversations") for i in rec.interactions)
                rec.source_status["notes"] = "ok" if has_notes else "none"

        sub_rows = await _batch(pool, "submittal history", lambda: client.bi_candidates_submittals(ids, budget=budget))
        for i, row in enumerate(sub_rows or []):
            cid = candidate_id_of(row)
            if cid in records:
                records[cid].interactions.extend(map_submittal(row, 2000 + i))

        profile_rows = await _batch(pool, "work history", lambda: client.bi_candidates_profiles(ids, budget=budget))
        for row in profile_rows or []:
            cid = candidate_id_of(row)
            if cid in records:
                map_candidate(row, records[cid])
                apply_work_history(records[cid], as_rows(pick(row, "experience")))
    else:
        for rec in records.values():
            has_last_note = any(i.interaction_id.startswith("lastnote-") for i in rec.interactions)
            rec.source_status.setdefault("notes", "ok" if has_last_note else "unavailable")
            rec.source_status.setdefault("resume", "unavailable")

    done = 0
    total = len(ids)

    async def one(cid: str) -> None:
        nonlocal done
        rec = records[cid]
        interactions: list[Interaction] = list(rec.interactions)  # sweep submittals, LASTNOTE, BI notes
        rec.source_status["submissions"] = "ok" if any(i.type == "submissions" for i in interactions) else "none"
        try:
            starts = await client.candidate_starts(cid, max_returned=settings.jobdiva_page_size, budget=budget)
        except CallBudgetExhausted:
            pool.partial = True
            rec.source_status["placements"] = "not_fetched"
            starts = None
        except FATAL_ERRORS:
            raise
        except JobDivaError:
            rec.source_status["placements"] = "unavailable"
            starts = None
        if starts is not None:
            mapped = [x for i, row in enumerate(starts) for x in map_submittal(row, START_ROW_INDEX_OFFSET + i)]
            interactions.extend(mapped)
            rec.source_status["placements"] = "ok" if any(m.type == "placements" for m in mapped) else "none"
        rec.interactions = _cap_interactions(dedupe_interactions(interactions), job.company)
        done += 1
        if done % HYDRATE_PROGRESS_EVERY == 0 or done == total:
            await emit("progress", {"stage": STAGE_HYDRATE, "done": done, "total": total})

    results = await asyncio.gather(*(one(cid) for cid in ids), return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            raise result
    if pool.partial and not any("call budget" in w for w in pool.warnings):
        pool.warnings.append("JobDiva call budget reached while loading profiles; some sources were not fetched.")
