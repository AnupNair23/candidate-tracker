"""Step 5 — evidence packets and Claude per-requirement assessment (batched, with a stub assessor for dev).

Claude sees short handles (c01) and evidence ids (c01-e03), never names or contact details.
It returns per-requirement verdicts with evidence ids; code validates them (validation.py) and
computes the fit score, tier and rank deterministically (scoring.py).
"""

from __future__ import annotations

import asyncio
import math
import re
import time

from app.clients.claude import ClaudeClient
from app.clients.claude_errors import (
    ClaudeAuthError,
    ClaudeError,
    ClaudeNotConfigured,
    ClaudeOutputInvalid,
    ClaudeRateLimited,
    ClaudeRefusal,
    ClaudeTruncated,
)
from app.constants.assessment import (
    INTERACTION_EVIDENCE_CHARS,
    RESUME_PARAGRAPH_CHARS,
    SEARCH_EXCERPT_CAP_DIVISOR,
    YEARS_REQUIREMENT_ID,
)
from app.constants.llm import ASSESS_MAX_TOKENS, STUB_CONTRIBUTION_EVIDENCE, STUB_MODEL, STUB_VERDICT_EVIDENCE
from app.constants.pii import AUTH_HINTS
from app.constants.search import STAGE_ASSESS
from app.core.config import Settings
from app.models.assessment import INTERACTION_SOURCES, AssessmentOut, BatchOut, ContributionOut, VerdictOut
from app.models.intent import Requirement, SearchIntent
from app.models.jobdiva import CandidateRecord, Job
from app.models.pipeline import AssessOutcome, Emit, Evidence, Packet
from app.prompts.assess import ASSESS_SYSTEM_PROMPT, REPAIR_NOTE
from app.services.intent import job_context
from app.services.validation import validate_batch
from app.utils.text import clip, escape_untrusted, scrub_pii, supports

# ------------------------------------------------------------------------- packets


def assessment_requirements(intent: SearchIntent) -> list[Requirement]:
    reqs = [r for r in intent.requirements]
    if intent.years and intent.years.min is not None:
        span = f"{intent.years.min}+" if intent.years.max is None else f"{intent.years.min}-{intent.years.max}"
        reqs.append(
            Requirement(
                id=YEARS_REQUIREMENT_ID,
                text=f"{span} years of relevant experience",
                kind="other",
                must_have=intent.years.required,
                aliases=[],
                source=intent.years.source,
            )
        )
    return reqs


def _needs_authorization(intent: SearchIntent) -> bool:
    return any(r.kind == "authorization" for r in intent.requirements)


def _split_paragraphs(text: str, cap: int) -> tuple[list[str], bool]:
    paras: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            paras.append("\n".join(buf).strip())  # keep lines: scrubbing is line-scoped
            buf.clear()

    for line in text.split("\n"):
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            flush()
            continue
        buf.append(line)
        if sum(len(x) for x in buf) > RESUME_PARAGRAPH_CHARS:
            flush()
    flush()
    out: list[str] = []
    total = 0
    for p in paras:
        if total + len(p) > cap:
            return out, True
        out.append(p)
        total += len(p)
    return out, False


