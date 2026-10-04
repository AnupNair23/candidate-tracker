"""Step 7 — deterministic fit score, stars, tier and shortlist entries from validated assessments."""

from __future__ import annotations

from app.constants.assessment import EVIDENCE_QUOTE_CHARS
from app.constants.ranking import (
    INTERACTION_ADJUSTMENT,
    INTERACTION_ADJUSTMENT_CAP,
    MUST_HAVE_WEIGHT,
    NICE_TO_HAVE_WEIGHT,
    NO_REQUIREMENTS_FIT,
    STAR_THRESHOLDS,
    STATUS_SCORE,
    TIER_THRESHOLDS,
)
from app.models.assessment import INTERACTION_SOURCES
from app.models.intent import Requirement
from app.models.jobdiva import CandidateRecord
from app.models.pipeline import Packet, PreScore, Scored, ValidatedAssessment
from app.models.results import Contribution, EvidenceRef, ShortlistEntry, SkillMatch
from app.utils.text import clip


def score_assessment(va: ValidatedAssessment, reqs: list[Requirement], rec: CandidateRecord) -> Scored:
    total = gained = 0.0
    failing: list[str] = []
    any_support = False
    for r in reqs:
        weight = MUST_HAVE_WEIGHT if r.must_have else NICE_TO_HAVE_WEIGHT
        total += weight
        v = va.verdicts[r.id]
        gained += weight * STATUS_SCORE.get(v.status, 0.0)
        if v.status in ("met", "partial"):
            any_support = True
        if r.must_have and v.status == "not_met" and v.evidence_ids:
            failing.append(r.id)
    fit = gained / total if total else NO_REQUIREMENTS_FIT
    adjust = 0.0
    for c in va.contributions:
        if c.source in INTERACTION_SOURCES and c.source != "notes":
            adjust += (
                INTERACTION_ADJUSTMENT
                if c.effect == "positive"
                else -INTERACTION_ADJUSTMENT
                if c.effect == "negative"
                else 0.0
            )
    fit = min(1.0, max(0.0, fit + max(-INTERACTION_ADJUSTMENT_CAP, min(INTERACTION_ADJUSTMENT_CAP, adjust))))
    positive = any(c.effect == "positive" for c in va.contributions)
    excluded = None
    if failing:
        excluded = "not_a_fit"
    elif not any_support and not positive and not rec.job_linked:
        excluded = "insufficient_evidence"
    return Scored(va=va, fit=round(fit * 100), excluded=excluded, failing_musts=failing)


def stars_for(fit: int) -> int:
    t = STAR_THRESHOLDS
    return 5 if fit >= t[5] else 4 if fit >= t[4] else 3 if fit >= t[3] else 2 if fit >= t[2] else 1


def tier_for(fit: int) -> str:
    return "strong" if fit >= TIER_THRESHOLDS["strong"] else "good" if fit >= TIER_THRESHOLDS["good"] else "possible"


def _refs(packet: Packet, ids: list[str]) -> list[EvidenceRef]:
    refs = []
    for eid in ids:
        ev = packet.evidence.get(eid)
        if ev:
            refs.append(
                EvidenceRef(
                    id=eid, source=ev.source, label=ev.label, quote=clip(ev.text, EVIDENCE_QUOTE_CHARS), date=ev.date
                )
            )
    return refs


def to_entry(
    rank: int, s: Scored, rec: CandidateRecord, packet: Packet, reqs: list[Requirement], pre: PreScore, model: str
) -> ShortlistEntry:
    matched: list[SkillMatch] = []
    gaps: list[SkillMatch] = []
    for r in reqs:
        v = s.va.verdicts[r.id]
        item = SkillMatch(
            requirement_id=r.id,
            label=r.text,
            kind=r.kind,
            must_have=r.must_have,
            status=v.status,
            evidence=_refs(packet, v.evidence_ids),
        )
        (matched if v.status in ("met", "partial") else gaps).append(item)
    placements = [i.date for i in rec.interactions if i.type == "placements" and i.date]
    return ShortlistEntry(
        rank=rank,
        candidate_id=rec.candidate_id,
        name=rec.name,
        title=rec.title,
        employer=rec.employer,
        city=rec.city,
        state=rec.state,
        distance_mi=pre.distance_mi,
        years_experience=rec.years_experience,
        fit_score=s.fit,
        stars=stars_for(s.fit),
        tier=tier_for(s.fit),
        reason=s.va.reason,
        matched=matched,
        gaps=gaps,
        contributions=[
            Contribution(source=c.source, effect=c.effect, summary=c.summary, evidence=_refs(packet, c.evidence_ids))
            for c in s.va.contributions
        ],
        concerns=s.va.concerns,
        injection_suspected=s.va.injection_suspected,
        job_linked=rec.job_linked,
        job_link_status=rec.job_link_status,
        placed_by_us_year=int(max(placements)[:4]) if placements else None,
        sources_unavailable=sorted(k for k, v in rec.source_status.items() if v in ("unavailable", "not_fetched")),
        assessed_by=model,
    )
