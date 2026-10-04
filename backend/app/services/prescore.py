"""Step 3 — deterministic pre-score: decides who is reviewed in depth and later breaks ties.

Unknown signals are neutral (never a penalty); recruiter-required filters exclude only on a known conflict.
"""

from __future__ import annotations

from datetime import date

from app.clients.jobdiva.mappers import parse_date
from app.constants.ranking import (
    ABOVE_MAX_YEARS_FIT,
    AGING_PROFILE_DAYS,
    AGING_PROFILE_FIT,
    DEFAULT_RADIUS_MI,
    LOCATION_FALLOFF_RADII,
    MUST_HAVE_WEIGHT,
    NICE_TO_HAVE_WEIGHT,
    OTHER_STATE_LOCATION_FIT,
    PRESCORE_TERM_KINDS,
    RECENT_PROFILE_DAYS,
    RECENT_PROFILE_FIT,
    SAME_STATE_LOCATION_FIT,
    STALE_PROFILE_FIT,
    UNKNOWN_SIGNAL,
    W_LOCATION,
    W_RECENCY,
    W_SKILLS,
    W_TITLE,
    W_YEARS,
)
from app.models.intent import SearchIntent
from app.models.jobdiva import CandidateRecord, Job
from app.models.pipeline import Pool, PreScore
from app.services.geo import distances_miles
from app.utils.text import norm, term_in_text, tokens


def _skill_corpus(rec: CandidateRecord) -> str:
    parts = [rec.title or "", " ".join(rec.skills), rec.search_text or "", rec.resume_text or ""]
    return " ".join(p for p in parts if p).strip()


def _title_similarity(title: str | None, intent: SearchIntent) -> float | None:
    if not title or not intent.titles:
        return None
    best = 0.0
    cand = tokens(title)
    for t in intent.titles:
        for target in [t.title, *t.synonyms]:
            if norm(target) and norm(target) in norm(title):
                return 1.0
            tgt = tokens(target)
            if cand and tgt:
                best = max(best, len(cand & tgt) / len(cand | tgt))
    return round(best, 3)


def prescore(
    rec: CandidateRecord, intent: SearchIntent, distance_mi: float | None, today: date | None = None
) -> PreScore:
    today = today or date.today()
    ps = PreScore(score=0.0, distance_mi=distance_mi)

    skills = [r for r in intent.requirements if r.kind in PRESCORE_TERM_KINDS]
    corpus = _skill_corpus(rec)
    if skills and corpus:
        total = matched = 0.0
        for r in skills:
            weight = MUST_HAVE_WEIGHT if r.must_have else NICE_TO_HAVE_WEIGHT
            total += weight
            if any(term_in_text(term, corpus) for term in [r.text, *r.aliases]):
                matched += weight
                ps.matched_terms.append(r.text)
        ps.skill_coverage = round(matched / total, 3) if total else None

    ps.title_similarity = _title_similarity(rec.title, intent)

    loc = intent.location
    if loc is not None:
        if loc.remote_ok:
            ps.location_fit = 1.0
        elif distance_mi is not None:
            radius = loc.radius_mi or DEFAULT_RADIUS_MI
            ps.location_fit = (
                1.0
                if distance_mi <= radius
                else max(0.0, 1 - (distance_mi - radius) / (radius * LOCATION_FALLOFF_RADII))
            )
            if loc.required and distance_mi > radius:
                ps.excluded = "location"
        elif rec.state and loc.state:
            ps.location_fit = (
                SAME_STATE_LOCATION_FIT
                if rec.state.strip().lower() == loc.state.strip().lower()
                else OTHER_STATE_LOCATION_FIT
            )

    yrs = intent.years
    if yrs is not None and rec.years_experience is not None:
        y = rec.years_experience
        if yrs.min is not None and y < yrs.min:
            ps.years_fit = max(0.0, 1 - (yrs.min - y) / max(yrs.min, 1))
            if yrs.required and ps.excluded is None:
                ps.excluded = "years"
        elif yrs.max is not None and y > yrs.max:
            ps.years_fit = ABOVE_MAX_YEARS_FIT
        else:
            ps.years_fit = 1.0

    updated = parse_date(rec.updated_on)
    if updated:
        age_days = (today - updated).days
        ps.recency = (
            RECENT_PROFILE_FIT
            if age_days <= RECENT_PROFILE_DAYS
            else AGING_PROFILE_FIT
            if age_days <= AGING_PROFILE_DAYS
            else STALE_PROFILE_FIT
        )

    def val(x: float | None) -> float:
        return UNKNOWN_SIGNAL if x is None else x  # unknown is neutral, never a penalty

    ps.score = round(
        W_SKILLS * val(ps.skill_coverage)
        + W_TITLE * val(ps.title_similarity)
        + W_LOCATION * val(ps.location_fit)
        + W_YEARS * val(ps.years_fit)
        + W_RECENCY * val(ps.recency),
        4,
    )
    return ps


async def prescore_pool(pool: Pool, intent: SearchIntent, job: Job) -> dict[str, PreScore]:
    origin = (intent.location.zipcode if intent.location and intent.location.zipcode else None) or job.zipcode
    dists = await distances_miles(origin, {cid: r.zipcode for cid, r in pool.records.items()})
    return {cid: prescore(rec, intent, dists.get(cid)) for cid, rec in pool.records.items()}


def select_for_review(pool: Pool, scores: dict[str, PreScore], top_n: int) -> tuple[list[str], int, dict[str, int]]:
    """Return (ids to review ordered by pre-score, prescreened-out count, hard-filter exclusion counts)."""
    excluded: dict[str, int] = {}
    eligible: list[str] = []
    for cid, ps in scores.items():
        if ps.excluded:
            excluded[ps.excluded] = excluded.get(ps.excluded, 0) + 1
        else:
            eligible.append(cid)
    eligible.sort(key=lambda c: (-scores[c].score, c))
    linked = [c for c in eligible if pool.records[c].job_linked]
    others = [c for c in eligible if not pool.records[c].job_linked]
    chosen = others[:top_n]
    selected = sorted(set(linked) | set(chosen), key=lambda c: (-scores[c].score, c))
    return selected, len(others) - len(chosen), excluded