def build_packet(
    handle: str, rec: CandidateRecord, intent: SearchIntent, distance_mi: float | None, settings: Settings
) -> Packet:
    names = [rec.first_name, rec.last_name, " ".join(p for p in (rec.first_name, rec.last_name) if p) or None]
    evidence: dict[str, Evidence] = {}

    def add(source: str, label: str, text: str | None, date: str | None = None) -> None:
        cleaned = scrub_pii(text, names).strip()
        if not cleaned:
            return
        eid = f"{handle}-e{len(evidence) + 1:02d}"
        evidence[eid] = Evidence(eid=eid, source=source, label=label, text=cleaned, date=date)

    if rec.title:
        add("profile", "Current title", f"Current title: {rec.title}")
    if rec.employer:
        add("profile", "Current employer", f"Current employer: {rec.employer}")
    where = ", ".join(p for p in (rec.city, rec.state) if p)
    if where:
        near = f" (about {distance_mi:.0f} mi from the job location)" if distance_mi is not None else ""
        add("profile", "Location", f"Location: {where}{near}")
    if rec.years_experience is not None:
        add("profile", "Years of experience", f"Years of experience (profile field): {rec.years_experience:g}")
    grouped: dict[str, list[str]] = {}
    needs_auth = _needs_authorization(intent)
    for q in rec.qualifications:
        if not needs_auth and any(h in q.name.lower() for h in AUTH_HINTS):
            continue
        grouped.setdefault(q.name, []).append(q.value)
    for name, values in grouped.items():
        add("profile", name, f"{name}: {', '.join(values)}")
    if rec.available is not None:
        add(
            "profile", "Availability", "Availability: available now" if rec.available else "Availability: not available"
        )
    if needs_auth and rec.work_authorization:
        add("profile", "Work authorization", f"Work authorization: {rec.work_authorization}")

    if rec.resume_text:
        paras, truncated = _split_paragraphs(scrub_pii(rec.resume_text, names), settings.resume_char_cap)
        for p in paras:
            add("resume", "Resume", p)
        if truncated:
            add("resume", "Resume", "(resume truncated for length)")
    elif rec.search_text:
        paras, truncated = _split_paragraphs(
            scrub_pii(rec.search_text, names), settings.resume_char_cap // SEARCH_EXCERPT_CAP_DIVISOR
        )
        for p in paras:
            add("resume", "Search excerpt", p)
        if truncated:
            add("resume", "Search excerpt", "(search excerpt truncated for length)")

    if rec.search_matches:
        add(
            "resume",
            "JobDiva resume search",
            "JobDiva's resume search matched this candidate on: " + ", ".join(rec.search_matches),
        )

    for it in rec.interactions:
        meta = " | ".join(
            p
            for p in (
                it.type.replace("_", " "),
                it.date,
                f"client: {it.client}" if it.client else None,
                f"job: {it.job_title}" if it.job_title else None,
                f"status: {it.status}" if it.status else None,
            )
            if p
        )
        add(
            it.type,
            it.type.replace("_", " ").capitalize(),
            f"[{meta}] {clip(it.content, INTERACTION_EVIDENCE_CHARS)}",
            it.date,
        )

    lines = [f'<candidate handle="{handle}">']
    for ev in evidence.values():
        date_attr = f' date="{ev.date}"' if ev.date else ""
        lines.append(f'<evidence id="{ev.eid}" source="{ev.source}"{date_attr}>{escape_untrusted(ev.text)}</evidence>')
    status = "; ".join(f"{k}: {v}" for k, v in sorted(rec.source_status.items()))
    if status:
        lines.append(f"<source_status>{escape_untrusted(status)}</source_status>")
    lines.append("</candidate>")
    return Packet(handle=handle, candidate_id=rec.candidate_id, evidence=evidence, rendered="\n".join(lines))


def build_job_block(job: Job, intent: SearchIntent, reqs: list[Requirement]) -> str:
    req_lines = []
    for r in reqs:
        alias = f" (also written as: {', '.join(r.aliases)})" if r.aliases else ""
        req_lines.append(
            f'<requirement id="{r.id}" kind="{r.kind}" must_have="{str(r.must_have).lower()}">'
            f"{escape_untrusted(r.text)}{escape_untrusted(alias)}</requirement>"
        )
    prefs = "\n".join(f"- {escape_untrusted(p)}" for p in intent.preferences_from_notes) or "(none)"
    excl = "\n".join(f"- {escape_untrusted(p)}" for p in intent.exclusions) or "(none)"
    return (
        f"<job>\n{escape_untrusted(job_context(job))}\n"
        f"<requirements>\n" + "\n".join(req_lines) + "\n</requirements>\n"
        f"<recruiter_preferences>\n{prefs}\n</recruiter_preferences>\n"
        f"<recruiter_exclusions>\n{excl}\n</recruiter_exclusions>\n</job>"
    )


# ------------------------------------------------------------------- assessment run


def deal_batches(handles: list[str], size: int) -> list[list[str]]:
    """Round-robin so each batch mixes stronger and weaker pre-scores."""
    if not handles:
        return []
    n = max(1, math.ceil(len(handles) / max(1, size)))
    return [handles[i::n] for i in range(n)]


def stub_assess(packets: list[Packet], reqs: list[Requirement]) -> BatchOut:
    """Deterministic keyword matcher used when LLM_MODE=stub. Never claims not_met."""
    out = []
    for p in packets:
        verdicts = []
        for r in reqs:
            hits = [e for e, ev in p.evidence.items() if r.kind != "other" and supports(r.text, r.aliases, ev.text)]
            verdicts.append(
                VerdictOut(
                    requirement_id=r.id, status="met" if hits else "unknown", evidence_ids=hits[:STUB_VERDICT_EVIDENCE]
                )
            )
        contribs = []
        for source in INTERACTION_SOURCES:
            ids = [e for e, ev in p.evidence.items() if ev.source == source]
            if ids:
                effect = "positive" if source == "placements" else "neutral"
                contribs.append(
                    ContributionOut(
                        source=source,
                        effect=effect,
                        summary=f"{len(ids)} {source.replace('_', ' ')} record(s) on file.",
                        evidence_ids=ids[:STUB_CONTRIBUTION_EVIDENCE],
                    )
                )
        met = sum(1 for v in verdicts if v.status == "met")
        out.append(
            AssessmentOut(
                handle=p.handle,
                verdicts=verdicts,
                source_contributions=contribs,
                reason=f"Keyword evidence found for {met} of {len(reqs)} requirements (stub assessor, not Claude).",
                concerns=[],
                injection_suspected=False,
            )
        )
    return BatchOut(assessments=out)


