"""Step 1 — recruiter query + notes + job description → structured SearchIntent (Claude, or the stub parser)."""

from __future__ import annotations

import re

from app.clients.claude import ClaudeClient
from app.constants.intent import (
    JOB_DESCRIPTION_CHARS,
    MAX_ALIASES,
    MAX_LIST_ITEMS,
    MAX_RADIUS_MI,
    MAX_REQUIREMENTS,
    MAX_SYNONYMS,
    MAX_TITLES,
    STUB_MAX_REQUIREMENTS,
    STUB_REQUIREMENT_CHARS,
    SUMMARY_CHARS,
)
from app.constants.llm import INTENT_MAX_TOKENS
from app.constants.ranking import DEFAULT_RADIUS_MI
from app.models.intent import LocationTarget, Requirement, SearchIntent, TitleTarget, YearsTarget
from app.models.jobdiva import Job
from app.prompts.intent import INTENT_SYSTEM_PROMPT
from app.utils.text import clip, escape_untrusted


def _block(tag: str, text: str | None) -> dict:
    body = escape_untrusted(text or "") or "(none provided)"
    return {"type": "text", "text": f"<{tag}>\n{body}\n</{tag}>"}


def job_context(job: Job) -> str:
    where = ", ".join(p for p in (job.city, job.state) if p)
    lines = [
        f"Title: {job.title}",
        f"Client: {job.company or 'unknown'}",
        f"Location: {where or 'unknown'}" + (f" (zip {job.zipcode})" if job.zipcode else ""),
        f"Onsite/remote: {job.onsite_remote or 'unknown'}",
        f"Job type: {job.job_type or 'unknown'}",
        "",
        clip(job.description_text or "(no description in JobDiva)", JOB_DESCRIPTION_CHARS),
    ]
    return "\n".join(lines)


async def parse_intent(claude: ClaudeClient, *, job: Job, query: str, notes: str, effort: str) -> SearchIntent:
    content = [
        _block("job_description", job_context(job)),
        _block("recruiter_query", query),
        _block("recruiter_notes", notes),
    ]
    result = await claude.structured(
        system=INTENT_SYSTEM_PROMPT,
        content=content,
        output_model=SearchIntent,
        effort=effort,
        max_tokens=INTENT_MAX_TOKENS,
    )
    return normalize_intent(result.parsed, job)


def _dedupe(items: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out[:limit]


def normalize_intent(intent: SearchIntent, job: Job | None = None) -> SearchIntent:
    """Deterministic clean-up applied to both Claude output and recruiter-edited intents."""
    data = intent.model_copy(deep=True)
    data.titles = [t for t in data.titles if t.title.strip()][:MAX_TITLES]
    for t in data.titles:
        t.title = t.title.strip()
        t.synonyms = _dedupe([s for s in t.synonyms if s.strip().lower() != t.title.lower()], MAX_SYNONYMS)

    reqs: list[Requirement] = []
    seen_text: set[str] = set()
    for r in data.requirements:
        text = re.sub(r"\s+", " ", r.text).strip()
        if not text or text.lower() in seen_text:
            continue
        seen_text.add(text.lower())
        r.text = text
        r.aliases = _dedupe([a for a in r.aliases if a.strip().lower() != text.lower()], MAX_ALIASES)
        reqs.append(r)
    for i, r in enumerate(reqs[:MAX_REQUIREMENTS], start=1):
        r.id = f"r{i}"
    data.requirements = reqs[:MAX_REQUIREMENTS]

    if data.location is not None:
        loc = data.location
        if loc.radius_mi is not None:
            loc.radius_mi = max(0, min(MAX_RADIUS_MI, loc.radius_mi))
        if not any((loc.city, loc.state, loc.zipcode)) and not loc.remote_ok:
            data.location = None
        elif job is not None and not loc.zipcode and job.zipcode and loc.source == "job":
            loc.zipcode = job.zipcode
    if data.years is not None:
        y = data.years
        if y.min is not None and y.min < 0:
            y.min = 0
        if y.min is not None and y.max is not None and y.min > y.max:
            y.min, y.max = y.max, y.min
        if y.min is None and y.max is None:
            data.years = None

    data.keywords = _dedupe(data.keywords, MAX_LIST_ITEMS)
    data.exclusions = _dedupe(data.exclusions, MAX_LIST_ITEMS)
    data.preferences_from_notes = _dedupe(data.preferences_from_notes, MAX_LIST_ITEMS)
    data.ambiguities = _dedupe(data.ambiguities, MAX_LIST_ITEMS)
    data.summary = clip(data.summary, SUMMARY_CHARS)
    return data


def stub_intent(job: Job, query: str) -> SearchIntent:
    """LLM_MODE=stub only: naive parse so the UI can be exercised without an API key."""
    phrases = [p.strip() for p in re.split(r",|;|\band\b|\bwith\b", query or "") if p.strip()]
    years = re.search(r"(\d+)\s*\+?\s*(?:years|yrs)", query or "", re.I)
    reqs = [
        Requirement(
            id=f"r{i}", text=p[:STUB_REQUIREMENT_CHARS], kind="skill", must_have=False, aliases=[], source="query"
        )
        for i, p in enumerate(
            [p for p in phrases if not re.search(r"\d+\s*\+?\s*(years|yrs)", p, re.I)][:STUB_MAX_REQUIREMENTS], start=1
        )
    ]
    return SearchIntent(
        summary=f"(stub) {job.title}" + (f" — {query.strip()}" if query.strip() else ""),
        titles=[TitleTarget(title=job.title, synonyms=[], source="job")],
        location=LocationTarget(
            city=job.city,
            state=job.state,
            zipcode=job.zipcode,
            radius_mi=DEFAULT_RADIUS_MI,
            remote_ok=None,
            required=False,
            source="job",
        )
        if (job.city or job.state or job.zipcode)
        else None,
        years=YearsTarget(min=int(years.group(1)), max=None, required=False, source="query") if years else None,
        requirements=reqs,
        keywords=[],
        exclusions=[],
        preferences_from_notes=[],
        ambiguities=["Stub parser (LLM_MODE=stub): requirements are the comma-separated phrases of the query."],
    )
