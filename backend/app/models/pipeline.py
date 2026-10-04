"""Internal dataclasses passed between the search pipeline's steps (never sent to the UI as-is)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from app.models.jobdiva import CandidateRecord
from app.models.results import QueryStat

if TYPE_CHECKING:
    from app.clients.claude import ClaudeClient
    from app.clients.jobdiva.client import JobDivaClient
    from app.core.config import Settings
    from app.services.jobs import JobsService

Emit = Callable[[str, dict], Awaitable[None]]
ValidatedStatus = Literal["met", "partial", "not_met", "unknown", "unverified"]


@dataclass
class Deps:
    settings: Settings
    jobdiva: JobDivaClient
    claude: ClaudeClient
    jobs: JobsService


# ------------------------------------------------------------------ retrieval


@dataclass(frozen=True)
class TalentQuery:
    """One TalentSearch call in the retrieval plan."""

    label: str
    skills: tuple[str, ...]
    title: str | None
    states: tuple[str, ...]
    resume_count: int


@dataclass
class Pool:
    records: dict[str, CandidateRecord] = field(default_factory=dict)
    queries: list[QueryStat] = field(default_factory=list)
    partial: bool = False
    warnings: list[str] = field(default_factory=list)

    def add(self, rec: CandidateRecord) -> bool:
        is_new = rec.candidate_id not in self.records
        self.records[rec.candidate_id] = rec
        return is_new

    @property
    def linked_ids(self) -> set[str]:
        return {cid for cid, r in self.records.items() if r.job_linked}


@dataclass
class PreScore:
    score: float
    skill_coverage: float | None = None
    matched_terms: list[str] = field(default_factory=list)
    title_similarity: float | None = None
    distance_mi: float | None = None
    location_fit: float | None = None
    years_fit: float | None = None
    recency: float | None = None
    excluded: str | None = None


# ---------------------------------------------------------- packets & validation


@dataclass
class Evidence:
    eid: str
    source: str
    label: str
    text: str
    date: str | None = None


@dataclass
class Packet:
    handle: str
    candidate_id: str
    evidence: dict[str, Evidence]
    rendered: str = ""


@dataclass
class ValidatedVerdict:
    requirement_id: str
    status: ValidatedStatus
    evidence_ids: list[str]
    downgraded_from: str | None = None


@dataclass
class ValidatedContribution:
    source: str
    effect: str
    summary: str
    evidence_ids: list[str]


@dataclass
class ValidatedAssessment:
    handle: str
    candidate_id: str
    verdicts: dict[str, ValidatedVerdict]
    contributions: list[ValidatedContribution]
    reason: str
    concerns: list[str]
    injection_suspected: bool
    issues: list[str] = field(default_factory=list)


# ------------------------------------------------------------ assessment & scoring


@dataclass
class AssessOutcome:
    assessments: dict[str, ValidatedAssessment] = field(default_factory=dict)
    not_assessed: dict[str, str] = field(default_factory=dict)  # handle → reason
    issues: list[str] = field(default_factory=list)
    raw_outputs: list[dict] = field(default_factory=list)
    models: set[str] = field(default_factory=set)
    fallback_used: bool = False


@dataclass
class Scored:
    va: ValidatedAssessment
    fit: int
    excluded: str | None  # "not_a_fit" | "insufficient_evidence"
    failing_musts: list[str]