async def assess_all(
    *,
    claude: ClaudeClient | None,
    settings: Settings,
    packets: list[Packet],
    reqs: list[Requirement],
    job_block: str,
    emit: Emit,
    deadline: float,
) -> AssessOutcome:
    outcome = AssessOutcome()
    by_handle = {p.handle: p for p in packets}
    batches = deal_batches([p.handle for p in packets], settings.assess_batch_size)
    sem = asyncio.Semaphore(max(1, settings.assess_concurrency))
    completed = 0

    async def call(handles: list[str], repair_note: str | None) -> BatchOut:
        batch_packets = [by_handle[h] for h in handles]
        if settings.llm_mode == "stub" or claude is None:
            outcome.models.add(STUB_MODEL)
            return stub_assess(batch_packets, reqs)
        content = [
            {"type": "text", "text": job_block, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "\n\n".join(p.rendered for p in batch_packets)},
        ]
        if repair_note:
            content.append({"type": "text", "text": repair_note})
        result = await claude.structured(
            system=ASSESS_SYSTEM_PROMPT,
            content=content,
            output_model=BatchOut,
            effort=settings.claude_effort_assess,
            max_tokens=ASSESS_MAX_TOKENS,
        )
        outcome.models.add(result.model)
        outcome.fallback_used |= result.fallback_used
        outcome.raw_outputs.append({"handles": handles, "model": result.model, "output": result.raw_text})
        return result.parsed

    async def run(handles: list[str], *, repaired: bool = False, retried_missing: bool = False) -> None:
        try:
            parsed = await call(
                handles,
                None if not repaired else REPAIR_NOTE,
            )
        except ClaudeTruncated:
            if len(handles) > 1:
                mid = len(handles) // 2
                await asyncio.gather(run(handles[:mid]), run(handles[mid:]))
            else:
                outcome.not_assessed.update({h: "model_output_too_long" for h in handles})
            return
        except ClaudeOutputInvalid:
            if not repaired:
                await run(handles, repaired=True, retried_missing=retried_missing)
            else:
                outcome.not_assessed.update({h: "invalid_model_output" for h in handles})
            return
        except ClaudeRefusal:
            outcome.not_assessed.update({h: "model_declined" for h in handles})
            return
        except (ClaudeRateLimited, ClaudeAuthError, ClaudeNotConfigured):
            raise
        except ClaudeError:
            outcome.not_assessed.update({h: "model_error" for h in handles})
            return

        validated, missing, issues = validate_batch({h: by_handle[h] for h in handles}, reqs, parsed)
        outcome.assessments.update(validated)
        outcome.issues.extend(issues)
        for va in validated.values():
            outcome.issues.extend(f"{va.handle}: {msg}" for msg in va.issues)
        if missing:
            if not retried_missing:
                await run(sorted(missing), repaired=repaired, retried_missing=True)
            else:
                outcome.not_assessed.update({h: "missing_from_model_output" for h in missing})

    async def guarded(handles: list[str]) -> None:
        nonlocal completed
        async with sem:
            await run(handles)
        completed += 1
        await emit("progress", {"stage": STAGE_ASSESS, "done": completed, "total": len(batches)})

    tasks = [asyncio.create_task(guarded(b)) for b in batches]
    if not tasks:
        return outcome
    timeout = max(1.0, deadline - time.monotonic())
    done, pending = await asyncio.wait(tasks, timeout=timeout)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    for task in done:
        exc = task.exception()
        if exc is not None:
            if isinstance(exc, ClaudeRateLimited | ClaudeAuthError | ClaudeNotConfigured):
                raise exc
            outcome.issues.append(f"batch failed: {type(exc).__name__}")
    for handle in by_handle:
        if handle not in outcome.assessments and handle not in outcome.not_assessed:
            outcome.not_assessed[handle] = "deadline" if pending else "model_error"
    return outcome
