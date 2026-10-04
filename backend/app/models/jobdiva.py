"""Normalized DTOs built from JobDiva v1 payloads (see `app.clients.jobdiva.mappers`)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------- jobs


class Job(BaseModel):
    job_id: str
    ref: str | None = None
    title: str
    company: str | None = None
    city: str | None = None
    state: str | None = None
    zipcode: str | None = None
    status: str | None = None
    job_type: str | None = None
    onsite_remote: str | None = None
    rate_min: float | None = None
    rate_max: float | None = None
    issue_date: str | None = None
    description_html: str | None = None
    description_text: str | None = None


# ---------------------------------------------------------------------- candidates


class Qualification(BaseModel):
    name: str
    value: str


class CandidateRecord(BaseModel):
    """Everything the pipeline knows about one candidate. Lives only in request memory."""

    candidate_id: str
    first_name: str | None = None
    last_name: str | None = None
    title: str | None = None
    employer: str | None = None
    city: str | None = None
    state: str | None = None
    zipcode: str | None = None
    country: str | None = None
    email: str | None = None
    phone: str | None = None
    years_experience: float | None = None
    available: bool | None = None
    work_authorization: str | None = None
    updated_on: str | None = None
    qualifications: list[Qualification] = Field(default_factory=list)
    search_text: str | None = None  # text returned by candidate search (TalentSearch ABSTRACT), if any
    search_matches: list[str] = Field(default_factory=list)  # skills/titles JobDiva's resume search matched
    resume_text: str | None = None
    interactions: list[Interaction] = Field(default_factory=list)
    source_status: dict[str, Literal["ok", "none", "unavailable", "not_fetched"]] = Field(default_factory=dict)
    job_linked: bool = False
    job_link_status: str | None = None

    @property
    def name(self) -> str:
        full = " ".join(p for p in (self.first_name, self.last_name) if p)
        return full or f"Candidate {self.candidate_id}"

    @property
    def skills(self) -> list[str]:
        return [q.value for q in self.qualifications if q.value]


# --------------------------------------------------------------------- interactions

InteractionType = Literal[
    "notes", "recorded_conversations", "submissions", "interviews", "placements", "client_feedback"
]


class Interaction(BaseModel):
    interaction_id: str
    type: InteractionType
    date: str | None = None
    author: str | None = None
    client: str | None = None
    job_id: str | None = None
    job_title: str | None = None
    status: str | None = None
    content: str


class WorkHistoryItem(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    start: str | None = None
    end: str | None = None
    description: str | None = None


CandidateRecord.model_rebuild()
