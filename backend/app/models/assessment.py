"""Claude structured-output models for candidate assessment.

Every field is declared without a default so the generated JSON schema marks them all required
(structured outputs need this).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

EvidenceSource = Literal[
    "profile",
    "resume",
    "notes",
    "recorded_conversations",
    "submissions",
    "interviews",
    "placements",
    "client_feedback",
]
INTERACTION_SOURCES: tuple[str, ...] = (
    "notes",
    "recorded_conversations",
    "submissions",
    "interviews",
    "placements",
    "client_feedback",
)


class VerdictOut(BaseModel):
    requirement_id: str
    status: Literal["met", "partial", "not_met", "unknown"]
    evidence_ids: list[str]


class ContributionOut(BaseModel):
    source: EvidenceSource
    effect: Literal["positive", "negative", "neutral"]
    summary: str
    evidence_ids: list[str]


class AssessmentOut(BaseModel):
    handle: str
    verdicts: list[VerdictOut]
    source_contributions: list[ContributionOut]
    reason: str
    concerns: list[str]
    injection_suspected: bool


class BatchOut(BaseModel):
    assessments: list[AssessmentOut]
