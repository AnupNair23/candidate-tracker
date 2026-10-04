"""Step 4 — stage-two hydration: per-candidate history (and, with JOBDIVA_USE_BI, notes and resume text)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable

from app.clients.jobdiva.client import CallBudget, JobDivaClient
from app.clients.jobdiva.errors import FATAL_ERRORS, CallBudgetExhausted, JobDivaError
from app.clients.jobdiva.mappers import dedupe_interactions, map_note, map_submittal, newest_resume_id, resume_text_of
from app.constants.search import HYDRATE_PROGRESS_EVERY, MAX_INTERACTIONS, STAGE_HYDRATE, START_ROW_INDEX_OFFSET
from app.core.config import Settings
from app.models.jobdiva import CandidateRecord, Interaction, Job
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


async def enrich_stage2(
    client: JobDivaClient, pool: Pool, ids: list[str], job: Job, budget: CallBudget, emit: Emit, settings: Settings
) -> None:
    """Per-candidate history from /api/jobdiva (searchSubmittal + searchStart). Notes and resume text exist
    only on /api/bi in v1, so they are fetched only when JOBDIVA_USE_BI=true and reported unavailable otherwise."""
    use_bi = settings.jobdiva_use_bi
    rid_map: dict[str, str] = {}
    resumes_ok = False
    if use_bi:
        try:
            rid_map = newest_resume_id(await client.bi_candidate_resume_ids(ids, budget=budget))
            resumes_ok = True
        except CallBudgetExhausted:
            pool.partial = True
        except FATAL_ERRORS:
            raise
        except JobDivaError as exc:
            pool.warnings.append(f"Resume list unavailable: {exc.message}")

    done = 0
    total = len(ids)

    async def guarded(source: str, rec: CandidateRecord, coro: Awaitable):
        try:
            return await coro
        except CallBudgetExhausted:
            pool.partial = True
            rec.source_status[source] = "not_fetched"
        except FATAL_ERRORS:
            raise
        except JobDivaError:
            rec.source_status[source] = "unavailable"
        return None

    async def one(cid: str) -> None:
        nonlocal done
        rec = pool.records[cid]
        interactions: list[Interaction] = []

        subs = await guarded("submissions", rec, client.candidate_submittals(cid, budget=budget))
        if subs is not None:
            mapped = [x for i, row in enumerate(subs) for x in map_submittal(row, i)]
            interactions.extend(mapped)
            rec.source_status["submissions"] = "ok" if mapped else "none"
        starts = await guarded(
            "placements", rec, client.candidate_starts(cid, max_returned=settings.jobdiva_page_size, budget=budget)
        )
        if starts is not None:
            mapped = [x for i, row in enumerate(starts) for x in map_submittal(row, START_ROW_INDEX_OFFSET + i)]
            interactions.extend(mapped)
            rec.source_status["placements"] = "ok" if any(m.type == "placements" for m in mapped) else "none"

        if use_bi:
            notes = await guarded("notes", rec, client.bi_candidate_notes(cid, budget=budget))
            if notes is not None:
                mapped_notes = [n for i, row in enumerate(notes) if (n := map_note(row, i))]
                interactions.extend(mapped_notes)
                rec.source_status["notes"] = "ok" if mapped_notes else "none"
            rid = rid_map.get(cid)
            if rid:
                detail = await guarded("resume", rec, client.bi_resume_detail(rid, budget=budget))
                if "resume" not in rec.source_status:
                    rec.resume_text = resume_text_of(detail)
                    rec.source_status["resume"] = "ok" if rec.resume_text else "none"
            else:
                rec.source_status["resume"] = "none" if resumes_ok else "unavailable"
        else:
            rec.source_status.setdefault("notes", "unavailable")
            rec.source_status.setdefault("resume", "unavailable")

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
