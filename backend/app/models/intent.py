"""Search intent: the structured criteria Claude derives from the job, query and notes (also a Claude output format).

Models used as Claude output formats declare every field without defaults so the generated JSON
schema marks them all required (structured outputs need this).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Source = Literal["query", "job", "notes"]
RequirementKind = Literal["skill", "title", "keyword", "authorization", "other"]


class TitleTarget(BaseModel):
    title: str
    synonyms: list[str]
    source: Source


class LocationTarget(BaseModel):
    city: str | None
    state: str | None
    zipcode: str | None
    radius_mi: int | None
    remote_ok: bool | None
    required: bool
    source: Source


class YearsTarget(BaseModel):
    min: int | None
    max: int | None
    required: bool
    source: Source


class Requirement(BaseModel):
    id: str
    text: str
    kind: RequirementKind
    must_have: bool
    aliases: list[str]
    source: Source


class SearchIntent(BaseModel):
    summary: str
    titles: list[TitleTarget]
    location: LocationTarget | None
    years: YearsTarget | None
    requirements: list[Requirement]
    keywords: list[str]
    exclusions: list[str]
    preferences_from_notes: list[str]
    ambiguities: list[str]
