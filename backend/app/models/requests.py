"""HTTP request bodies."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.constants.api import REQUEST_TEXT_MAX_CHARS
from app.models.intent import SearchIntent


class IntentRequest(BaseModel):
    query: str = Field(default="", max_length=REQUEST_TEXT_MAX_CHARS)
    notes: str = Field(default="", max_length=REQUEST_TEXT_MAX_CHARS)


class SearchRequest(BaseModel):
    intent: SearchIntent
    query: str = Field(default="", max_length=REQUEST_TEXT_MAX_CHARS)
    notes: str = Field(default="", max_length=REQUEST_TEXT_MAX_CHARS)
