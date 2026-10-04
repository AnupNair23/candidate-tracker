"""Search result returned to the UI: shortlist entries with evidence, the funnel and the shortfall explanation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.assessment import EvidenceSource
from app.models.intent import RequirementKind, SearchIntent


class EvidenceRef(BaseModel):
    id: str
    source: EvidenceSource
    label: str
    quote: str
    date: str | None = None


class SkillMatch(BaseModel):
    requirement_id: str
    label: str
    kind: RequirementKind
    must_have: bool
    status: Literal["met", "partial", "not_met", "unknown", "unverified"]
    evidence: list[EvidenceRef] = Field(default_factory=list)


class Contribution(BaseModel):
    source: EvidenceSource
    effect: Literal["positive", "negative", "neutral"]
    summary: str
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ShortlistEntry(BaseModel):
    rank: int
    candidate_id: str
    name: str
    title: str | None = None
    employer: str | None = None
    city: str | None = None
    state: str | None = None
    distance_mi: float | None = None
    years_experience: float | None = None
    fit_score: int
    stars: int
    tier: Literal["strong", "good", "possible"]
    reason: str
    matched: list[SkillMatch]
    gaps: list[SkillMatch]
    contributions: list[Contribution]
    concerns: list[str]
    injection_suspected: bool = False
    job_linked: bool = False
    job_link_status: str | None = None
    placed_by_us_year: int | None = None
    sources_unavailable: list[str] = Field(default_factory=list)
    assessed_by: str


class QueryStat(BaseModel):
    label: str
    criteria: str
    found: int | None = None
    returned: int = 0
    new: int = 0
    error: str | None = None


class RequirementFailure(BaseModel):
    requirement_id: str
    label: str
    count: int
    sole_blocker: int


class Funnel(BaseModel):
    queries: list[QueryStat] = Field(default_factory=list)
    pool: int = 0
    linked: int = 0
    excluded_by_filter: dict[str, int] = Field(default_factory=dict)
    prescreened_out: int = 0
    reviewed: int = 0
    assessed: int = 0
    not_assessed: int = 0
    not_assessed_reasons: dict[str, int] = Field(default_factory=dict)
    not_a_fit: int = 0
    failing_requirements: list[RequirementFailure] = Field(default_factory=list)
    insufficient_evidence: int = 0
    shortlisted: int = 0
    retrieval_partial: bool = False


class Shortfall(BaseModel):
    headline: str
    reasons: list[str]
    suggestions: list[str]


class SearchResult(BaseModel):
    job_id: str
    search_id: str
    generated_at: str
    intent: SearchIntent
    shortlist: list[ShortlistEntry]
    funnel: Funnel
    shortfall: Shortfall | None
    partial: bool
    warnings: list[str]
    assessed_by: str
    replayed: bool = False
